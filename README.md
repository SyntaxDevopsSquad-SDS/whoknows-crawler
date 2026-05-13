# whoknows-crawler

Automated crawler and simulation tool for [WhoKnows](https://syntax-reborndev.com) – uses Playwright to test endpoints, user flows and load scenarios as a real browser would.

## What it does

- **HTTP bots** – continuously hits `/health`, `/api/search`, `/metrics` and `/about`
- **DB bot** – pings PostgreSQL directly via asyncpg
- **Normal user bots (10)** – login → search 3 times with realistic pauses → logout
- **Heavy user bots (5)** – login → search 10 times rapidly → logout
- **Session bots (5)** – login → logout immediately, stressing session handling
- **Response validation** – verifies that `/api/search` returns valid JSON with a `search_results` key
- **Live report** – prints uptime, latency and error breakdown every 15 seconds

## Prerequisites

- Python 3.11+
- Bot users seeded in the WhoKnows database (see below)

## Installation

```bash
git clone https://github.com/SyntaxDevopsSquad-SDS/whoknows-crawler.git
cd whoknows-crawler
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

## Configuration

```bash
cp env.example .env
```

Fill in `.env`:

```env
BASE_URL=https://syntax-reborndev.com
BOT_PASSWORD=Simulation2026!
DB_DSN=                          # leave empty for prod
REPORT_EVERY_S=15
NORMAL_BOTS=10
HEAVY_BOTS=5
SESSION_BOTS=5
```

## Seed bot users

Run once against the target database:

```bash
# Dev
docker exec -i whoknows-postgres-1 psql -U whoknows -d whoknows -f - < ../devops-syntaxsquad/tools/endpoint-sim/users.seed.sql

# Prod – via SSH tunnel
ssh -L 5432:localhost:5432 user@syntax-reborndev.com
psql postgres://whoknows:PASSWORD@localhost:5432/whoknows -f users.seed.sql
```

## Run

```bash
# Against prod
python crawler.py

# Against local dev
BASE_URL=http://localhost:8080 python crawler.py
```

Stop with `Ctrl+C`.

## Report output

```
╔══════════════════════════════════════════════════════╗
║  📊 Rapport – 14:32:05                               ║
╠══════════════════════════════════════════════════════╣
║  🟢 HTTP    │ OK:25    Fejl:0    Uptime:100.0% Lat:  7.1 ms ║
║  🟢 DB      │ OK:2     Fejl:0    Uptime:100.0% Lat:  1.9 ms ║
║  👤 Login   │ OK:40    Fejl:0    Uptime:100.0%              ║
║  🔍 Søgning │ OK:155   Fejl:0    Uptime:100.0% (inv.JSON:0 mangl.key:0) ║
║  🔓 Session │ OK:35    Fejl:0    Uptime:100.0%              ║
╚══════════════════════════════════════════════════════╝
```

## Related

- [devops-syntaxsquad](https://github.com/SyntaxDevopsSquad-SDS/devops-syntaxsquad) – the application being tested
- [Live app](https://syntax-reborndev.com)
- [Monitoring](https://monitor.syntax-reborndev.com)# whoknows-crawler
Automated crawler and simulation tool for WhoKnows – uses Playwright to test endpoints, user flows and load scenarios against syntax-reborndev.com
