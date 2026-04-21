import json
import logging
import re
from pathlib import Path

import requests


logger = logging.getLogger(__name__)

STORAGE_DIR = Path(__file__).parent.parent / "storage"

VG_AUTH_REFRESH_URL = "https://services.virtuagym.com/v2/auth/refresh"
VG_KEYCLOAK_TOKEN_URL = "https://iam.services.virtuagym.com/auth/realms/virtuagym/protocol/openid-connect/token"
VG_KEYCLOAK_CLIENT_ID = "monolith-web"


def session_file_for_user(user: str) -> Path:
    safe_name = re.sub(r"[^\w\-]", "_", user.lower())
    return STORAGE_DIR / f"{safe_name}.json"


def load_cookies(session: requests.Session, cookie_file: Path) -> bool:
    if not cookie_file.exists():
        return False
    try:
        with open(cookie_file) as f:
            data = json.load(f)
        for cookie in data.get("cookies", []):
            session.cookies.set(
                cookie["name"], cookie["value"],
                domain=cookie.get("domain", ""), path=cookie.get("path", "/"),
            )
        logger.info("Loaded %d cookies from %s", len(data.get("cookies", [])), cookie_file)
        return True
    except (json.JSONDecodeError, KeyError) as e:
        logger.warning("Failed to load cookies: %s", e)
        return False


def save_cookies(session: requests.Session, cookie_file: Path, domain: str):
    cookie_file.parent.mkdir(parents=True, exist_ok=True)
    cookies = []
    for c in session.cookies:
        cookies.append({
            "name": c.name, "value": c.value,
            "domain": c.domain or domain, "path": c.path or "/",
            "httpOnly": False, "secure": True, "sameSite": "Lax",
        })
    with open(cookie_file, "w") as f:
        json.dump({"cookies": cookies, "origins": []}, f, indent=2)
    logger.info("Saved %d cookies to %s", len(cookies), cookie_file)


def save_cookies_from_playwright(context, cookie_file: Path):
    cookie_file.parent.mkdir(parents=True, exist_ok=True)
    context.storage_state(path=str(cookie_file))
    logger.info("Saved session to %s", cookie_file)


def check_session(session: requests.Session, base_url: str) -> bool:
    try:
        resp = session.get(f"{base_url}/classes", allow_redirects=False, timeout=10)
        if resp.status_code == 302 and "/signin" in resp.headers.get("Location", ""):
            logger.info("Session expired (redirected to signin)")
            return False
        if resp.status_code == 200:
            if 'href="/signin"' in resp.text:
                logger.info("Session expired (signin link in page)")
                return False
            logger.info("Session valid (HTTP 200, authenticated content)")
            return True
        logger.warning("Unexpected status %d during session check", resp.status_code)
        return False
    except requests.RequestException as e:
        logger.warning("Session check failed: %s", e)
        return False


def refresh_access_token(session: requests.Session, domain: str, cookie_file: Path) -> bool:
    """Refresh old-style vg-user-access-token via services.virtuagym.com/v2/auth/refresh.

    Uses the old-style refresh token as Bearer auth. No CAPTCHA needed.
    The old refresh token has ~250-day expiry.
    """
    refresh_token = None
    old_access_domain = None
    for c in session.cookies:
        if c.name == "vg-user-refresh-token" and c.value:
            refresh_token = c.value
        if c.name == "vg-user-access-token":
            old_access_domain = c.domain
    if not refresh_token:
        logger.info("No old-style refresh token available")
        return False

    try:
        resp = requests.post(
            VG_AUTH_REFRESH_URL,
            headers={"Authorization": f"Bearer {refresh_token}"},
            timeout=10,
        )
        if resp.status_code != 200:
            logger.warning("Token refresh failed: HTTP %d", resp.status_code)
            return False
        data = resp.json()
        new_access = data.get("accessToken")
        if not new_access:
            logger.warning("Token refresh response missing accessToken")
            return False

        # Remove all existing access tokens, then set the new one on the
        # same domain as the original to avoid duplicate cookie conflicts.
        _clear_cookie(session, "vg-user-access-token")
        token_domain = old_access_domain or domain
        session.cookies.set("vg-user-access-token", new_access, domain=token_domain, path="/")
        logger.info("Refreshed access token (domain=%s)", token_domain)
        save_cookies(session, cookie_file, domain)
        return True
    except requests.RequestException as e:
        logger.warning("Token refresh request failed: %s", e)
        return False


def _clear_cookie(session: requests.Session, name: str):
    """Remove all cookies with the given name from the session."""
    to_remove = [(c.domain, c.path) for c in session.cookies if c.name == name]
    for cookie_domain, cookie_path in to_remove:
        session.cookies.clear(cookie_domain, cookie_path, name)


def login_with_keycloak(session: requests.Session, email: str, password: str, domain: str, cookie_file: Path) -> bool:
    """Login via Keycloak password grant — no CAPTCHA required.

    Merges v3 tokens into the existing session (preserving old cookies like
    the old-style refresh token). Does NOT create a new session.
    """
    logger.info("Logging in via Keycloak password grant...")
    resp = requests.post(
        VG_KEYCLOAK_TOKEN_URL,
        data={
            "grant_type": "password",
            "client_id": VG_KEYCLOAK_CLIENT_ID,
            "username": email,
            "password": password,
        },
        timeout=15,
    )
    if resp.status_code != 200:
        logger.warning("Keycloak login failed: HTTP %d: %s", resp.status_code, resp.text[:200])
        return False

    tokens = resp.json()
    _clear_cookie(session, "vg-user-access-token-v3")
    _clear_cookie(session, "vg-user-refresh-token-v3")
    session.cookies.set("vg-user-access-token-v3", tokens["access_token"], domain=domain, path="/")
    session.cookies.set("vg-user-refresh-token-v3", tokens["refresh_token"], domain=domain, path="/")
    save_cookies(session, cookie_file, domain)
    logger.info("Keycloak login successful (v3 tokens merged)")
    return True


def login_with_playwright(base_url: str, email: str, password: str, cookie_file: Path, headless: bool = False) -> requests.Session:
    import time
    from playwright.sync_api import sync_playwright

    logger.info("Logging in via Playwright browser (headless=%s)...", headless)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        page = context.new_page()
        page.goto(f"{base_url}/signin")
        page.wait_for_load_state("networkidle")
        page.fill('input[name="username"]', email)
        page.fill('input[name="password"]', password)

        if headless:
            page.click('button:has-text("Login"), button:has-text("Iniciar sesión"), input[type="submit"]')
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(3000)
        else:
            print("Browser opened. Click Login and solve CAPTCHA if present.")
            print("Waiting up to 3 minutes for login to complete...")
            for i in range(90):
                time.sleep(2)
                cookies = context.cookies()
                auth_cookies = [c for c in cookies if c["name"] == "vg-user-access-token" and c["value"]]
                if auth_cookies:
                    logger.info("Auth cookie detected after %ds", (i + 1) * 2)
                    break
                if "/signin" not in page.url:
                    logger.info("URL changed to %s after %ds", page.url, (i + 1) * 2)
                    break
            else:
                logger.warning("Timeout waiting for login")

        cookies = context.cookies()
        auth_cookies = [c for c in cookies if c["name"] == "vg-user-access-token" and c["value"]]
        if not auth_cookies:
            browser.close()
            raise RuntimeError("Login failed - no auth token received")

        save_cookies_from_playwright(context, cookie_file)

        session = requests.Session()
        for cookie in cookies:
            session.cookies.set(
                cookie["name"], cookie["value"],
                domain=cookie.get("domain", ""), path=cookie.get("path", "/"),
            )
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        })
        browser.close()
        logger.info("Login successful via Playwright")
        return session
