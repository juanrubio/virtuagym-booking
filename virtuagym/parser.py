import re
import logging
from datetime import datetime

from bs4 import BeautifulSoup

from virtuagym.models import GymClass, ClassState

logger = logging.getLogger(__name__)

# Map CSS class to ClassState
STATE_MAP = {
    "class_available": ClassState.AVAILABLE,
    "class_joined": ClassState.JOINED,
    "class_full": ClassState.FULL,
    "class_past": ClassState.PAST,
}

# Event ID pattern: number-hex-number
EVENT_ID_RE = re.compile(r"^\d+-[a-f0-9]+-\d+$")

# Date from CSS class: internal-event-day-DD-MM-YYYY
DATE_RE = re.compile(r"internal-event-day-(\d{2})-(\d{2})-(\d{4})")

# Time range: HH:MM - HH:MM
TIME_RE = re.compile(r"(\d{2}:\d{2})\s*-\s*(\d{2}:\d{2})")

# Capacity: N / M
CAPACITY_RE = re.compile(r"(\d+)\s*/\s*(\d+)")

DAY_NAMES_ES = {
    0: "Lunes", 1: "Martes", 2: "Miércoles", 3: "Jueves",
    4: "Viernes", 5: "Sábado", 6: "Domingo",
}


def parse_schedule_html(html: str) -> list[GymClass]:
    """Parse the schedule page HTML and extract all classes."""
    soup = BeautifulSoup(html, "html.parser")
    classes = []

    # Find all event divs with the internal-event-day pattern
    for div in soup.find_all("div", class_=DATE_RE):
        event_id = div.get("id", "")
        if not EVENT_ID_RE.match(event_id):
            continue

        css_classes = div.get("class", [])

        # Determine state
        state = ClassState.BOOKABLE  # default
        for css_class, class_state in STATE_MAP.items():
            if css_class in css_classes:
                state = class_state
                break

        # Extract date from CSS class
        date_match = DATE_RE.search(" ".join(css_classes))
        if not date_match:
            continue
        day, month, year = date_match.groups()
        date_str = f"{year}-{month}-{day}"

        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            day_of_week = DAY_NAMES_ES.get(dt.weekday(), "")
        except ValueError:
            day_of_week = ""

        # Extract using the actual HTML structure:
        # <span class="classname">WOD</span>
        # <span class="time">07:20 - 08:00</span>
        # <span class="instructor"><i>LUIS VIUDEZ</i></span>
        name_el = div.find("span", class_="classname")
        time_el = div.find("span", class_="time")
        instructor_el = div.find("span", class_="instructor")

        name = name_el.get_text(strip=True) if name_el else ""
        time_text = time_el.get_text(strip=True) if time_el else ""
        instructor = instructor_el.get_text(strip=True) if instructor_el else ""

        # Skip empty placeholder divs (class_available with no content)
        if not name and not time_text:
            continue

        # Parse time range
        time_match = TIME_RE.search(time_text)
        time_start = time_match.group(1) if time_match else ""
        time_end = time_match.group(2) if time_match else ""

        # Extract onclick URL for the modal (contains the class detail URL)
        onclick = div.get("onclick", "")

        classes.append(GymClass(
            event_id=event_id,
            name=name,
            date=date_str,
            time_start=time_start,
            time_end=time_end,
            instructor=instructor,
            state=state,
            day_of_week=day_of_week,
        ))

    # Sort by date and time
    classes.sort(key=lambda c: (c.date, c.time_start))
    return classes


def parse_class_detail_html(html: str) -> dict:
    """Parse the class detail dialog HTML for capacity, room, cost info."""
    soup = BeautifulSoup(html, "html.parser")
    info = {}

    # Capacity: "N / M"
    cap_match = CAPACITY_RE.search(html)
    if cap_match:
        info["capacity_current"] = int(cap_match.group(1))
        info["capacity_max"] = int(cap_match.group(2))

    # Room name (after room icon)
    room_el = soup.find(string=re.compile(r"^[A-Z]+$"))
    if room_el:
        info["room"] = room_el.strip()

    # Cost
    cost_el = soup.find(string=re.compile(r"Gym Creditos"))
    if cost_el:
        info["cost"] = cost_el.strip()

    return info
