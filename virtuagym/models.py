from dataclasses import dataclass
from enum import Enum


class ClassState(Enum):
    AVAILABLE = "available"
    JOINED = "joined"
    FULL = "full"
    PAST = "past"
    BOOKABLE = "bookable"  # within booking window, not full


@dataclass
class GymClass:
    event_id: str
    name: str
    date: str  # YYYY-MM-DD
    time_start: str  # HH:MM
    time_end: str  # HH:MM
    instructor: str
    state: ClassState
    capacity_current: int | None = None
    capacity_max: int | None = None
    room: str | None = None
    cost: str | None = None
    day_of_week: str | None = None

    @property
    def is_bookable(self) -> bool:
        return self.state in (ClassState.AVAILABLE, ClassState.BOOKABLE)

    @property
    def is_booked(self) -> bool:
        return self.state == ClassState.JOINED

    def __str__(self) -> str:
        status = ""
        if self.state == ClassState.JOINED:
            status = " [BOOKED]"
        elif self.state == ClassState.FULL:
            status = " [FULL]"
        elif self.state == ClassState.PAST:
            status = " [PAST]"
        cap = ""
        if self.capacity_current is not None and self.capacity_max is not None:
            cap = f" ({self.capacity_current}/{self.capacity_max})"
        return f"{self.date} {self.time_start}-{self.time_end} {self.name} - {self.instructor}{cap}{status}"


@dataclass
class Booking:
    event_id: str
    class_name: str
    date: str
    time_start: str
    time_end: str
    instructor: str
    capacity_current: int | None = None
    capacity_max: int | None = None

    def __str__(self) -> str:
        return f"{self.date} {self.time_start}-{self.time_end} {self.class_name} - {self.instructor}"


@dataclass
class BookingResult:
    success: bool
    message: str
    event_id: str | None = None
