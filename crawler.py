"""
whoknows-crawler – Python + Playwright simulation tool
Tester WhoKnows applikationen som en rigtig bruger via headless browser.
Bots registrerer sig selv hvis de ikke allerede eksisterer.
"""

import asyncio
import os
import random
import time
from dataclasses import dataclass, field
from datetime import datetime

import asyncpg
from dotenv import load_dotenv
from playwright.async_api import async_playwright, Page, BrowserContext

load_dotenv()

BASE_URL     = os.getenv("BASE_URL", "http://localhost:8080")
BOT_PASSWORD = os.getenv("BOT_PASSWORD", "Simulation2026!")
DB_DSN       = os.getenv("DB_DSN", "")
REPORT_EVERY_S = int(os.getenv("REPORT_EVERY_S", "15"))
NORMAL_BOTS  = int(os.getenv("NORMAL_BOTS", "10"))
HEAVY_BOTS   = int(os.getenv("HEAVY_BOTS", "5"))
SESSION_BOTS = int(os.getenv("SESSION_BOTS", "5"))

SEARCH_TERMS = [
    "linux", "docker", "python", "devops", "kubernetes",
    "nginx", "golang", "ansible", "terraform", "ubuntu",
    "postgresql", "bash", "ssh", "firewall", "github",
    "container", "security", "monitoring", "prometheus", "grafana",
    "go", "ci", "cd",
]

BOT_CREDENTIALS = [
    *[{"username": f"bot_normal_{i:02d}",  "password": BOT_PASSWORD} for i in range(1, 11)],
    *[{"username": f"bot_heavy_{i:02d}",   "password": BOT_PASSWORD} for i in range(1, 6)],
    *[{"username": f"bot_session_{i:02d}", "password": BOT_PASSWORD} for i in range(1, 6)],
]


# ─────────────────────────────── Metrics ─────────────────────────────────────

@dataclass
class Metrics:
    http_ok: int = 0
    http_fail: int = 0
    http_latencies: list = field(default_factory=list)

    login_ok: int = 0
    login_fail: int = 0
    register_ok: int = 0
    register_fail: int = 0

    search_ok: int = 0
    search_fail: int = 0
    search_invalid_json: int = 0
    search_missing_key: int = 0

    session_ok: int = 0
    session_fail: int = 0

    db_ok: int = 0
    db_fail: int = 0
    db_latencies: list = field(default_factory=list)

    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def snapshot(self):
        async with self._lock:
            snap = {
                "http_ok": self.http_ok, "http_fail": self.http_fail,
                "http_avg_lat": _avg(self.http_latencies),
                "login_ok": self.login_ok, "login_fail": self.login_fail,
                "register_ok": self.register_ok, "register_fail": self.register_fail,
                "search_ok": self.search_ok, "search_fail": self.search_fail,
                "search_invalid_json": self.search_invalid_json,
                "search_missing_key": self.search_missing_key,
                "session_ok": self.session_ok, "session_fail": self.session_fail,
                "db_ok": self.db_ok, "db_fail": self.db_fail,
                "db_avg_lat": _avg(self.db_latencies),
            }
            self.http_ok = self.http_fail = 0
            self.http_latencies.clear()
            self.login_ok = self.login_fail = 0
            self.register_ok = self.register_fail = 0
            self.search_ok = self.search_fail = 0
            self.search_invalid_json = self.search_missing_key = 0
            self.session_ok = self.session_fail = 0
            self.db_ok = self.db_fail = 0
            self.db_latencies.clear()
            return snap


def _avg(lst):
    return round(sum(lst) / len(lst) * 1000, 1) if lst else 0.0

def _uptime(ok, fail):
    return 100.0 if ok + fail == 0 else round(ok / (ok + fail) * 100, 1)

def _icon(ok, fail):
    if ok + fail == 0: return "⚪"
    pct = _uptime(ok, fail)
    if pct >= 99: return "🟢"
    if pct >= 90: return "🟡"
    return "🔴"


# ─────────────────────────────── HTTP bot ────────────────────────────────────

async def http_bot(m: Metrics, interval_s: float = 2.0):
    import aiohttp
    endpoints = [
        f"{BASE_URL}/health",
        f"{BASE_URL}/api/search?q=devops&language=en",
        f"{BASE_URL}/api/search?q=go&language=en",
        f"{BASE_URL}/metrics",
        f"{BASE_URL}/about",
    ]
    async with aiohttp.ClientSession() as session:
        idx = 0
        while True:
            url = endpoints[idx % len(endpoints)]
            idx += 1
            t = time.monotonic()
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    lat = time.monotonic() - t
                    async with m._lock:
                        if 200 <= resp.status < 400:
                            m.http_ok += 1
                            m.http_latencies.append(lat)
                        else:
                            m.http_fail += 1
                            print(f"[HTTP] ⚠️  {url} → {resp.status}")
            except Exception as e:
                async with m._lock:
                    m.http_fail += 1
                print(f"[HTTP] ❌ {url} – {e}")
            await asyncio.sleep(interval_s)


# ─────────────────────────────── DB bot ──────────────────────────────────────

async def db_bot(m: Metrics, interval_s: float = 5.0):
    if not DB_DSN:
        print("[DB] Ingen DSN konfigureret – DB-bot deaktiveret")
        return
    while True:
        t = time.monotonic()
        try:
            conn = await asyncpg.connect(DB_DSN)
            await conn.fetchval("SELECT 1")
            await conn.close()
            lat = time.monotonic() - t
            async with m._lock:
                m.db_ok += 1
                m.db_latencies.append(lat)
        except Exception as e:
            async with m._lock:
                m.db_fail += 1
            print(f"[DB] ❌ ping fejlede – {e}")
        await asyncio.sleep(interval_s)


# ─────────────────────────────── Browser helpers ─────────────────────────────

def _is_logged_in(content: str, username: str) -> bool:
    """Tjekker om siden indikerer at brugeren er logget ind."""
    lower = content.lower()
    return username.lower() in lower or "log out" in lower or "logout" in lower


async def browser_register(page: Page, cred: dict, m: Metrics) -> bool:
    """
    Registrerer bot-brugeren via /register-formularen.
    Returnerer True ved succes, False hvis brugeren allerede eksisterer eller fejl.
    """
    try:
        await page.goto(f"{BASE_URL}/register", wait_until="domcontentloaded", timeout=15000)

        await page.fill('input[name="username"]', cred["username"])
        await page.fill('input[name="email"]',    f"{cred['username']}@bot.internal")
        await page.fill('input[name="password"]',  cred["password"])

        # Udfyld password2 hvis den eksisterer
        if await page.locator('input[name="password2"]').count() > 0:
            await page.fill('input[name="password2"]', cred["password"])

        await page.click('input[type="submit"], button[type="submit"]')
        await page.wait_for_load_state("domcontentloaded", timeout=10000)

        content = await page.content()

        # Succes: enten logget ind direkte eller redirectet til login/search
        if _is_logged_in(content, cred["username"]) or page.url.endswith("/search") or page.url.endswith("/login"):
            async with m._lock:
                m.register_ok += 1
            print(f"[Bot] ✅ '{cred['username']}' registreret")
            return True

        # Allerede eksisterende bruger – det er fint
        if "already taken" in content.lower() or "already exists" in content.lower():
            async with m._lock:
                m.register_ok += 1
            return True

        async with m._lock:
            m.register_fail += 1
        print(f"[Bot] ⚠️  Registrering fejlede for '{cred['username']}' – URL: {page.url}")
        return False

    except Exception as e:
        async with m._lock:
            m.register_fail += 1
        print(f"[Bot] ❌ Registreringsfejl for '{cred['username']}' – {e}")
        return False


async def browser_login(page: Page, cred: dict, m: Metrics) -> bool:
    """
    Logger ind. Hvis login fejler fordi brugeren ikke eksisterer,
    registreres brugeren automatisk og login forsøges igen.
    """
    for attempt in range(2):
        try:
            await page.goto(f"{BASE_URL}/login", wait_until="domcontentloaded", timeout=15000)
            await page.fill('input[name="username"]', cred["username"])
            await page.fill('input[name="password"]', cred["password"])
            await page.click('input[type="submit"], button[type="submit"]')
            await page.wait_for_load_state("domcontentloaded", timeout=10000)

            content = await page.content()

            if _is_logged_in(content, cred["username"]):
                async with m._lock:
                    m.login_ok += 1
                return True

            # Login fejlede – er det fordi brugeren ikke eksisterer?
            lower = content.lower()
            user_not_found = "invalid" in lower or "incorrect" in lower or page.url.endswith("/api/login")

            if user_not_found and attempt == 0:
                print(f"[Bot] ℹ️  '{cred['username']}' ikke fundet – registrerer...")
                await browser_register(page, cred, m)
                continue  # Prøv login igen

            async with m._lock:
                m.login_fail += 1
            return False

        except Exception as e:
            async with m._lock:
                m.login_fail += 1
            print(f"[Bot] ❌ Login fejl for '{cred['username']}' – {e}")
            return False

    async with m._lock:
        m.login_fail += 1
    return False


async def browser_search(page: Page, term: str, m: Metrics):
    """Søger via API og validerer JSON-struktur, interagerer også med browser-UI."""
    try:
        import aiohttp
        cookies = {c["name"]: c["value"] for c in await page.context.cookies()}
        async with aiohttp.ClientSession(cookies=cookies) as session:
            async with session.get(
                f"{BASE_URL}/api/search?q={term}&language=en",
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status != 200:
                    async with m._lock:
                        m.search_fail += 1
                    return

                try:
                    data = await resp.json()
                except Exception:
                    async with m._lock:
                        m.search_invalid_json += 1
                        m.search_fail += 1
                    print(f"[Search] ❌ Ugyldigt JSON for '{term}'")
                    return

                if "search_results" not in data:
                    async with m._lock:
                        m.search_missing_key += 1
                        m.search_fail += 1
                    print(f"[Search] ❌ Mangler 'search_results' nøgle for '{term}'")
                    return

                async with m._lock:
                    m.search_ok += 1

        # Interagér med browser UI
        await page.goto(f"{BASE_URL}/", wait_until="domcontentloaded", timeout=10000)
        search_input = page.locator('input[name="q"], input[type="search"]').first
        if await search_input.count() > 0:
            await search_input.fill(term)
            await asyncio.sleep(random.uniform(0.3, 0.8))
            await search_input.press("Enter")
            await page.wait_for_load_state("domcontentloaded", timeout=10000)

    except Exception as e:
        async with m._lock:
            m.search_fail += 1
        print(f"[Search] ❌ {term} – {e}")


async def browser_logout(page: Page, m: Metrics):
    try:
        await page.goto(f"{BASE_URL}/logout", wait_until="domcontentloaded", timeout=10000)
        async with m._lock:
            m.session_ok += 1
    except Exception as e:
        async with m._lock:
            m.session_fail += 1
        print(f"[Bot] ❌ Logout fejl – {e}")


# ─────────────────────────────── User bots ───────────────────────────────────

async def normal_user_bot(bot_id: int, browser, m: Metrics):
    """Login → søg 3 gange med realistiske pauser → logout."""
    cred = BOT_CREDENTIALS[bot_id % len(BOT_CREDENTIALS)]
    print(f"[UserBot-{bot_id}] starter som '{cred['username']}' (normal)")

    while True:
        context: BrowserContext = await browser.new_context()
        page = await context.new_page()

        if await browser_login(page, cred, m):
            for _ in range(3):
                await browser_search(page, random.choice(SEARCH_TERMS), m)
                await asyncio.sleep(random.uniform(1.5, 3.0))

        await browser_logout(page, m)
        await context.close()
        await asyncio.sleep(5.0)


async def heavy_user_bot(bot_id: int, browser, m: Metrics):
    """Login → søg 10 gange hurtigt → logout."""
    cred = BOT_CREDENTIALS[bot_id % len(BOT_CREDENTIALS)]
    print(f"[UserBot-{bot_id}] starter som '{cred['username']}' (heavy)")

    while True:
        context: BrowserContext = await browser.new_context()
        page = await context.new_page()

        if await browser_login(page, cred, m):
            for _ in range(10):
                await browser_search(page, random.choice(SEARCH_TERMS), m)
                await asyncio.sleep(random.uniform(0.2, 0.5))

        await browser_logout(page, m)
        await context.close()
        await asyncio.sleep(1.0)


async def session_bot(bot_id: int, browser, m: Metrics):
    """Login → logout med det samme – stresser session-håndtering."""
    cred = BOT_CREDENTIALS[bot_id % len(BOT_CREDENTIALS)]
    print(f"[UserBot-{bot_id}] starter som '{cred['username']}' (session)")

    while True:
        context: BrowserContext = await browser.new_context()
        page = await context.new_page()
        await browser_login(page, cred, m)
        await browser_logout(page, m)
        await context.close()
        await asyncio.sleep(3.0)


# ─────────────────────────────── Reporter ────────────────────────────────────

async def reporter(m: Metrics):
    while True:
        await asyncio.sleep(REPORT_EVERY_S)
        snap = await m.snapshot()
        now = datetime.now().strftime("%H:%M:%S")

        sep = "══════════════════════════════════════════════════════"
        print(f"\n╔{sep}╗")
        print(f"║  📊 Rapport – {now:<39}║")
        print(f"╠{sep}╣")
        print(f"║  {_icon(snap['http_ok'], snap['http_fail'])} HTTP       │ OK:{snap['http_ok']:<5} Fejl:{snap['http_fail']:<5} Uptime:{_uptime(snap['http_ok'], snap['http_fail']):5.1f}% Lat:{snap['http_avg_lat']:5.1f} ms ║")
        print(f"╠{sep}╣")
        print(f"║  {_icon(snap['db_ok'], snap['db_fail'])} DB         │ OK:{snap['db_ok']:<5} Fejl:{snap['db_fail']:<5} Uptime:{_uptime(snap['db_ok'], snap['db_fail']):5.1f}% Lat:{snap['db_avg_lat']:5.1f} ms ║")
        print(f"╠{sep}╣")
        print(f"║  👤 Register  │ OK:{snap['register_ok']:<5} Fejl:{snap['register_fail']:<5}                                   ║")
        print(f"║  🔑 Login     │ OK:{snap['login_ok']:<5} Fejl:{snap['login_fail']:<5} Uptime:{_uptime(snap['login_ok'], snap['login_fail']):5.1f}%              ║")
        print(f"║  🔍 Søgning   │ OK:{snap['search_ok']:<5} Fejl:{snap['search_fail']:<5} Uptime:{_uptime(snap['search_ok'], snap['search_fail']):5.1f}% (inv.JSON:{snap['search_invalid_json']} mangl.key:{snap['search_missing_key']}) ║")
        print(f"║  🔓 Session   │ OK:{snap['session_ok']:<5} Fejl:{snap['session_fail']:<5} Uptime:{_uptime(snap['session_ok'], snap['session_fail']):5.1f}%              ║")
        print(f"╚{sep}╝")


# ──────────────────────────────── Main ───────────────────────────────────────

async def main():
    m = Metrics()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        print(f"▶ Crawler startet mod {BASE_URL}")
        print(f"▶ {NORMAL_BOTS} normal · {HEAVY_BOTS} heavy · {SESSION_BOTS} session user-bots")
        print(f"▶ Bots registrerer sig selv automatisk hvis de ikke eksisterer")

        tasks = [
            asyncio.create_task(http_bot(m)),
            asyncio.create_task(db_bot(m)),
            asyncio.create_task(reporter(m)),
        ]

        offset = 0
        for i in range(NORMAL_BOTS):
            tasks.append(asyncio.create_task(normal_user_bot(offset + i, browser, m)))
        offset += NORMAL_BOTS

        for i in range(HEAVY_BOTS):
            tasks.append(asyncio.create_task(heavy_user_bot(offset + i, browser, m)))
        offset += HEAVY_BOTS

        for i in range(SESSION_BOTS):
            tasks.append(asyncio.create_task(session_bot(offset + i, browser, m)))

        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            pass
        finally:
            await browser.close()
            print("\n✅ Crawler stoppet.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Afbrudt af bruger.")
