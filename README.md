# Virtuagym Booking

Unofficial Python library and CLI for reading class schedules and booking classes through the member-facing Virtuagym web portal.

*This project is not affiliated with, endorsed by, or maintained by Virtuagym.*

## Why this exists

Virtuagym exposes member functionality through its web app, but many useful flows are not packaged as a simple developer-facing client. This project wraps the member portal used by end users and provides:

- a Python API
- a command line interface
- reusable auth handling for browser-backed and headless environments

## Status

This is a reverse-engineered integration. Expect breakage when Virtuagym changes its frontend or auth flows.

## Safety and risk warnings

Before using this project, understand the tradeoffs:

- It is an unofficial integration.
- It may stop working without notice.
- Browser automation and repeated login attempts may trigger CAPTCHA or account friction.
- Automated access to Virtuagym may violate their Terms of Service.
- You are solely responsible for ensuring your use complies with applicable terms and local laws.
- Never commit credentials, cookies, or captured traffic from a real account.
- Raw captures may include third-party personal data and must be sanitized before sharing.

## Features

- schedule lookup for date ranges
- booking and cancellation by event ID
- multiple account profiles via environment variables
- saved session reuse
- refresh-token recovery when possible
- headless-friendly auth fallback support

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
```

Then edit `.env`:

```env
VG_GYM_URL=https://your-gym.virtuagym.com
VG_EMAIL=your@email.com
VG_PASSWORD=your-password

# Optional named profiles
# VG_EMAIL_WORK=another@email.com
# VG_PASSWORD_WORK=another-password
```

## CLI usage

```bash
# Show this week's schedule
python cli.py schedule

# Show schedule for a date range
python cli.py schedule --from 2026-02-23 --to 2026-02-27

# Show schedule with event IDs
python cli.py -v schedule

# Show current bookings
python cli.py bookings

# Book a class by event ID
python cli.py book <event_id>

# Cancel a booking
python cli.py cancel <event_id>

# Use a named user profile
python cli.py --user work schedule
```

## Python API

```python
from virtuagym import VirtuagymClient

client = VirtuagymClient()
client.login()

classes = client.get_schedule("2026-02-23", "2026-02-27")
for c in classes:
    print(c)

bookings = client.get_my_bookings()
print(bookings)
```

## How authentication works

The client tries several strategies in order:

1. saved session cookies
2. token refresh for older session flows
3. Keycloak token login for newer flows
4. Playwright browser login as a last resort

This order is practical, not guaranteed. Different gyms and deployments may behave differently.

## Project structure

```text
virtuagym/
  __init__.py
  client.py
  auth.py
  models.py
  parser.py
cli.py
requirements.txt
discover.py
```

## Developer notes

- Use `discover.py` only with your own account and a throwaway or otherwise safe environment.
- Captured traffic may include third-party personal data, analytics identifiers, and session material. Sanitize aggressively before sharing anything.
- If you want to contribute support for more portals or event types, open an issue first.

## Contributing and security

- See [CONTRIBUTING.md](CONTRIBUTING.md) for development workflow and repo hygiene rules.
- See [SECURITY.md](SECURITY.md) for vulnerability reporting guidance.

## License

MIT. See [LICENSE](LICENSE).
