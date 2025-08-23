import re
import unicodedata
from datetime import datetime
from typing import Dict, Any, Optional


def now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def mask_cpf(cpf: str) -> str:
    digits = "".join([c for c in cpf if c.isdigit()])
    if len(digits) != 11:
        return "***.***.***-**"
    return f"{digits[0:3]}.***.{digits[6:9]}-**"


def cpf_mask_matches(mask: str, cpf: str) -> bool:
    only = "".join([c for c in cpf if c.isdigit()])
    if len(only) != 11:
        return False
    m = re.sub(r"[^0-9\\*]", "", mask or "")
    if len(m) != 11:
        return False
    return all(md == "*" or md == cd for md, cd in zip(m, only))


def norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return s.lower()


# ===================== Parsing =====================

def parse_enem_result(text: str) -> Dict[str, Any]:
    cpf_mask = None
    m = re.search(r"\b[\d\*]{3}\.[\d\*]{3}\.[\d\*]{3}-[\d\*]{2}\b", text)
    if m:
        cpf_mask = m.group(0)

    years = [int(y) for y in re.findall(r"\b(20\d{2})\b", text)]
    year = max([y for y in years if y >= 2009], default=None)

    raw_lines = [l.strip() for l in text.splitlines() if l.strip()]
    norm_lines = [norm(l) for l in raw_lines]
    labels = {
        "linguagens": ["linguagens"],
        "humanas": ["ciencias humanas"],
        "natureza": ["ciencias da natureza"],
        "matematica": ["matematica"],
        "redacao": ["redacao"],
    }
    num_re = re.compile(r"\b(1000|\d{2,3}(?:[.,]\d{1,2})?)\b")
    areas: Dict[str, Optional[float]] = {k: None for k in labels.keys()}

    for key, variants in labels.items():
        idx = None
        for i, line in enumerate(norm_lines):
            if any(v in line for v in variants):
                idx = i
                break
        if idx is None:
            continue
        for j in range(idx, min(idx + 4, len(raw_lines))):
            mm = num_re.search(raw_lines[j])
            if mm:
                try:
                    areas[key] = float(mm.group(1).replace(",", "."))
                except Exception:
                    pass
                break

    nome = None
    for rl, nl in zip(raw_lines, norm_lines):
        if "nome" in nl or "participante" in nl:
            nome = rl
            break

    return {"cpf_mask": cpf_mask, "ano": year, "areas": areas, "nome": nome}


def _count_numeric_areas(data: Dict[str, Any]) -> int:
    return sum(1 for v in (data.get("areas") or {}).values() if isinstance(v, (int, float)))
