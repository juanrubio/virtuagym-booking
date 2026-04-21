# Contributing

Thanks for considering a contribution.

## Before you open a PR

- Keep examples generic and privacy-safe.
- Never commit real credentials, session cookies, personal account data, or captured traffic.
- Prefer small, focused pull requests.
- Include reproduction steps for bugs.

## Development setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
```

Fill in `.env` with your own test account.

## Scope

Good contributions:
- parser hardening
- auth reliability improvements
- CLI ergonomics
- docs improvements
- tests

Please avoid PRs that add private operator workflows, personal deployment instructions, or account-specific data.

## Style

- Keep dependencies minimal.
- Prefer readable code over clever code.
- Preserve backwards compatibility where practical.
