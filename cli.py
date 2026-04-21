#!/usr/bin/env python3
"""Virtuagym Booking CLI - Check schedules and book classes."""

import argparse
import logging
import sys
from datetime import date, timedelta

from virtuagym import VirtuagymClient


def cmd_schedule(client: VirtuagymClient, args):
    date_from = args.date_from or date.today().isoformat()
    date_to = args.date_to or (date.fromisoformat(date_from) + timedelta(days=6)).isoformat()

    classes = client.get_schedule(date_from, date_to)
    if not classes:
        print("No classes found for this period.")
        return

    current_date = None
    for c in classes:
        if c.date != current_date:
            current_date = c.date
            print(f"\n--- {c.day_of_week} {c.date} ---")
        print(f"  {c.time_start}-{c.time_end}  {c.name:<30} {c.instructor:<30} {_state_label(c)}")
        if args.verbose and c.event_id:
            print(f"              ID: {c.event_id}")


def cmd_bookings(client: VirtuagymClient, args):
    bookings = client.get_my_bookings()
    if not bookings:
        print("No current bookings found.")
        return

    print("Current bookings:")
    for b in bookings:
        print(f"  {b.date} {b.time_start}-{b.time_end}  {b.class_name} - {b.instructor}")
        if args.verbose:
            print(f"              ID: {b.event_id}")


def cmd_book(client: VirtuagymClient, args):
    result = client.book_class(args.event_id, recurring=args.recurring)
    if result.success:
        print(f"Booked! {result.message}")
    else:
        print(f"Failed: {result.message}", file=sys.stderr)
        sys.exit(1)


def cmd_cancel(client: VirtuagymClient, args):
    result = client.cancel_booking(args.event_id)
    if result.success:
        print(f"Cancelled! {result.message}")
    else:
        print(f"Failed: {result.message}", file=sys.stderr)
        sys.exit(1)


def _state_label(c) -> str:
    from virtuagym.models import ClassState
    labels = {
        ClassState.JOINED: "[BOOKED]",
        ClassState.FULL: "[FULL]",
        ClassState.PAST: "[PAST]",
        ClassState.AVAILABLE: "",
        ClassState.BOOKABLE: "",
    }
    return labels.get(c.state, "")


def main():
    parser = argparse.ArgumentParser(
        prog="vgym",
        description="Virtuagym class booking CLI",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Show event IDs and extra info")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument(
        "-u", "--user",
        help="User profile name (uses VG_EMAIL_{USER}/VG_PASSWORD_{USER} from .env). "
             "Omit to use default VG_EMAIL/VG_PASSWORD.",
    )
    parser.add_argument(
        "--headless", action="store_true", default=None,
        help="Use headless browser for login (for servers without a display). "
             "Default: auto-detect based on DISPLAY env var.",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # schedule
    p_sched = sub.add_parser("schedule", aliases=["s"], help="Show class schedule")
    p_sched.add_argument("--from", dest="date_from", help="Start date (YYYY-MM-DD, default: today)")
    p_sched.add_argument("--to", dest="date_to", help="End date (YYYY-MM-DD, default: +7 days)")
    p_sched.set_defaults(func=cmd_schedule)

    # bookings
    p_book = sub.add_parser("bookings", aliases=["b"], help="Show current bookings")
    p_book.set_defaults(func=cmd_bookings)

    # book
    p_do = sub.add_parser("book", help="Book a class by event ID")
    p_do.add_argument("event_id", help="Event ID to book")
    p_do.add_argument("--recurring", action="store_true", help="Book all future occurrences")
    p_do.set_defaults(func=cmd_book)

    # cancel
    p_cancel = sub.add_parser("cancel", help="Cancel a booking by event ID")
    p_cancel.add_argument("event_id", help="Event ID to cancel")
    p_cancel.set_defaults(func=cmd_cancel)

    args = parser.parse_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.WARNING)

    client = VirtuagymClient(user=args.user)
    client.login(headless=args.headless)
    args.func(client, args)


if __name__ == "__main__":
    main()
