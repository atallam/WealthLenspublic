# WealthLens OSS

**Zero-knowledge family wealth management + budgeting — your data stays yours.**

Free, open-source, multi-family platform with end-to-end encryption (AES-256-GCM). The operator cannot see any family's financial data.

## Features

**Wealth Management** — 8 asset types (FD, PPF, EPF, MF, Indian Stocks, Indian ETFs, US Stocks, Real Estate), family member tracking, goals with progress, allocation alerts, XIRR calculator, SIP bulk import, AI advisor (Claude), encrypted artifact storage.

**Budgeting** — Multi-bank CSV import (HDFC, SBI, ICICI, Axis, Kotak, generic), auto-categorization (100+ Indian merchant rules), AI re-categorization, 17 default categories, monthly budget buckets, pie/bar charts, 1-year import history retention.

**Auth** — Email/password or Google OAuth. Google users set a vault PIN for encryption. Dual-auth: Google handles identity, PIN handles cryptography.

**Market Data (4-source resilience)** — MF NAVs: MFAPI → AMFI daily → AMFI historical → mftool. Stocks: Twelve Data → Yahoo. FX: exchangerate-api → Twelve Data → Yahoo → hardcoded.

**Infrastructure** — FastAPI (49 endpoints), React SPA (dark theme), Redis caching, Nginx (rate limiting + static), Docker Compose (one-command deploy), connection pooling, parallel batch refresh.

## Quick Start

```bash
# Local dev
chmod +x setup.sh && ./setup.sh
source venv/bin/activate && uvicorn app.main:app --reload  # Terminal 1
cd frontend && npm run dev                                  # Terminal 2

# Docker production
docker compose -f docker-compose.prod.yml up -d
```

## 49 API Endpoints

Auth (8): register, login, Google OAuth, vault setup/unlock, change password, me, Google client ID
Holdings (4): list, create, update, delete
Transactions (3): add, list, delete
Portfolio (2): get, save (members, goals, alerts)
Market (8): MF search (2), MF NAV, SIP NAVs, manual NAV, stock info, ETF search, FX rate
Prices (2): batch refresh, source status
Budget (17): import, list imports, delete import, list/update/delete transactions, manual transaction, categories CRUD, buckets CRUD, monthly summary, AI categorization
AI (1): chat with portfolio context
Artifacts (3): upload, download, delete
Health (1): status + pool stats

## Security

PBKDF2-SHA256 (600K rounds) → vault key → AES-256-GCM encrypted DEK → field-level encryption on all sensitive data. DB stores only ciphertext. Nginx rate limits: 5 logins/min, 30 API/sec per IP.

## Environment Variables

DATABASE_URL, SECRET_KEY, ENCRYPTION_MASTER_SALT (required)
ALLOWED_ORIGINS, GOOGLE_CLIENT_ID, ANTHROPIC_API_KEY, TWELVE_DATA_API_KEY, REDIS_URL, DB_POOL_SIZE, DB_MAX_OVERFLOW, PORT (optional)

## License

MIT
