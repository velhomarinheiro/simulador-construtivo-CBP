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


@dataclass
class ForcePackage:
    """
    Pacote de força alternativo (opção de capacidade).

    ``modifications`` mapeia unit_id → fator de escala aplicado ao grupo:
    0 remove o grupo; 1 mantém; 1.5 reforça em ~50% (SP, armas e
    capacidades escalados). ``additions`` são specs completas de novos
    grupos-tarefa a incluir.
    """
    name: str
    description: str = ""
    modifications: dict = field(default_factory=dict)
    additions: list = field(default_factory=list)
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


def package_cost(oob: dict, pkg: ForcePackage) -> float:
    """Custo ilustrativo do pacote (grupos presentes × escala)."""
    total = 0.0
    for spec in oob["forces"][pkg.side]:
        base = UNIT_COSTS.get(spec["id"], 0.0)
        factor = pkg.modifications.get(spec["id"], 1.0)
        if factor > 0:
            total += base * factor
    for extra in pkg.additions:
        total += float(extra.get("cost", UNIT_COSTS.get(extra.get("id"), 0.0)))
    return total


def capability_profile(oob: dict, side: str = "blue") -> dict[str, float]:
    """Agrega o perfil de capacidades de uma força (p/ gráfico radar)."""
    profile = {}
    for area, fn in CAPABILITY_AREAS.items():
        profile[area] = float(sum(fn(u) for u in oob["forces"][side]))
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
]
