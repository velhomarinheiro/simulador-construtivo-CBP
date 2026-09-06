"""
Camada de Planejamento Baseado em Capacidades (PBC / CBP).

Traduz decisões de planejamento de força (pacotes de força alternativos)
em modificações da ordem de batalha, associa custos ilustrativos de ciclo
de vida e agrega as MOEs da simulação construtiva em medidas de eficácia
por alternativa — permitindo análise de custo-efetividade e comparação
de opções de capacidade no cenário Operação Atlântico Sul.

Os custos são **ilustrativos** (unidades de custo ≈ R$ bilhão, ciclo de
vida ~10 anos) e devem ser calibrados com fontes orçamentárias reais.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

# ── Custos ilustrativos por grupo-tarefa da Força Azul ───────────────────────
UNIT_COSTS = {
    "BLUE-SAG-P": 14.0,    # NAM Atlântico + helicópteros orgânicos
    "BLUE-SAG-S1": 9.0,    # 3x Fragatas Tamandaré
    "BLUE-SAG-S2": 10.0,   # 2x FT + 2x Corvetas Barroso
    "BLUE-ANFIB": 6.0,     # NDM Bahia + LPD + NCC
    "BLUE-LOG-A": 1.5,
    "BLUE-LOG-T": 1.5,
    "BLUE-PAT-O1": 1.6,    # 2x NPaOc
    "BLUE-PAT-O2": 1.6,
    "BLUE-PAT-C1": 0.8,
    "BLUE-PAT-C2": 0.8,
    "BLUE-SUB-N": 25.0,    # SNAC Álvaro Alberto
    "BLUE-SUB-1": 5.0,     # S-40 Riachuelo
    "BLUE-SUB-2": 5.0,
    "BLUE-SUB-3": 5.0,
    "BLUE-SEOP": 0.3,
    "BLUE-MPRA-1": 1.5,    # 2x P-3AM
    "BLUE-MPRA-2": 1.5,
    "BLUE-CACA-1": 8.0,    # 6x F-39E Gripen
    "BLUE-CACA-2": 8.0,
    "BLUE-CJAT-1": 1.0,    # 2x AF-1
    "BLUE-CJAT-2": 1.0,
    "BLUE-DCOST1": 1.2,    # baterias MANSUP-ER
    "BLUE-DCOST2": 1.2,
    "BLUE-ADA-1": 1.5,
    "BLUE-ADA-2": 1.5,
    # Infraestruturas (FPSOs, portos, aeródromos) são ativos protegidos,
    # não itens de aquisição — custo 0 na comparação de pacotes de força.
}

# ── Taxonomia: domínios e grupos de capacidade ───────────────────────────────
# Organização dos meios por domínio (naval-superfície, naval-submarino,
# aéreo, terrestre, cibernético) e por grupo de capacidades. Para os meios
# navais, a referência é a estrutura de classificação em três camadas do
# Artigo 1 — Camada 2, componentes de força de Coutau-Bégarie (Traité,
# item 350): Dissuasão (DISS), Intervenção (INTERV), Vigilância (VIG),
# Costeira (COST), Anfíbia (ANF) e Logística (LOG). No cenário, o grupo
# aeronaval do NAM Atlântico (SAG-P) e a escolta do CSG vermelho (ESCCSG)
# são computados na componente de Intervenção. Domínios aéreo e terrestre
# recebem grupos análogos; o cibernético é tratado por estoques
# (C2/SEN/WPN/LOG), não por grupos-tarefa.

FORCE_TAXONOMY = {
    "blue": [
        {"domain": "⚓ Naval — Superfície", "groups": [
            {"sigla": "INTERV", "label": "Intervenção (grupo aeronaval)",
             "units": ["BLUE-SAG-P"]},
            {"sigla": "VIG", "label": "Vigilância (escolta oceânica)",
             "units": ["BLUE-SAG-S1", "BLUE-SAG-S2"]},
            {"sigla": "ANF", "label": "Anfíbia",
             "units": ["BLUE-ANFIB"]},
            {"sigla": "COST", "label": "Costeira (patrulha)",
             "units": ["BLUE-PAT-O1", "BLUE-PAT-O2",
                       "BLUE-PAT-C1", "BLUE-PAT-C2"]},
            {"sigla": "LOG", "label": "Logística (trem de esquadra)",
             "units": ["BLUE-LOG-A", "BLUE-LOG-T"]},
        ]},
        {"domain": "🌊 Naval — Submarino", "groups": [
            {"sigla": "DISS", "label": "Dissuasão (negação do mar)",
             "units": ["BLUE-SUB-N", "BLUE-SUB-1", "BLUE-SUB-2",
                       "BLUE-SUB-3"]},
        ]},
        {"domain": "✈️ Aéreo", "groups": [
            {"sigla": "DAE", "label": "Defesa aérea / superioridade",
             "units": ["BLUE-CACA-1", "BLUE-CACA-2"]},
            {"sigla": "PATMAR", "label": "Patrulha marítima e ISR",
             "units": ["BLUE-MPRA-1", "BLUE-MPRA-2"]},
            {"sigla": "ATQ", "label": "Ataque aeronaval",
             "units": ["BLUE-CJAT-1", "BLUE-CJAT-2"]},
        ]},
        {"domain": "🏔️ Terrestre", "groups": [
            {"sigla": "DCOST", "label": "Defesa costeira (A2/AD)",
             "units": ["BLUE-DCOST1", "BLUE-DCOST2"]},
            {"sigla": "GBAD", "label": "Defesa antiaérea",
             "units": ["BLUE-ADA-1", "BLUE-ADA-2"]},
            {"sigla": "OPESP", "label": "Operações especiais",
             "units": ["BLUE-SEOP"]},
        ]},
    ],
    "red": [
        {"domain": "⚓ Naval — Superfície", "groups": [
            {"sigla": "INTERV", "label": "Intervenção (grupo de batalha)",
             "units": ["RED-GBPA", "RED-GE-1"]},
            {"sigla": "VIG", "label": "Vigilância (escoltas)",
             "units": ["RED-GE-2", "RED-GE-3"]},
            {"sigla": "ANF", "label": "Anfíbia",
             "units": ["RED-GANF"]},
            {"sigla": "LOG", "label": "Logística",
             "units": ["RED-AOR-G", "RED-GLOG", "RED-AKE"]},
        ]},
        {"domain": "🌊 Naval — Submarino", "groups": [
            {"sigla": "DISS", "label": "Dissuasão (negação do mar)",
             "units": ["RED-KSN", "RED-KS-1"]},
        ]},
        {"domain": "✈️ Aéreo", "groups": [
            {"sigla": "DAE", "label": "Caça embarcada",
             "units": ["RED-KMF-1", "RED-KMF-2"]},
            {"sigla": "PATMAR", "label": "Patrulha marítima e AEW",
             "units": ["RED-MPRA-K1", "RED-MPRA-K2", "RED-AWACS-K"]},
        ]},
        {"domain": "🏔️ Terrestre", "groups": [
            {"sigla": "OPESP", "label": "Operações especiais",
             "units": ["RED-SEOP", "RED-SEOP-2"]},
        ]},
    ],
}

CYBER_DOMAIN_LABEL = "⚡ Cibernético"


def unit_group(unit_id: str, side: str = "blue"):
    """(domínio, sigla, rótulo do grupo) de um grupo-tarefa, ou None."""
    for dom in FORCE_TAXONOMY.get(side, []):
        for grp in dom["groups"]:
            if unit_id in grp["units"]:
                return dom["domain"], grp["sigla"], grp["label"]
    return None


#: Domínio-fantasia para os ativos protegidos (FPSOs, portos, aeródromos):
#: são objetivos do cenário, não itens de aquisição — ficam fora dos grupos
#: de capacidade e do cômputo de custo dos pacotes de força.
INFRA_DOMAIN = "🏭 Infraestrutura crítica"


def classify_unit(unit_id: str, side: str = "blue"):
    """
    (domínio, sigla, rótulo) de qualquer unidade da OOB: grupos de
    capacidade da taxonomia ou, para os ativos protegidos, o domínio
    de infraestrutura crítica.
    """
    tax = unit_group(unit_id, side)
    if tax is not None:
        return tax
    return INFRA_DOMAIN, "INFRA", "Ativo protegido (objetivo do cenário)"


def taxonomy_order(side: str = "blue") -> dict:
    """unit_id → índice de ordenação (domínio → grupo → posição na lista)."""
    order: dict[str, int] = {}
    i = 0
    for dom in FORCE_TAXONOMY.get(side, []):
        for grp in dom["groups"]:
            for uid in grp["units"]:
                order[uid] = i
                i += 1
    return order


def group_labels(side: str = "blue") -> list[tuple[str, str]]:
    """
    [(sigla, rótulo)] dos grupos de capacidade na ordem da taxonomia.
    No lado azul inclui INFRA ao final (ativos protegidos), pois as perdas
    de infraestrutura são a MOE central do cenário.
    """
    out = [(grp["sigla"], grp["label"])
           for dom in FORCE_TAXONOMY.get(side, [])
           for grp in dom["groups"]]
    if side == "blue":
        out.append(("INFRA", "Infraestrutura crítica (ativos protegidos)"))
    return out


def _effect_label(factor: float) -> str:
    if factor <= 0:
        return "✖ removido"
    if factor == 1.0:
        return "—"
    if factor > 1.0:
        return f"▲ ×{factor:g}" if factor >= 2 else f"▲ +{(factor - 1):.0%}"
    return f"▼ −{(1 - factor):.0%}"


def _composition_str(spec: dict) -> str:
    return " + ".join(f"{c['quantity']}× {c['type'].replace('_', ' ')}"
                      for c in (spec.get("composition") or []))


def package_composition(oob: dict, pkg: ForcePackage) -> "pd.DataFrame":
    """
    Composição de um pacote de força, organizada por domínio e grupo de
    capacidade: toda a força do lado do pacote, com a coluna "Efeito"
    indicando o que o pacote muda (removido / reforçado / adicionado),
    mais a linha do estoque cibernético.
    """
    import pandas as pd
    specs = {s["id"]: s for s in oob["forces"][pkg.side]}
    rows = []
    for dom in FORCE_TAXONOMY.get(pkg.side, []):
        for grp in dom["groups"]:
            for uid in grp["units"]:
                spec = specs.get(uid)
                if spec is None:
                    continue
                factor = pkg.modifications.get(uid, 1.0)
                rows.append({
                    "Domínio": dom["domain"],
                    "Grupo de capacidade": f"{grp['sigla']} — {grp['label']}",
                    "Grupo-tarefa": spec.get("name", uid),
                    "Composição": _composition_str(spec),
                    "Efeito do pacote": _effect_label(factor),
                })
    for extra in pkg.additions:
        tax = unit_group(extra.get("id", ""), pkg.side)
        rows.append({
            "Domínio": tax[0] if tax else "⚓ Naval — Superfície",
            "Grupo de capacidade": (f"{tax[1]} — {tax[2]}" if tax
                                    else "(novo grupo)"),
            "Grupo-tarefa": extra.get("name", extra.get("id", "novo")),
            "Composição": _composition_str(extra),
            "Efeito do pacote": "✚ adicionado",
        })
    cyber = pkg.cyber or {}
    rows.append({
        "Domínio": CYBER_DOMAIN_LABEL,
        "Grupo de capacidade": "CIB — Guerra cibernética (C2/SEN/WPN/LOG)",
        "Grupo-tarefa": "Estoque cibernético",
        "Composição": (" · ".join(f"{k}:{v}" for k, v in cyber.items())
                       if cyber else "sem estoque"),
        "Efeito do pacote": ("⚡ " + " · ".join(f"{k}+{v}"
                                               for k, v in cyber.items())
                             if cyber else "—"),
    })
    return pd.DataFrame(rows)


def preset_overview(oob: dict, packages: list,
                    cost_table: dict | None = None) -> "pd.DataFrame":
    """
    Matriz-resumo pacote × grupo de capacidade (lado azul): cada célula
    mostra o efeito líquido do pacote sobre o grupo ("—" = inalterado).
    Inclui as linhas de estoque cibernético e custo total.
    """
    import pandas as pd
    side = "blue"
    specs = {s["id"]: s for s in oob["forces"][side]}
    rows = []
    for dom in FORCE_TAXONOMY[side]:
        for grp in dom["groups"]:
            row = {"Domínio": dom["domain"],
                   "Grupo de capacidade": f"{grp['sigla']} — {grp['label']}"}
            for pkg in packages:
                effects = []
                for uid in grp["units"]:
                    if uid not in specs:
                        continue
                    f = pkg.modifications.get(uid, 1.0)
                    if f != 1.0:
                        effects.append(
                            f"{specs[uid].get('name', uid)} "
                            f"{_effect_label(f)}")
                row[pkg.name] = "; ".join(effects) if effects else "—"
            rows.append(row)
    cyber_row = {"Domínio": CYBER_DOMAIN_LABEL,
                 "Grupo de capacidade": "CIB — Estoque cibernético"}
    cost_row = {"Domínio": "💰", "Grupo de capacidade": "Custo total (UC)"}
    for pkg in packages:
        cyber_row[pkg.name] = (" · ".join(f"{k}:{v}"
                                          for k, v in pkg.cyber.items())
                               if pkg.cyber else "—")
        cost_row[pkg.name] = f"{package_cost(oob, pkg, cost_table):.1f}"
    rows.append(cyber_row)
    rows.append(cost_row)
    return pd.DataFrame(rows)


# Áreas de capacidade p/ o perfil radar (agregação da ordem de batalha)
CAPABILITY_AREAS = {
    "Antissubmarino (ASW)": lambda u: u.get("capabilities", {}).get("asw", 0),
    "Defesa Aérea": lambda u: (u.get("capabilities", {}).get("airDefense", 0)
                               + u.get("capabilities", {}).get("bmd", 0)),
    "Ataque de Superfície": lambda u: (
        u.get("weapons", {}).get("ascm", {}).get("quantity", 0)
        + u.get("weapons", {}).get("mss", {}).get("quantity", 0)),
    "Ataque Aéreo": lambda u: u.get("capabilities", {}).get("airAttack", 0),
    "Guerra Submarina": lambda u: (
        u.get("weapons", {}).get("torpedo", {}).get("quantity", 0)),
    "ISR / Vigilância": lambda u: sum(
        (u.get("detectionRange") or {}).values()),
    "Poder de Permanência": lambda u: u.get("stayingPower", 0),
}


#: Custo ilustrativo por ponto de estoque cibernético (equipe/capacidade).
CYBER_COST_PER_POINT = 0.4

@dataclass
class ForcePackage:
    """
    Pacote de força alternativo (opção de capacidade).

    ``modifications`` mapeia unit_id → fator de escala aplicado ao grupo:
    0 remove o grupo; 1 mantém; 1.5 reforça em ~50% (SP, armas e
    capacidades escalados). ``additions`` são specs completas de novos
    grupos-tarefa a incluir. ``cyber`` é o estoque cibernético do pacote
    por subtipo ({"C2":…, "SEN":…, "WPN":…, "LOG":…}), com custo de
    ``CYBER_COST_PER_POINT`` UC por ponto.
    """
    name: str
    description: str = ""
    modifications: dict = field(default_factory=dict)
    additions: list = field(default_factory=list)
    cyber: dict = field(default_factory=dict)
    side: str = "blue"


def _scale_group(spec: dict, factor: float) -> dict:
    s = copy.deepcopy(spec)
    s["stayingPower"] = max(1, round(spec["stayingPower"] * factor))
    for wpn, w in (s.get("weapons") or {}).items():
        if "quantity" in w:
            w["quantity"] = max(1, round(w["quantity"] * factor))
    caps = s.get("capabilities") or {}
    for k in caps:
        caps[k] = max(1, round(caps[k] * factor))
    for comp in s.get("composition") or []:
        comp["quantity"] = max(1, round(comp["quantity"] * factor))
    return s


def apply_package(oob: dict, pkg: ForcePackage) -> dict:
    """Aplica um pacote de força à ordem de batalha (retorna cópia)."""
    out = copy.deepcopy(oob)
    force = out["forces"][pkg.side]
    new_force = []
    for spec in force:
        factor = pkg.modifications.get(spec["id"], 1.0)
        if factor <= 0:
            continue
        new_force.append(spec if factor == 1.0 else _scale_group(spec, factor))
    for extra in pkg.additions:
        new_force.append(copy.deepcopy(extra))
    out["forces"][pkg.side] = new_force
    return out


def package_cost(oob: dict, pkg: ForcePackage,
                 cost_table: dict | None = None) -> float:
    """
    Custo ilustrativo do pacote (grupos presentes × escala + ciber).

    ``cost_table`` permite substituir os custos padrão (``UNIT_COSTS``)
    por uma tabela calibrada pelo usuário.
    """
    costs = cost_table if cost_table is not None else UNIT_COSTS
    total = 0.0
    for spec in oob["forces"][pkg.side]:
        base = float(costs.get(spec["id"], 0.0))
        factor = pkg.modifications.get(spec["id"], 1.0)
        if factor > 0:
            total += base * factor
    for extra in pkg.additions:
        total += float(extra.get("cost", costs.get(extra.get("id"), 0.0)))
    total += CYBER_COST_PER_POINT * sum(pkg.cyber.values())
    return total


def capability_profile(oob: dict, side: str = "blue",
                       cyber: dict | None = None) -> dict[str, float]:
    """Agrega o perfil de capacidades de uma força (p/ gráfico radar)."""
    profile = {}
    for area, fn in CAPABILITY_AREAS.items():
        profile[area] = float(sum(fn(u) for u in oob["forces"][side]))
    profile["Cibernética"] = float(sum((cyber or {}).values()))
    return profile


# ── Pacotes de força predefinidos (excursões de análise) ─────────────────────

PRESET_PACKAGES: list[ForcePackage] = [
    ForcePackage(
        name="Força Base",
        description="Ordem de batalha de referência da Operação Atlântico Sul."),
    ForcePackage(
        name="Sem Submarino Nuclear",
        description="Excursão: SNAC indisponível — mede o valor marginal da "
                    "propulsão nuclear na negação do mar.",
        modifications={"BLUE-SUB-N": 0}),
    ForcePackage(
        name="Reforço de Escoltas",
        description="Esquadra de superfície reforçada (+50% nos SAGs de "
                    "fragatas/corvetas) — prioriza defesa aérea de área e ASW.",
        modifications={"BLUE-SAG-S1": 1.5, "BLUE-SAG-S2": 1.5}),
    ForcePackage(
        name="Ênfase Submarina",
        description="Flotilha de submarinos convencionais reforçada (+1 SP e "
                    "dotação por submarino) — aposta em negação do mar.",
        modifications={"BLUE-SUB-1": 1.5, "BLUE-SUB-2": 1.5, "BLUE-SUB-3": 1.5}),
    ForcePackage(
        name="Ênfase Aeroespacial",
        description="Aviação de caça e patrulha reforçadas (+50%) — prioriza "
                    "superioridade aérea local e ISR.",
        modifications={"BLUE-CACA-1": 1.5, "BLUE-CACA-2": 1.5,
                       "BLUE-MPRA-1": 1.5, "BLUE-MPRA-2": 1.5}),
    ForcePackage(
        name="Defesa Costeira Reforçada",
        description="Baterias MANSUP-ER e artilharia antiaérea dobradas — "
                    "estratégia A2/AD de baixo custo.",
        modifications={"BLUE-DCOST1": 2.0, "BLUE-DCOST2": 2.0,
                       "BLUE-ADA-1": 2.0, "BLUE-ADA-2": 2.0}),
    ForcePackage(
        name="Esquadra Enxuta",
        description="Excursão de restrição orçamentária: sem SAG-2, sem "
                    "2º grupo de patrulha oceânica e sem 3º submarino.",
        modifications={"BLUE-SAG-S2": 0, "BLUE-PAT-O2": 0, "BLUE-SUB-3": 0}),
    ForcePackage(
        name="Capacidade Ciber Defensiva",
        description="Força base + contra-ciber (SEN/C2/LOG defensivos) — "
                    "protege detecção, interceptação e logística próprias "
                    "a custo baixo.",
        cyber={"C2": 2, "SEN": 3, "WPN": 1, "LOG": 2}),
    ForcePackage(
        name="Guerra Ciber Ofensiva",
        description="Força base + ciber ofensivo pesado (WPN/C2) — degrada "
                    "a eficácia cinética e a logística do adversário via "
                    "modulador Φ.",
        cyber={"C2": 3, "SEN": 2, "WPN": 4, "LOG": 3}),
    ForcePackage(
        name="A2/AD Integrada",
        description="Negação de área integrada: baterias costeiras e ADA "
                    "dobradas, submarinos reforçados e ciber defensivo — "
                    "aposta em defesa em camadas sem reforço da esquadra "
                    "de superfície.",
        modifications={"BLUE-DCOST1": 2.0, "BLUE-DCOST2": 2.0,
                       "BLUE-ADA-1": 2.0, "BLUE-ADA-2": 2.0,
                       "BLUE-SUB-1": 1.5, "BLUE-SUB-2": 1.5,
                       "BLUE-SUB-3": 1.5},
        cyber={"C2": 1, "SEN": 2, "WPN": 1, "LOG": 1}),
]


# ── Pacotes de ameaça (variantes da Força Vermelha) ──────────────────────────

THREAT_PACKAGES: list[ForcePackage] = [
    ForcePackage(
        name="Ameaça Base", side="red",
        description="Força expedicionária de referência da Operação "
                    "Atlântico Sul."),
    ForcePackage(
        name="Ameaça Reforçada", side="red",
        description="Escoltas e aviação embarcada reforçadas (+50%) — "
                    "testa a robustez do pacote azul contra um cenário "
                    "de ameaça agravado.",
        modifications={"RED-GE-1": 1.5, "RED-GE-2": 1.5, "RED-GE-3": 1.5,
                       "RED-KMF-1": 1.5, "RED-KMF-2": 1.5}),
    ForcePackage(
        name="Ameaça com Ciber", side="red",
        description="Força vermelha base com capacidade cibernética "
                    "ofensiva significativa (assimetria ciber do cenário "
                    "Bacia de Campos do naval_salvo).",
        cyber={"C2": 2, "SEN": 2, "WPN": 3, "LOG": 2}),
    ForcePackage(
        name="Ameaça Submarina", side="red",
        description="SSN reforçado e segundo submarino convencional — "
                    "pressão submarina sobre a logística azul.",
        modifications={"RED-KSN": 1.5, "RED-KS-1": 2.0}),
]
