"""
Epic Games free games auto-claimer for multiple accounts (parallel).

Usage:
  python claimer.py login acc1      # one-time manual login for an account (saves session)
  python claimer.py list            # show current free games
  python claimer.py claim           # claim current free games on all accounts at once
  python claimer.py daemon          # claim now, then repeat every N hours
"""
import asyncio
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import aiohttp
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

if getattr(sys, "frozen", False):
    ROOT = Path(sys.executable).parent
    BUNDLE = Path(getattr(sys, "_MEIPASS", ROOT))
else:
    ROOT = Path(__file__).parent
    BUNDLE = ROOT

PROFILES = ROOT / "profiles"
SHOTS = ROOT / "screenshots"
HISTORY_FILE = ROOT / "claimed.json"

DEFAULT_CONFIG = {
    "accounts": ["acc1", "acc2", "acc3"],
    "headless": False,
    "browser_path": "C:\\Program Files\\Yandex\\YandexBrowser\\Application\\browser.exe",
    "sync": True,
    "country": "US",
    "check_interval_hours": 6,
    "telegram_bot_token": "",
    "telegram_chat_id": "",
}


def load_config():
    path = ROOT / "config.json"
    if not path.exists() and (BUNDLE / "config.json").exists():
        shutil.copy(BUNDLE / "config.json", path)
    if not path.exists():
        path.write_text(json.dumps(DEFAULT_CONFIG, indent=2, ensure_ascii=False),
                        encoding="utf-8")
    return json.loads(path.read_text(encoding="utf-8"))


CONFIG = load_config()

FREE_API = ("https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions"
            "?locale=en-US&country={c}&allowCountries={c}")
STORE = "https://store.epicgames.com/en-US"
LAUNCH_ARGS = ["--disable-blink-features=AutomationControlled", "--lang=en-US"]


def log(acc, msg):
    print(f"[{datetime.now():%H:%M:%S}] [{acc}] {msg}", flush=True)


def load_history():
    if HISTORY_FILE.exists():
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    return {}


def save_history(h):
    HISTORY_FILE.write_text(json.dumps(h, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------- free games
def _parse_date(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


async def fetch_free_games():
    url = FREE_API.format(c=CONFIG.get("country", "US"))
    async with aiohttp.ClientSession() as s:
        async with s.get(url, timeout=aiohttp.ClientTimeout(total=30)) as r:
            data = await r.json(content_type=None)

    now = datetime.now(timezone.utc)
    games = []
    for el in data["data"]["Catalog"]["searchStore"]["elements"]:
        promos = (el.get("promotions") or {}).get("promotionalOffers") or []
        active = False
        for block in promos:
            for p in block.get("promotionalOffers", []):
                if (p["discountSetting"]["discountPercentage"] == 0
                        and _parse_date(p["startDate"]) <= now <= _parse_date(p["endDate"])):
                    active = True
        if not active:
            continue

        slug = None
        for m in (el.get("catalogNs") or {}).get("mappings") or []:
            if m.get("pageSlug"):
                slug = m["pageSlug"]
                break
        if not slug:
            for m in el.get("offerMappings") or []:
                if m.get("pageSlug"):
                    slug = m["pageSlug"]
                    break
        slug = slug or el.get("productSlug") or el.get("urlSlug")
        if not slug:
            continue
        slug = slug.split("/")[0]
        kind = "bundles" if el.get("offerType") == "BUNDLE" else "p"
        games.append({"id": el["id"], "title": el["title"], "url": f"{STORE}/{kind}/{slug}"})
    return games


# ---------------------------------------------------------------- browser
async def open_context(pw, acc, headless):
    PROFILES.mkdir(exist_ok=True)
    # Playwright's default flags that break sync / reveal automation
    ignore = ["--enable-automation", "--disable-extensions",
              "--disable-component-extensions-with-background-pages",
              "--disable-default-apps", "--disable-background-networking"]
    if CONFIG.get("sync", True):
        ignore += ["--disable-sync", "--password-store=basic", "--use-mock-keychain"]
    kwargs = dict(
        user_data_dir=str(PROFILES / acc),
        headless=headless,
        args=LAUNCH_ARGS,
        ignore_default_args=ignore,
        locale="en-US",
        no_viewport=True,
    )
    exe = CONFIG.get("browser_path")
    if exe and Path(exe).exists():
        kwargs["executable_path"] = exe
    elif CONFIG.get("browser_channel"):  # e.g. "chrome" or "msedge"
        kwargs["channel"] = CONFIG["browser_channel"]
    ctx = await pw.chromium.launch_persistent_context(**kwargs)
    await ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
    return ctx


async def is_logged_in(page):
    await page.goto("https://www.epicgames.com/account/personal", wait_until="domcontentloaded")
    await page.wait_for_timeout(4000)
    return "/id/login" not in page.url and "login" not in page.url.lower()


async def cmd_login(acc):
    async with async_playwright() as pw:
        ctx = await open_context(pw, acc, headless=False)
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        if CONFIG.get("sync", True):
            ya = await ctx.new_page()
            await ya.goto("https://passport.yandex.ru/auth")
            log(acc, "Вкладка Яндекса: войди в Яндекс ID и включи синхронизацию "
                     "(меню ≡ → Синхронизация), чтобы подтянулись пароли.")
            await page.bring_to_front()
        await page.goto("https://www.epicgames.com/id/login")
        log(acc, "Войди в аккаунт Epic в открывшемся окне (включая 2FA/капчу).")
        log(acc, "Жду входа до 10 минут...")
        for _ in range(120):
            await page.wait_for_timeout(5000)
            try:
                url = page.url
            except Exception:
                break
            if "epicgames.com" in url and "/id/" not in url:
                break
        ok = await is_logged_in(page)
        log(acc, "Успешно, сессия сохранена." if ok else "Вход не подтверждён, попробуй снова.")
        await ctx.close()


async def click_if_visible(locator, timeout=1500):
    try:
        await locator.first.wait_for(state="visible", timeout=timeout)
        await locator.first.click()
        return True
    except PWTimeout:
        return False


async def claim_game(page, acc, game):
    await page.goto(game["url"], wait_until="domcontentloaded")
    await page.wait_for_timeout(3000)

    # age gate
    await click_if_visible(page.get_by_role("button", name="Continue"), 2000)

    btn = page.locator('[data-testid="purchase-cta-button"]').first
    try:
        await btn.wait_for(state="visible", timeout=20000)
    except PWTimeout:
        return "error: кнопка покупки не найдена"
    text = (await btn.inner_text()).strip().lower()
    if any(w in text for w in ("in library", "owned")):
        return "already"
    if "get" not in text:
        return f"error: неожиданная кнопка '{text}'"

    await btn.click()
    # "Get" can open an edition chooser / confirm modal on some pages
    await page.wait_for_timeout(2000)

    frame = page.frame_locator("#webPurchaseContainer iframe")
    place = frame.locator("button.payment-order-confirm__btn, button:has-text('Place Order')")
    try:
        await place.first.wait_for(state="visible", timeout=30000)
    except PWTimeout:
        return "error: окно оформления не появилось (капча?)"
    await page.wait_for_timeout(1000)
    await place.first.click()

    # EU refund policy confirmation
    await click_if_visible(frame.get_by_role("button", name="I Accept"), 5000) or \
        await click_if_visible(frame.get_by_role("button", name="I Agree"), 2000)

    # wait for success
    for _ in range(40):
        await page.wait_for_timeout(1500)
        try:
            if await page.get_by_text("Thanks for your order", exact=False).count():
                return "claimed"
            if await frame.locator("text=/captcha/i").count():
                log(acc, "Похоже на капчу — реши её в окне браузера.")
            t = (await btn.inner_text()).strip().lower()
            if "in library" in t or "owned" in t:
                return "claimed"
        except Exception:
            pass
    return "error: не дождались подтверждения"


async def run_account(pw, acc, games, history):
    headless = CONFIG.get("headless", False)
    ctx = await open_context(pw, acc, headless)
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()
    results = {}
    try:
        if not await is_logged_in(page):
            if getattr(sys, "frozen", False):
                log(acc, f"Не залогинен! Нажми кнопку 'Войти · {acc}' в программе")
            else:
                log(acc, f"Не залогинен! Выполни: python claimer.py login {acc}")
            return {g["title"]: "not logged in" for g in games}
        done = set(history.get(acc, []))
        for g in games:
            if g["id"] in done:
                log(acc, f"{g['title']}: уже забрано ранее")
                continue
            log(acc, f"Забираю: {g['title']}")
            try:
                res = await claim_game(page, acc, g)
            except Exception as e:
                res = f"error: {e}"
            log(acc, f"{g['title']}: {res}")
            results[g["title"]] = res
            if res in ("claimed", "already"):
                history.setdefault(acc, []).append(g["id"])
            else:
                SHOTS.mkdir(exist_ok=True)
                await page.screenshot(path=str(SHOTS / f"{acc}_{datetime.now():%Y%m%d_%H%M%S}.png"))
    finally:
        await ctx.close()
    return results


async def notify(text):
    tok, chat = CONFIG.get("telegram_bot_token"), CONFIG.get("telegram_chat_id")
    if not tok or not chat:
        return
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                         json={"chat_id": chat, "text": text})
    except Exception as e:
        print("telegram error:", e)


async def cmd_claim():
    games = await fetch_free_games()
    if not games:
        print("Сейчас нет бесплатных раздач.")
        return "Сейчас нет бесплатных раздач."
    print("Бесплатно сейчас:", ", ".join(g["title"] for g in games))
    history = load_history()
    async with async_playwright() as pw:
        results = await asyncio.gather(
            *(run_account(pw, acc, games, history) for acc in CONFIG["accounts"]),
            return_exceptions=True)
    save_history(history)

    lines = []
    for acc, res in zip(CONFIG["accounts"], results):
        if isinstance(res, Exception):
            lines.append(f"{acc}: ОШИБКА {res}")
        else:
            for title, r in res.items():
                lines.append(f"{acc}: {title} -> {r}")
    summary = "\n".join(lines) or "Всё уже забрано."
    print("\n=== Итог ===\n" + summary)
    if lines:
        await notify("Epic claimer:\n" + summary)
    return summary


async def cmd_daemon():
    while True:
        try:
            await cmd_claim()
        except Exception as e:
            print("Ошибка цикла:", e)
        hours = CONFIG.get("check_interval_hours", 6)
        print(f"Следующая проверка через {hours} ч.")
        await asyncio.sleep(hours * 3600)


async def cmd_list():
    for g in await fetch_free_games():
        print(f"- {g['title']}  {g['url']}")


def main():
    if sys.platform == "win32" and sys.stdout is not None:
        sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) < 2:
        print(__doc__)
        return
    cmd = sys.argv[1]
    if cmd == "login":
        accs = sys.argv[2:] or CONFIG["accounts"]
        for a in accs:
            asyncio.run(cmd_login(a))
    elif cmd == "claim":
        asyncio.run(cmd_claim())
    elif cmd == "daemon":
        asyncio.run(cmd_daemon())
    elif cmd == "list":
        asyncio.run(cmd_list())
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
