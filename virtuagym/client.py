import logging
import os
from datetime import date, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

from virtuagym.auth import load_cookies, check_session, login_with_playwright, login_with_keycloak, refresh_access_token, session_file_for_user
from virtuagym.models import GymClass, Booking, BookingResult, ClassState
from virtuagym.parser import parse_schedule_html

logger = logging.getLogger(__name__)

load_dotenv()


def _resolve_user_config(user: str | None) -> tuple[str, str, str]:
    """Resolve credentials for a user profile.

    Looks for VG_EMAIL_{USER} / VG_PASSWORD_{USER} in env,
    falls back to VG_EMAIL / VG_PASSWORD for the default user.

    Returns:
        (user_name, email, password)
    """
    if user:
        key = user.upper()
        email = os.getenv(f"VG_EMAIL_{key}", "")
        password = os.getenv(f"VG_PASSWORD_{key}", "")
        if email and password:
            return user, email, password
        raise ValueError(
            f"No credentials found for user '{user}'. "
            f"Set VG_EMAIL_{key} and VG_PASSWORD_{key} in .env"
        )
    # Default user
    email = os.getenv("VG_EMAIL", "")
    password = os.getenv("VG_PASSWORD", "")
    # Derive a name from the email for the session file
    name = email.split("@")[0] if email else "default"
    return name, email, password


class VirtuagymClient:
    """Client for interacting with Virtuagym's member-facing web portal.

    Supports multiple user profiles. Each user gets their own session file
    in storage/{username}.json.

    Args:
        user: User profile name (looks up VG_EMAIL_{USER}/VG_PASSWORD_{USER}).
              If None, uses VG_EMAIL/VG_PASSWORD from .env.
        gym_url: Gym portal URL. Defaults to VG_GYM_URL from .env.
        email: Override email (skip profile lookup).
        password: Override password (skip profile lookup).
    """

    def __init__(
        self,
        user: str | None = None,
        gym_url: str | None = None,
        email: str | None = None,
        password: str | None = None,
    ):
        self.base_url = (gym_url or os.getenv("VG_GYM_URL", "")).rstrip("/")

        if email and password:
            self.user = user or email.split("@")[0]
            self.email = email
            self.password = password
        else:
            self.user, self.email, self.password = _resolve_user_config(user)

        self._session_file = session_file_for_user(self.user)

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        })

        self._logged_in = False

    def login(self, headless: bool | None = None) -> bool:
        """Login to Virtuagym. Tries multiple auth methods in order.

        Auth cascade:
        1. Saved cookies (IP-bound server-side session)
        2. Old-style token refresh (extends existing session)
        3. Keycloak v3 Bearer token (works from any IP, no CAPTCHA)
        4. Playwright browser login (last resort, needs CAPTCHA)

        Args:
            headless: If True, use headless browser (may fail with CAPTCHA).
                     If False, opens visible browser for manual CAPTCHA solving.
                     If None (default), auto-detect based on DISPLAY env var.
        """
        if headless is None:
            headless = not os.environ.get("DISPLAY")

        domain = self.base_url.split('//')[1].split('/')[0]

        # Try loading saved session cookies
        if load_cookies(self.session, self._session_file):
            if check_session(self.session, self.base_url):
                logger.info("Resumed session for user '%s'", self.user)
                self._logged_in = True
                return True

            # Session expired — try refreshing the access token (no CAPTCHA)
            logger.info("Session expired for user '%s', trying token refresh...", self.user)
            if refresh_access_token(self.session, domain, self._session_file):
                if check_session(self.session, self.base_url):
                    logger.info("Session restored via token refresh for user '%s'", self.user)
                    self._logged_in = True
                    return True

        # Keycloak v3 Bearer auth (works from any IP, no CAPTCHA needed).
        # The web portal accepts Authorization: Bearer with a v3 token.
        logger.info("Trying Keycloak login for user '%s'...", self.user)
        if login_with_keycloak(self.session, self.email, self.password, domain, self._session_file):
            # Set the v3 token as a Bearer header for all future requests
            v3_token = None
            for c in self.session.cookies:
                if c.name == "vg-user-access-token-v3" and c.value:
                    v3_token = c.value
                    break
            if v3_token:
                self.session.headers["Authorization"] = f"Bearer {v3_token}"
                if check_session(self.session, self.base_url):
                    logger.info("Session established via Keycloak Bearer for user '%s'", self.user)
                    self._logged_in = True
                    return True
            logger.info("Keycloak v3 tokens not sufficient for web session")

        # Last resort: Playwright browser login
        logger.info("Falling back to Playwright login for user '%s'", self.user)
        self.session = login_with_playwright(
            self.base_url, self.email, self.password,
            cookie_file=self._session_file, headless=headless,
        )
        self._logged_in = True
        return True

    def _ensure_logged_in(self):
        if not self._logged_in:
            raise RuntimeError("Not logged in. Call login() first.")

    def get_schedule(
        self,
        date_from: str | date | None = None,
        date_to: str | date | None = None,
        event_type: int = 2,
    ) -> list[GymClass]:
        """Get the class schedule for a date range.

        Args:
            date_from: Start date (YYYY-MM-DD or date object). Defaults to today.
            date_to: End date (YYYY-MM-DD or date object). Defaults to 7 days from start.
            event_type: Schedule type. 2=Actividades Dirigidas, 3=Zona Fitness, 5=Piscina.

        Returns:
            List of GymClass objects sorted by date and time.
        """
        self._ensure_logged_in()

        if date_from is None:
            date_from = date.today()
        elif isinstance(date_from, str):
            date_from = date.fromisoformat(date_from)

        if date_to is None:
            date_to = date_from + timedelta(days=7)
        elif isinstance(date_to, str):
            date_to = date.fromisoformat(date_to)

        all_classes = []
        seen_weeks = set()

        # Iterate day-by-day to find all weeks that overlap the date range.
        # Each week page is identified by its Saturday (Mon-Sun week).
        current = date_from
        while current <= date_to:
            weekday = current.weekday()  # Mon=0 ... Sun=6
            if weekday == 6:  # Sunday belongs to the previous Saturday's week
                saturday = current - timedelta(days=1)
            else:
                saturday = current + timedelta(days=(5 - weekday) % 7)
            week_key = saturday.isoformat()

            if week_key not in seen_weeks:
                seen_weeks.add(week_key)
                week_classes = self._fetch_week(saturday, event_type)
                all_classes.extend(week_classes)

            # Jump to next Monday (start of next week)
            days_to_next_monday = (7 - weekday) % 7 or 7
            current += timedelta(days=days_to_next_monday)

        # Filter to the requested date range
        from_str = date_from.isoformat()
        to_str = date_to.isoformat()
        filtered = [c for c in all_classes if from_str <= c.date <= to_str]
        filtered.sort(key=lambda c: (c.date, c.time_start))

        return filtered

    def _fetch_week(self, saturday: date, event_type: int) -> list[GymClass]:
        """Fetch and parse one week of schedule."""
        url = f"{self.base_url}/classes/week/{saturday.isoformat()}"
        params = {"event_type": event_type}

        logger.debug("Fetching schedule: %s", url)
        resp = self.session.get(url, params=params, timeout=15)
        resp.raise_for_status()

        return parse_schedule_html(resp.text)

    def get_my_bookings(
        self,
        date_from: str | date | None = None,
        date_to: str | date | None = None,
    ) -> list[Booking]:
        """Get current user's bookings within a date range.

        This filters the schedule for classes with state=JOINED.

        Args:
            date_from: Start date. Defaults to today.
            date_to: End date. Defaults to 14 days from start.

        Returns:
            List of Booking objects.
        """
        if date_from is None:
            date_from = date.today()
        if date_to is None:
            if isinstance(date_from, str):
                date_from = date.fromisoformat(date_from)
            date_to = date_from + timedelta(days=14)

        schedule = self.get_schedule(date_from, date_to)
        bookings = []
        for c in schedule:
            if c.state == ClassState.JOINED:
                bookings.append(Booking(
                    event_id=c.event_id,
                    class_name=c.name,
                    date=c.date,
                    time_start=c.time_start,
                    time_end=c.time_end,
                    instructor=c.instructor,
                    capacity_current=c.capacity_current,
                    capacity_max=c.capacity_max,
                ))
        return bookings

    def book_class(self, event_id: str, recurring: bool = False) -> BookingResult:
        """Book a class by its event ID.

        Args:
            event_id: The event ID (format: number-hex-number).
            recurring: If True, book all future occurrences too.

        Returns:
            BookingResult with success status and message.
        """
        self._ensure_logged_in()

        url = f"{self.base_url}/classes/class/{event_id}"
        data = {
            "action": "reserve_class",
            "book_recurring": "1" if recurring else "",
            "send_email": "1",
            "attendees": "0",
        }

        logger.info("Booking class %s (recurring=%s)", event_id, recurring)
        resp = self.session.post(url, data=data, params={"event_type": 2}, timeout=15)

        if resp.status_code == 200:
            text = resp.text.lower()
            if "error" in text or "demasiado" in text or "tarde" in text or "temprano" in text:
                return BookingResult(success=False, message=resp.text.strip(), event_id=event_id)
            return BookingResult(success=True, message="Booking confirmed", event_id=event_id)
        else:
            return BookingResult(
                success=False,
                message=f"HTTP {resp.status_code}: {resp.text[:200]}",
                event_id=event_id,
            )

    def cancel_booking(self, event_id: str) -> BookingResult:
        """Cancel a booking by its event ID.

        Args:
            event_id: The event ID to cancel.

        Returns:
            BookingResult with success status and message.
        """
        self._ensure_logged_in()

        url = f"{self.base_url}/classes/class/{event_id}"
        data = {
            "action": "delete_participant",
        }

        logger.info("Cancelling booking %s", event_id)
        resp = self.session.post(url, data=data, params={"event_type": 2}, timeout=15)

        if resp.status_code == 200:
            text = resp.text.lower()
            if "error" in text:
                return BookingResult(success=False, message=resp.text.strip(), event_id=event_id)
            return BookingResult(success=True, message="Booking cancelled", event_id=event_id)
        else:
            return BookingResult(
                success=False,
                message=f"HTTP {resp.status_code}: {resp.text[:200]}",
                event_id=event_id,
            )
