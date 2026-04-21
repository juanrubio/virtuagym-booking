# Security Policy

## Supported versions

Security fixes are applied to the latest development state of this repository.

## Reporting a vulnerability

Please do not open public issues for security problems, leaked credentials, or account-specific data.

- Use GitHub's private vulnerability reporting flow for this repository if it is available.
- Otherwise, contact the maintainer privately through GitHub.
- Never include active session tokens, personal identifiers, or raw captured traffic in a report.

## Sensitive data

This project can store browser-derived session state locally in `storage/`. Anyone with access to valid session files or tokens may be able to act on the associated account.

If you believe a token or other account data has been exposed:

1. Change the account password or sign out and sign back in through the Virtuagym web portal.
2. Remove any exposed local files such as `.env` and `storage/*.json`.
3. Report the incident privately with sanitized reproduction steps.
