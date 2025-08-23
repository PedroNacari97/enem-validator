import uuid
from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape

from models import StartBody
from helpers import mask_cpf, now_iso
from browser import (
    new_context_page,
    try_finalize,
    SESSIONS,
    fill_chave_any,
    find_form_scope,
)
from config import SESSION_CPF, INEP_URL, NAV_TIMEOUT, logger

router = APIRouter()

env = Environment(loader=FileSystemLoader("templates"), autoescape=select_autoescape())


@router.get("/", response_class=HTMLResponse)
async def index():
    tpl = env.get_template("index.html")
    return tpl.render(cpf_mask=mask_cpf(SESSION_CPF))


@router.post("/v1/enem/start")
async def start(b: StartBody):
    ctx, page = await new_context_page()
    await page.goto(INEP_URL, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)

    vid = "ver_" + uuid.uuid4().hex[:12]
    SESSIONS[vid] = {
        "id": vid,
        "created_at": now_iso(),
        "chave": b.chave.strip(),
        "session_cpf": SESSION_CPF,
        "ctx": ctx,
        "page": page,
        "status": "captcha_pendente",
        "audit": [],
    }

    try:
        await page.wait_for_timeout(1500)
        scope = await find_form_scope(page)

        ok = await fill_chave_any(scope, b.chave.strip())
        if not ok:
            for fr in page.frames:
                try:
                    ok = await fill_chave_any(fr, b.chave.strip())
                    if ok:
                        break
                except Exception:
                    pass

        if ok:
            logger.info(
                f"✅ Chave {b.chave.strip()} preenchida automaticamente no INEP."
            )
        else:
            logger.warning(
                "⚠️ Não foi possível preencher a chave automaticamente (campo não encontrado)."
            )
    except Exception as e:
        logger.error(f"Erro ao tentar preencher a chave automaticamente: {e}")

    return {
        "verification_id": vid,
        "cpf_mask": mask_cpf(SESSION_CPF),
        "status": "captcha_pendente",
        "opened": True,
    }


@router.get("/v1/enem/status/{verification_id}")
async def status(verification_id: str):
    sess = SESSIONS.get(verification_id)
    if not sess:
        return {"status": "nao_encontrado"}
    final = await try_finalize(sess)
    if final:
        return {"status": final["status"], "result": final["result"]}
    return {"status": sess.get("status", "captcha_pendente")}
