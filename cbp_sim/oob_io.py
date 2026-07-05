"""
Serialização da ordem de batalha em CSV (além do JSON nativo).

A OOB do wargame OAS tem campos aninhados (``composition``, ``weapons``,
``capabilities``, ``detectionRange``, ``attackRange``, ``position``). Para
um CSV plano e reversível, cada grupo-tarefa vira uma linha e os campos
aninhados são codificados em colunas com convenção de sufixo:

    id, team, name, category, movement, stayingPower, notes,
    col, row,                              (position)
    det_surface, det_air, det_submarine, det_land,   (detectionRange)
    atk_surface, atk_air, atk_submarine, atk_land,    (attackRange)
    composition,                           "tipo:qtd; tipo:qtd"
    weapons,                               "tipo:qtd:alcance; ..."
    capabilities,                          "chave:valor; ..."
    embarked, hostId, stealthy

Colunas ausentes assumem o padrão vazio/0, de modo que uma planilha
mínima (id, team, category, stayingPower, movement, col, row) já produz
uma OOB válida — útil para editar forças no Excel/LibreOffice.
"""

from __future__ import annotations

import io

import pandas as pd

_DIRS = ("surface", "air", "submarine", "land")

CSV_COLUMNS = [
    "id", "team", "name", "category", "movement", "stayingPower", "notes",
    "col", "row",
    *[f"det_{d}" for d in _DIRS],
    *[f"atk_{d}" for d in _DIRS],
    "composition", "weapons", "capabilities",
    "embarked", "hostId", "stealthy",
]


def _fmt_composition(comp: list) -> str:
    return "; ".join(f"{c['type']}:{c['quantity']}" for c in (comp or []))


def _parse_composition(s: str) -> list:
    out = []
    for part in _split(s):
        typ, _, qty = part.partition(":")
        out.append({"type": typ.strip(), "quantity": _int(qty)})
    return out


def _fmt_weapons(weapons: dict) -> str:
    parts = []
    for wpn, w in (weapons or {}).items():
        qty = w.get("quantity", 0)
        rng = w.get("range")
        parts.append(f"{wpn}:{qty}:{rng}" if rng is not None
                     else f"{wpn}:{qty}")
    return "; ".join(parts)


def _parse_weapons(s: str) -> dict:
    out = {}
    for part in _split(s):
        bits = part.split(":")
        wpn = bits[0].strip()
        if not wpn:
            continue
        entry = {"quantity": _int(bits[1]) if len(bits) > 1 else 0}
        if len(bits) > 2 and bits[2].strip() != "":
            entry["range"] = _int(bits[2])
        out[wpn] = entry
    return out


def _fmt_caps(caps: dict) -> str:
    return "; ".join(f"{k}:{v}" for k, v in (caps or {}).items())


def _parse_caps(s: str) -> dict:
    out = {}
    for part in _split(s):
        k, _, v = part.partition(":")
        if k.strip():
            out[k.strip()] = _int(v)
    return out


def _split(s) -> list[str]:
    if s is None:
        return []
    s = str(s).strip()
    if not s or s.lower() == "nan":
        return []
    return [p.strip() for p in s.split(";") if p.strip()]


def _int(x) -> int:
    try:
        return int(float(str(x).strip()))
    except (ValueError, TypeError):
        return 0


def _get(row: dict, key: str, default=""):
    v = row.get(key, default)
    if v is None:
        return default
    if isinstance(v, float) and pd.isna(v):
        return default
    return v


def oob_to_dataframe(oob: dict) -> pd.DataFrame:
    """Converte uma OOB (dict) em DataFrame plano (uma linha por grupo)."""
    rows = []
    for team in ("blue", "red"):
        for s in oob["forces"].get(team, []):
            pos = s.get("position") or {"col": 0, "row": 0}
            det = s.get("detectionRange") or {}
            atk = s.get("attackRange") or {}
            row = {
                "id": s["id"], "team": team, "name": s.get("name", s["id"]),
                "category": s["category"], "movement": s.get("movement", 0),
                "stayingPower": s.get("stayingPower", 1),
                "notes": s.get("notes", ""),
                "col": pos.get("col", 0), "row": pos.get("row", 0),
                "composition": _fmt_composition(s.get("composition")),
                "weapons": _fmt_weapons(s.get("weapons")),
                "capabilities": _fmt_caps(s.get("capabilities")),
                "embarked": s.get("embarked", ""),
                "hostId": s.get("hostId", ""),
                "stealthy": bool(s.get("stealthy", False)),
            }
            for d in _DIRS:
                row[f"det_{d}"] = det.get(d, 0)
                row[f"atk_{d}"] = atk.get(d, 0)
            rows.append(row)
    return pd.DataFrame(rows, columns=CSV_COLUMNS)


def oob_to_csv(oob: dict) -> str:
    """Serializa a OOB em texto CSV."""
    return oob_to_dataframe(oob).to_csv(index=False)


def dataframe_to_oob(df: pd.DataFrame) -> dict:
    """Reconstrói uma OOB (dict) a partir do DataFrame plano."""
    forces = {"blue": [], "red": []}
    for _, r in df.iterrows():
        row = r.to_dict()
        team = str(_get(row, "team", "blue")).strip().lower()
        if team not in forces:
            raise ValueError(
                f"Coluna 'team' deve ser 'blue' ou 'red'; obtido: {team!r}")
        uid = str(_get(row, "id", "")).strip()
        if not uid:
            raise ValueError("Cada linha precisa de um 'id' não vazio.")
        spec = {
            "id": uid,
            "name": str(_get(row, "name", uid)) or uid,
            "category": str(_get(row, "category", "surface")).strip(),
            "movement": _int(_get(row, "movement", 0)),
            "stayingPower": _int(_get(row, "stayingPower", 1)) or 1,
            "position": {"col": _int(_get(row, "col", 0)),
                         "row": _int(_get(row, "row", 0))},
        }
        det = {d: _int(_get(row, f"det_{d}", 0)) for d in _DIRS}
        atk = {d: _int(_get(row, f"atk_{d}", 0)) for d in _DIRS}
        if any(det.values()):
            spec["detectionRange"] = det
        if any(atk.values()):
            spec["attackRange"] = atk
        comp = _parse_composition(_get(row, "composition", ""))
        if comp:
            spec["composition"] = comp
        weapons = _parse_weapons(_get(row, "weapons", ""))
        if weapons:
            spec["weapons"] = weapons
        caps = _parse_caps(_get(row, "capabilities", ""))
        if caps:
            spec["capabilities"] = caps
        notes = str(_get(row, "notes", "")).strip()
        if notes:
            spec["notes"] = notes
        emb = str(_get(row, "embarked", "")).strip()
        if emb:
            spec["embarked"] = emb
        host = str(_get(row, "hostId", "")).strip()
        if host:
            spec["hostId"] = host
        stealthy = _get(row, "stealthy", False)
        if str(stealthy).strip().lower() in ("true", "1", "sim", "yes"):
            spec["stealthy"] = True
        forces[team].append(spec)
    if not forces["blue"] or not forces["red"]:
        raise ValueError("A OOB precisa de ao menos um grupo em cada força "
                         "(blue e red).")
    return {"forces": forces}


def csv_to_oob(text: str | bytes) -> dict:
    """Desserializa uma OOB a partir de texto/bytes CSV."""
    if isinstance(text, bytes):
        text = text.decode("utf-8-sig")
    df = pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False)
    return dataframe_to_oob(df)
