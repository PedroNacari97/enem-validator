import base64
from typing import Optional, Dict, Any

from playwright.async_api import async_playwright, Page, Browser, BrowserContext

from helpers import (
    parse_enem_result,
    _count_numeric_areas,
    cpf_mask_matches,
    now_iso,
)
from config import HEADLESS, logger

SESSIONS: Dict[str, Dict[str, Any]] = {}

_playwright = None
_browser: Optional[Browser] = None


async def launch_browser(playwright):
    for channel in ("msedge", "chrome"):
        try:
            return await playwright.chromium.launch(channel=channel, headless=HEADLESS)
        except Exception:
            pass
    return await playwright.chromium.launch(headless=HEADLESS)


async def startup_event():
    global _playwright, _browser
    _playwright = await async_playwright().start()
    _browser = await launch_browser(_playwright)


async def shutdown_event():
    global _playwright, _browser
    if _browser:
        await _browser.close()
    if _playwright:
        await _playwright.stop()


async def new_context_page():
    ctx: BrowserContext = await _browser.new_context()
    page: Page = await ctx.new_page()
    await page.bring_to_front()
    return ctx, page


async def _peek_text(page: Page) -> str:
    try:
        return await page.inner_text("body")
    except Exception:
        return ""


async def try_finalize(sess):
    page: Page = sess.get("page")
    ctx: BrowserContext = sess.get("ctx")
    if not page or page.is_closed():
        return None

    text = await _peek_text(page)
    data = parse_enem_result(text)
    cpf_mask = data.get("cpf_mask")
    numeric_areas = _count_numeric_areas(data)

    status = None
    if cpf_mask:
        ok = cpf_mask_matches(cpf_mask, sess["session_cpf"])
        if ok:
            status = "aprovado"
        else:
            status = "negado"  # 🚨 CPF não bateu
            logger.warning(
                f"CPF divergente: esperado {sess['session_cpf']}, encontrado {cpf_mask}"
            )
    elif numeric_areas >= 2:
        status = "revisao"
    else:
        return None

    img_b64 = None
    try:
        shot = await page.screenshot(full_page=True)
        img_b64 = base64.b64encode(shot).decode("ascii")
    except Exception:
        pass

    sess["status"] = status
    sess["result"] = {
        "cpf_mask": cpf_mask,
        "ano": data.get("ano"),
        "nome": data.get("nome"),
        "areas": data.get("areas"),
    }
    sess.setdefault("audit", []).append({"ts": now_iso(), "screenshot_b64": img_b64})

    try:
        await ctx.close()
    except Exception:
        pass
    sess["ctx"] = None
    sess["page"] = None
    return {"status": status, "result": sess["result"]}


async def find_form_scope(page_or_frame):
    scope = page_or_frame
    for q in [
        "input[name*='chave' i]",
        "#chave",
        "input[id*='chave' i]",
        "input[name*='codigo' i]",
        "#codigo",
        "input[id*='codigo' i]",
    ]:
        if await scope.query_selector(q):
            return scope
    return scope


async def type_or_js(scope, el, value: str):
    try:
        await el.fill(value)
        return True
    except Exception:
        try:
            await scope.evaluate(
                "(el, v) => { el.value = v; el.dispatchEvent(new Event('input', {bubbles:true})); el.dispatchEvent(new Event('change', {bubbles:true})); }",
                el,
                value,
            )
            return True
        except Exception:
            return False


async def fill_chave_any(scope, value: str):
    for sel in [
        "input[name*='chave' i]",
        "#chave",
        "input[id*='chave' i]",
        "input[name*='codigo' i]",
        "#codigo",
        "input[id*='codigo' i]",
    ]:
        el = await scope.query_selector(sel)
        if el:
            ok = await type_or_js(scope, el, value)
            if ok:
                return True
    return False
