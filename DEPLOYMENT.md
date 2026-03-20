# WealthLens OSS — Production Deployment Guide

## Quick Start: Custom Domain + Public Access

### Step 1: Get a VPS ($7/mo)

Any provider works. Recommended for India-based users:

| Provider | Plan | RAM | Cost | Notes |
|----------|------|-----|------|-------|
| **Hetzner** (Ashburn) | CX22 | 4GB | €4.5/mo | Best value |
| **DigitalOcean** (Bangalore) | Basic | 2GB | $12/mo | Closest to India |
| **Railway.app** | Pro | Auto | $5/mo + usage | Zero-ops |
| **Render** | Starter | 512MB | $7/mo | Easy deploy |

For Indian users: Hetzner Ashburn or DigitalOcean Bangalore give ~100-200ms round-trip.

### Step 2: DNS + Free SSL via Cloudflare

1. Buy a domain (Namecheap, Porkbun — ~$10/year)
2. Sign up at [Cloudflare](https://cloudflare.com) (free tier)
3. Add your domain → point nameservers to Cloudflare
4. Add an **A record**: `@` → your server IP, proxied (orange cloud)
5. Add a **CNAME**: `www` → `yourdomain.com`, proxied

Cloudflare gives you:
- **Free SSL** (automatic, no certbot needed)
- **Global CDN** for static assets (SPA JS/CSS)
- **DDoS protection** (free tier handles most attacks)
- **Page load: 200ms → 30-50ms** globally

In Cloudflare SSL settings: set mode to **Full (strict)**.

### Step 3: Deploy

```bash
# SSH into your VPS
ssh root@your-server-ip

# Install Docker
curl -fsSL https://get.docker.com | sh

# Clone and configure
git clone https://github.com/your-org/wealthlens-oss.git
cd wealthlens-oss

# Generate secrets
cat > .env << EOF
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(48))")
ENCRYPTION_MASTER_SALT=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
DB_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(24))")
ALLOWED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
GOOGLE_CLIENT_ID=your-google-client-id.apps.googleusercontent.com
ANTHROPIC_API_KEY=sk-ant-xxxxx
PORT=80
EOF

# Launch production stack
docker compose -f docker-compose.prod.yml up -d

# Check health
curl http://localhost/api/health
```

### Step 4: Google OAuth Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
2. Create OAuth 2.0 Client ID → Web application
3. Authorized JavaScript origins: `https://yourdomain.com`
4. Authorized redirect URIs: `https://yourdomain.com/api/auth/google/callback`
5. Copy the Client ID → set as `GOOGLE_CLIENT_ID` in `.env`
6. Restart: `docker compose -f docker-compose.prod.yml restart app`

---

## Architecture: What Runs Where

```
Internet
  │
  ▼
Cloudflare (free CDN + SSL + DDoS protection)
  │
  ▼ (port 80/443)
┌─────────────────────────────────────────────────┐
│  Nginx                                          │
│  ├── Static assets (React SPA) → served directly │
│  ├── /api/auth/* → rate limit: 5/min per IP     │
│  ├── /api/mf|stock/* → rate limit: 10/sec       │
│  └── /api/* → rate limit: 30/sec → proxy to:    │
│                                                  │
│  FastAPI (4 Gunicorn workers)                   │
│  ├── JWT auth → decrypt DEK → process request   │
│  ├── Market data → check Redis cache first      │
│  └── Batch refresh → asyncio.gather (parallel)  │
│                                                  │
│  Redis (64MB, LRU eviction)                     │
│  ├── NAV cache: 5min TTL                        │
│  ├── Stock prices: 1min TTL                     │
│  └── FX rates: 2min TTL                         │
│                                                  │
│  PostgreSQL (tuned for 2GB RAM)                 │
│  └── All data AES-256-GCM encrypted             │
└─────────────────────────────────────────────────┘
```

---

## Capacity Planning

| Families | Workers | RAM | Redis | DB Connections | Cost |
|----------|---------|-----|-------|---------------|------|
| 1-50 | 2 | 512MB | In-memory | 10 | Free (Render) |
| 50-500 | 4 | 1GB | 64MB | 20 | $7-14/mo |
| 500-2000 | 4-8 | 2GB | 64MB | 50 | $14-28/mo |
| 2000+ | 8-16 | 4GB+ | 128MB | 100+ | $50+/mo |

### What limits scale:

1. **PBKDF2 on login** (~312ms, CPU-bound) — limits to ~13 logins/sec per worker
2. **External API calls** (MFAPI, Yahoo) — solved by Redis cache
3. **DB connections** — solved by SQLAlchemy connection pooling
4. **Static assets** — solved by Cloudflare CDN

### What does NOT limit scale:

- AES encryption/decryption: 2ms for 50 holdings + 200 transactions
- DB queries: <5ms for typical portfolio reads
- Memory: each family's decrypted data is ~50KB, held only during request

---

## Monitoring

```bash
# Check all services are running
docker compose -f docker-compose.prod.yml ps

# View logs
docker compose -f docker-compose.prod.yml logs -f app
docker compose -f docker-compose.prod.yml logs -f nginx

# Check Redis cache stats
docker compose -f docker-compose.prod.yml exec redis redis-cli info stats

# Check PostgreSQL connections
docker compose -f docker-compose.prod.yml exec db psql -U wealthlens -c "SELECT count(*) FROM pg_stat_activity;"

# Restart a single service
docker compose -f docker-compose.prod.yml restart app
```

---

## Backup

```bash
# Database backup (run daily via cron)
docker compose -f docker-compose.prod.yml exec db \
  pg_dump -U wealthlens wealthlens | gzip > backup_$(date +%Y%m%d).sql.gz

# Note: backups contain encrypted data — useless without user passwords
```

---

## Updates

```bash
cd wealthlens-oss
git pull origin main
docker compose -f docker-compose.prod.yml build app
docker compose -f docker-compose.prod.yml up -d app
```
