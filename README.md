# whoknows-crawler

Automated intelligent crawler and simulation tool for [WhoKnows](https://syntax-reborndev.com) – uses Playwright to interact with the application as a real browser would, including self-registration, login, search and logout flows.

## What it does

- **HTTP bots** – continuously hits `/health`, `/api/search`, `/metrics` and `/about`
- **DB bot** – pings PostgreSQL directly via asyncpg (optional)
- **Intelligent user bots** – register themselves automatically if they don't exist, then login, search and logout in realistic flows
- **Response validation** – verifies that `/api/search` returns valid JSON with a `search_results` key
- **Live report** – prints uptime, latency and error breakdown every 15 seconds

### Bot types

| Type | Count | Behaviour |
|---|---|---|
| Normal | 10 | Login → search 3 times with realistic pauses → logout |
| Heavy | 5 | Login → search 10 times rapidly → logout |
| Session | 5 | Login → logout immediately, stressing session handling |

### Self-registration

Bots are fully autonomous – no manual seeding required. On first run, each bot navigates to `/register`, fills in the form and creates its own account. On subsequent runs it logs in directly. If a bot's account already exists, it skips registration and proceeds to login.

## Prerequisites

- Python 3.11+

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
DB_DSN=                          # leave empty – prod DB is not exposed externally
REPORT_EVERY_S=15
NORMAL_BOTS=10
HEAVY_BOTS=5
SESSION_BOTS=5
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
║  📊 Rapport – 11:51:05                               ║
╠══════════════════════════════════════════════════════╣
║  🟢 HTTP       │ OK:7    Fejl:0   Uptime:100.0% Lat: 43.5 ms ║
║  ⚪ DB         │ OK:0    Fejl:0   Uptime:100.0% Lat:  0.0 ms ║
║  👤 Register  │ OK:20   Fejl:0                               ║
║  🔑 Login     │ OK:41   Fejl:0   Uptime:100.0%               ║
║  🔍 Søgning   │ OK:129  Fejl:0   Uptime:100.0% (inv.JSON:0 mangl.key:0) ║
║  🔓 Session   │ OK:44   Fejl:0   Uptime:100.0%               ║
╚══════════════════════════════════════════════════════╝
```

## Related

- [devops-syntaxsquad](https://github.com/SyntaxDevopsSquad-SDS/devops-syntaxsquad) – the application being tested
- [Live app](https://syntax-reborndev.com)
- [Monitoring](https://monitor.syntax-reborndev.com)
