# app.py (v2.7) — INEP ENEM validator (Playwright + chave auto + verificação de CPF)
import os, re, base64, sys, asyncio, uuid, unicodedata, logging
from datetime import datetime
from typing import Optional, Dict, Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import BaseModel
from playwright.async_api import async_playwright, Page, Browser, BrowserContext, TimeoutError as PWTimeout

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("enem-validator")

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

SESSION_CPF = "39847351899"   # CPF chumbado para teste
HEADLESS = os.getenv("HEADLESS", "1") != "0"
INEP_URL = "https://enem.inep.gov.br/participante/#!/autenticidade"
NAV_TIMEOUT = int(os.getenv("NAV_TIMEOUT_MS", "45000"))

app = FastAPI(title="Servidor ENEM - Verificação via INEP", version="2.7")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
env = Environment(loader=FileSystemLoader("templates"), autoescape=select_autoescape())

SESSIONS: Dict[str, Dict[str, Any]] = {}

def now_iso(): return datetime.utcnow().isoformat() + "Z"

def mask_cpf(cpf: str) -> str:
    d = ''.join([c for c in cpf if c.isdigit()])
    if len(d) != 11: return "***.***.***-**"
    return f"{d[0:3]}.***.{d[6:9]}-**"

def cpf_mask_matches(mask: str, cpf: str) -> bool:
    only = ''.join([c for c in cpf if c.isdigit()])
    if len(only) != 11: return False
    m = re.sub(r'[^0-9\*]', '', mask or '')
    if len(m) != 11: return False
    return all(md == '*' or md == cd for md, cd in zip(m, only))

def norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s)
    s = ''.join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return s.lower()

# ===================== Parsing =====================
def parse_enem_result(text: str) -> Dict[str, Any]:
    cpf_mask = None
    m = re.search(r"\b[\d\*]{3}\.[\d\*]{3}\.[\d\*]{3}-[\d\*]{2}\b", text)
    if m: cpf_mask = m.group(0)

    years = [int(y) for y in re.findall(r"\b(20\d{2})\b", text)]
    year = max([y for y in years if y >= 2009], default=None)

    raw_lines = [l.strip() for l in text.splitlines() if l.strip()]
    norm_lines = [norm(l) for l in raw_lines]
    labels = {
        "linguagens": ["linguagens"],
        "humanas":    ["ciencias humanas"],
        "natureza":   ["ciencias da natureza"],
        "matematica": ["matematica"],
        "redacao":    ["redacao"],
    }
    num_re = re.compile(r"\b(1000|\d{2,3}(?:[.,]\d{1,2})?)\b")
    areas: Dict[str, Optional[float]] = {k: None for k in labels.keys()}

    for key, variants in labels.items():
        idx = None
        for i, line in enumerate(norm_lines):
            if any(v in line for v in variants): idx = i; break
        if idx is None: continue
        for j in range(idx, min(idx+4, len(raw_lines))):
            mm = num_re.search(raw_lines[j])
            if mm:
                try: areas[key] = float(mm.group(1).replace(",", "."))
                except: pass
                break

    nome = None
    for rl, nl in zip(raw_lines, norm_lines):
        if "nome" in nl or "participante" in nl:
            nome = rl; break

    return {"cpf_mask": cpf_mask, "ano": year, "areas": areas, "nome": nome}

def _count_numeric_areas(data: Dict[str, Any]) -> int:
    return sum(1 for v in (data.get("areas") or {}).values() if isinstance(v, (int,float)))

async def _peek_text(page: Page) -> str:
    try: return await page.inner_text("body")
    except: return ""

async def try_finalize(sess):
    page: Page = sess.get("page")
    ctx: BrowserContext = sess.get("ctx")
    if not page or page.is_closed(): return None

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
            logger.warning(f"CPF divergente: esperado {sess['session_cpf']}, encontrado {cpf_mask}")
    elif numeric_areas >= 2:
        status = "revisao"
    else:
        return None

    img_b64 = None
    try:
        shot = await page.screenshot(full_page=True)
        img_b64 = base64.b64encode(shot).decode("ascii")
    except: pass

    sess["status"] = status
    sess["result"] = {"cpf_mask": cpf_mask,"ano": data.get("ano"),
                      "nome": data.get("nome"),"areas": data.get("areas")}
    sess.setdefault("audit", []).append({"ts": now_iso(),"screenshot_b64": img_b64})

    try: await ctx.close()
    except: pass
    sess["ctx"] = None; sess["page"] = None
    return {"status": status, "result": sess["result"]}

# ===================== Playwright bootstrap =====================
_playwright = None
_browser: Optional[Browser] = None

async def launch_browser(playwright):
    for channel in ("msedge","chrome"):
        try:
            return await playwright.chromium.launch(channel=channel, headless=HEADLESS)
        except: pass
    return await playwright.chromium.launch(headless=HEADLESS)

@app.on_event("startup")
async def startup_event():
    global _playwright, _browser
    _playwright = await async_playwright().start()
    _browser = await launch_browser(_playwright)

@app.on_event("shutdown")
async def shutdown_event():
    global _playwright, _browser
    if _browser: await _browser.close()
    if _playwright: await _playwright.stop()

async def new_context_page():
    ctx: BrowserContext = await _browser.new_context()
    page: Page = await ctx.new_page()
    await page.bring_to_front()
    return ctx, page

# ===================== Helpers =====================
async def find_form_scope(page_or_frame):
    scope = page_or_frame
    for q in ["input[name*='chave' i]", "#chave", "input[id*='chave' i]",
              "input[name*='codigo' i]", "#codigo", "input[id*='codigo' i]"]:
        if await scope.query_selector(q): return scope
    return scope

async def type_or_js(scope, el, value: str):
    try:
        await el.fill(value); return True
    except:
        try:
            await scope.evaluate(
                "(el, v) => { el.value = v; el.dispatchEvent(new Event('input', {bubbles:true})); el.dispatchEvent(new Event('change', {bubbles:true})); }",
                el, value
            )
            return True
        except: return False

async def fill_chave_any(scope, value: str):
    for sel in ["input[name*='chave' i]", "#chave", "input[id*='chave' i]",
                "input[name*='codigo' i]", "#codigo", "input[id*='codigo' i]"]:
        el = await scope.query_selector(sel)
        if el:
            ok = await type_or_js(scope, el, value)
            if ok: return True
    return False

# ===================== Models =====================
class StartBody(BaseModel): chave: str

# ===================== Routes =====================
@app.get("/", response_class=HTMLResponse)
async def index():
    tpl = env.get_template("index.html")
    return tpl.render(cpf_mask=mask_cpf(SESSION_CPF))

@app.post("/v1/enem/start")
async def start(b: StartBody):
    ctx, page = await new_context_page()
    await page.goto(INEP_URL, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)

    vid = "ver_" + uuid.uuid4().hex[:12]
    SESSIONS[vid] = {"id": vid,"created_at": now_iso(),"chave": b.chave.strip(),
                     "session_cpf": SESSION_CPF,"ctx": ctx,"page": page,
                     "status": "captcha_pendente","audit": []}

    # Preenche automaticamente a chave
    try:
        # Espera até que algum input apareça (pode estar em frame)
        await page.wait_for_timeout(1500)  # dá tempo do INEP renderizar
        scope = await find_form_scope(page)

        ok = await fill_chave_any(scope, b.chave.strip())
        if not ok:
            # tenta em todos os frames, caso não esteja no root
            for fr in page.frames:
                try:
                    ok = await fill_chave_any(fr, b.chave.strip())
                    if ok: break
                except: pass

        if ok:
            logger.info(f"✅ Chave {b.chave.strip()} preenchida automaticamente no INEP.")
        else:
            logger.warning("⚠️ Não foi possível preencher a chave automaticamente (campo não encontrado).")
    except Exception as e:
        logger.error(f"Erro ao tentar preencher a chave automaticamente: {e}")


    return {"verification_id": vid,"cpf_mask": mask_cpf(SESSION_CPF),
            "status": "captcha_pendente","opened": True}

@app.get("/v1/enem/status/{verification_id}")
async def status(verification_id: str):
    sess = SESSIONS.get(verification_id)
    if not sess: return {"status": "nao_encontrado"}
    final = await try_finalize(sess)
    if final: return {"status": final["status"],"result": final["result"]}
    return {"status": sess.get("status","captcha_pendente")}
