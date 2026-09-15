# Insight MVP

A deployable Python + SQL MVP for neutral tenant-landlord repair documentation and workflow tracking.


[![LICENSE](https://img.shields.io/badge/License-All%20Rights%20Reserved-red.svg)](LICENSE)
[![Usage](https://img.shields.io/badge/Usage-Permission%20Required-orange.svg)](LICENSE)
[![Modification](https://img.shields.io/badge/Modification-Not%20Allowed-critical.svg)](LICENSE)
[![Commercial](https://img.shields.io/badge/Commercial-Permission%20Required-orange.svg)](LICENSE)

## Included
- Tenant/landlord registration and login
- Linked property records
- Tenant repair requests with configurable severity deadlines
- Photo/PDF evidence uploads (JPG/PNG/WebP/PDF, max 15 MB)
- Server upload timestamps and SHA-256 evidence hashes
- Optional browser-provided latitude/longitude metadata
- Shared case view, completion status, and audit trail
- Counsel-replaceable jurisdiction ruleset JSON
- Neutral notice generation and downloadable PDF
- Payment/escrow provider interface with **demo-only ledger enabled by default**
- SQLite local mode and PostgreSQL Docker deployment

## Critical compliance boundary
This repository intentionally does **not** accept, custody, escrow, or transfer real rent money. Escrow is a regulated/restricted financial activity in many contexts and payment processors may require approval. Before enabling real funds, obtain jurisdiction-specific legal advice and integrate an approved bank/escrow/payment partner under a written compliance design.

Likewise, the bundled `demo_us_general.json` is not law. It only demonstrates workflow deadlines. Production deployments must use attorney-reviewed jurisdiction packs, versioning, effective dates, citations, and change monitoring.

## Run locally
```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```
Open `http://127.0.0.1:8000`.

Create one tenant account and one landlord account, then link a property. The tenant can open a repair case.

## Docker/PostgreSQL
```bash
docker compose up --build
```
Then open `http://127.0.0.1:8000`.

## Production hardening checklist
1. Put the app behind TLS and set session cookies `https_only=True`.
2. Replace session-only auth with verified email, password reset, MFA options, login throttling, and CSRF protection.
3. Store evidence in immutable/versioned object storage (for example S3 Object Lock or equivalent), not a local disk.
4. Add malware scanning, image decompression safeguards, signed download URLs, retention/deletion rules, and backup/restore procedures.
5. Do not call GPS/EXIF data “proof”; record provenance and preserve original bytes/hash.
6. Add organization/property invitations instead of selecting users from a global list.
7. Add privacy policy, terms, DPA/subprocessors, incident response, and jurisdiction-specific consent/recording rules.
8. Have housing counsel create and approve each legal ruleset and notice template; store statutory citations, effective dates, and reviewer approvals.
9. If adding an LLM/RAG layer, make statute text the source of record, show citations, prevent unsupported output, retain the source/version used, and require human confirmation before sending notices.
10. Integrate real rent funds only after regulatory analysis and provider approval. Use provider webhooks, idempotency keys, reconciliation, KYC/KYB, sanctions checks where applicable, dispute/refund handling, and double-entry accounting.
11. Add background jobs for reminders/deadlines and a transactional email/SMS provider with delivery logs.
12. Add Alembic migrations, structured logging, monitoring, security headers, dependency scanning, and continuous tests.

## Suggested commercial architecture
- Web/API: FastAPI
- DB: PostgreSQL
- Worker/queue: Redis + Celery/RQ/Arq
- Evidence: S3-compatible object storage with retention controls
- Legal knowledge: versioned jurisdiction pack + optional RAG index
- PDF: ReportLab
- Payments: approved external escrow/banking partner through `services/payments.py`

## License
📄 **[Read the Full Legal Terms → LICENSE](LICENSE)**
