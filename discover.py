#!/usr/bin/env python3
"""
Virtuagym API Discovery Script

Logs into the Virtuagym web portal and captures all network traffic
to reverse-engineer the internal API endpoints for schedule and booking.

Usage:
    python discover.py

The script will:
1. Open the login page in a visible browser
2. Auto-fill credentials (you may need to solve CAPTCHA manually)
3. After login, navigate to schedule and capture API calls
4. Save all captured traffic to discovery/captured-traffic.json
5. Save session cookies to storage/session.json
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

BASE_URL = os.getenv("VG_GYM_URL", "https://your-gym.virtuagym.com")
EMAIL = os.getenv("VG_EMAIL", "")
PASSWORD = os.getenv("VG_PASSWORD", "")

PROJECT_DIR = Path(__file__).parent
TRAFFIC_FILE = PROJECT_DIR / "discovery" / "captured-traffic.json"
SESSION_FILE = PROJECT_DIR / "storage" / "session.json"

captured_requests = []


def should_capture(url: str) -> bool:
    """Only capture API/AJAX calls, not static assets."""
    parsed = urlparse(url)
    skip_extensions = {".js", ".css", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".woff", ".woff2", ".ttf", ".ico"}
    if any(parsed.path.endswith(ext) for ext in skip_extensions):
        return False
    skip_domains = {"google", "gstatic", "googleapis", "facebook", "doubleclick", "analytics"}
    if any(d in parsed.hostname for d in skip_domains):
        return False
    return True


def on_request(request):
    if not should_capture(request.url):
        return
    entry = {
        "timestamp": datetime.now().isoformat(),
        "method": request.method,
        "url": request.url,
        "headers": dict(request.headers),
        "post_data": request.post_data,
        "resource_type": request.resource_type,
    }
    captured_requests.append(entry)
    print(f"  -> {request.method} {request.url[:120]}")


def on_response(response):
    if not should_capture(response.url):
        return
    # Find matching request and add response data
    for entry in reversed(captured_requests):
        if entry["url"] == response.url and "status" not in entry:
            entry["status"] = response.status
            entry["response_headers"] = dict(response.headers)
            content_type = response.headers.get("content-type", "")
            if "json" in content_type or "text" in content_type:
                try:
                    entry["response_body"] = response.text()
                except Exception:
                    entry["response_body"] = "<could not read>"
            break


def save_traffic():
    TRAFFIC_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(TRAFFIC_FILE, "w") as f:
        json.dump(captured_requests, f, indent=2, default=str)
    print(f"\nSaved {len(captured_requests)} requests to {TRAFFIC_FILE}")


def main():
    print(f"Virtuagym API Discovery")
    print(f"Target: {BASE_URL}")
    print(f"Account: {EMAIL}")
    print()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        page = context.new_page()

        # Hook network traffic
        page.on("request", on_request)
        page.on("response", on_response)

        # Step 1: Login
        print("=== Step 1: Login ===")
        page.goto(f"{BASE_URL}/signin")
        page.wait_for_load_state("networkidle")

        page.fill('input[name="username"]', EMAIL)
        page.fill('input[name="password"]', PASSWORD)

        print("Credentials filled. Solve CAPTCHA if present, then press Enter here...")
        input("Press Enter after CAPTCHA is solved (or if there's no CAPTCHA)...")

        # Click login
        page.click('button:has-text("Login"), input[type="submit"]')
        page.wait_for_load_state("networkidle")
        time.sleep(2)

        if "/signin" in page.url:
            print("WARNING: Still on login page. Login may have failed.")
            print(f"Current URL: {page.url}")
            input("Try solving CAPTCHA and clicking Login manually. Press Enter when logged in...")

        print(f"Logged in! Current URL: {page.url}")
        print()

        # Save session
        context.storage_state(path=str(SESSION_FILE))
        print(f"Session saved to {SESSION_FILE}")
        print()

        # Step 2: Explore the schedule
        print("=== Step 2: Navigate to Schedule ===")
        print("Looking for schedule/calendar link...")

        # Try common schedule URLs
        schedule_urls = [
            f"{BASE_URL}/classes",
            f"{BASE_URL}/schedule",
            f"{BASE_URL}/club_portal/schedule",
            f"{BASE_URL}/timetable",
        ]

        # First, let's see what navigation options exist
        print("Capturing page links...")
        links = page.evaluate("""
            () => Array.from(document.querySelectorAll('a')).map(a => ({
                href: a.href,
                text: a.textContent.trim().substring(0, 50)
            })).filter(l => l.href && l.text)
        """)
        print("Available links:")
        for link in links:
            if any(kw in link["text"].lower() or kw in link["href"].lower()
                   for kw in ["class", "schedule", "horario", "actividad", "reserv", "book", "agenda"]):
                print(f"  * {link['text']} -> {link['href']}")

        print()
        print("Navigate to the class schedule/booking page in the browser.")
        print("You can also try these URLs:")
        for url in schedule_urls:
            print(f"  - {url}")
        input("Press Enter when you're on the schedule page...")

        print(f"Current URL: {page.url}")
        page.wait_for_load_state("networkidle")
        time.sleep(2)
        print()

        # Step 3: Browse classes
        print("=== Step 3: Browse Classes ===")
        print("Click around the schedule - view different days, click on classes.")
        print("The script is capturing all network requests in the background.")
        input("Press Enter when you've browsed enough of the schedule...")
        print()

        # Step 4: Book a class
        print("=== Step 4: Book a Class ===")
        print("Try booking a class in the browser (we'll cancel it after).")
        input("Press Enter after booking a class (or skip if not possible)...")
        print()

        # Step 5: Check bookings
        print("=== Step 5: Check Bookings ===")
        print("Navigate to the bookings/reservations page.")
        input("Press Enter when you're on the bookings page...")
        print()

        # Step 6: Cancel the test booking
        print("=== Step 6: Cancel Booking ===")
        print("Cancel the test booking if you made one.")
        input("Press Enter after cancelling (or skip)...")
        print()

        # Step 7: Any additional exploration
        print("=== Step 7: Free Exploration ===")
        print("Explore any other pages you want to capture API calls from.")
        input("Press Enter when done exploring...")

        # Save everything
        save_traffic()
        context.storage_state(path=str(SESSION_FILE))
        print(f"Session updated at {SESSION_FILE}")

        # Summary
        print("\n=== Summary ===")
        api_calls = [r for r in captured_requests if r.get("resource_type") in ("xhr", "fetch")]
        print(f"Total captured requests: {len(captured_requests)}")
        print(f"XHR/Fetch API calls: {len(api_calls)}")
        print("\nAPI endpoints found:")
        seen = set()
        for r in api_calls:
            key = f"{r['method']} {urlparse(r['url']).path}"
            if key not in seen:
                seen.add(key)
                print(f"  {key} (status: {r.get('status', '?')})")

        browser.close()

    print(f"\nDone! Review captured traffic at: {TRAFFIC_FILE}")


if __name__ == "__main__":
    main()
