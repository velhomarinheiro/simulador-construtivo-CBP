"""
Adjudicação de engajamentos pela equação de salva multidomínio.

Segue o modelo do pacote ``naval_salvo`` (equação canônica em regime
pulsado, forma de Johns-Pilnick-Hughes 2001 generalizada por domínios):

    ΔSP_alvo = (1/s) · 1^{(d', d)} · [ T_atq − T_def ]_+

onde

    T_atq = n_lançados · η_of · p_of      (mísseis "bem apontados")
    T_def = z_int · η_def · p_int         (interceptação da pilha defensora)
    1^{(d', d)}  = coeficiente de admissibilidade entre o domínio do
                   atacante (d') e o do alvo (d) — matriz 5×5 com nível
                   marginal χ calibrável
    s            = poder de permanência (staying power); aqui o SP da
                   unidade já é expresso em "hits absorvíveis", i.e. s ≡ 1
                   por ponto de SP, como em Hughes (1995) com b1 = SP.

A letalidade por vazador (η_of·p_of) e a probabilidade de interceptação
(η_def·p_int) são calibradas a partir das tabelas de dano d6 do wargame
Operação Atlântico Sul (shared/combat_config.js), de modo que o valor
esperado do modo determinístico reproduz o balanceamento do jogo original
e o modo estocástico reproduz exatamente sua distribuição de dados.

Domínios: S (superfície), U (submarino), A (aéreo), C (costeiro/terrestre),
X (cibernético — reservado para extensão).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

DATA_DIR = Path(__file__).parent / "data"

with open(DATA_DIR / "combat_config.json", encoding="utf-8") as _f:
    COMBAT_CONFIG = json.load(_f)

WEAPON_PROFILES: dict = COMBAT_CONFIG["weaponProfiles"]
DAMAGE_TABLES: dict = COMBAT_CONFIG["damageTables"]

WEAPON_LABELS = {w: p.get("label", w.upper()) for w, p in WEAPON_PROFILES.items()}

# Tamanho de salva padrão por tipo de arma (espelho de SALVO_SIZE do server.js).
SALVO_SIZE = {"ascm": 2, "mss": 2, "torpedo": 1, "lacm": 1, "asbm": 1, "raid": 1}

# ── Domínios e admissibilidade ───────────────────────────────────────────────

DOMAINS = ["S", "U", "A", "C", "X"]
DOMAIN_INDEX = {d: i for i, d in enumerate(DOMAINS)}
DOMAIN_LABELS = {
    "S": "Superfície", "U": "Submarino", "A": "Aéreo",
    "C": "Costeiro/Terrestre", "X": "Cibernético",
}

CATEGORY_TO_DOMAIN = {
    "surface": "S", "submarine": "U", "air": "A",
    "land": "C", "specops": "C", "cyber": "X",
}

DEFAULT_CHI = 0.5


def canonical_matrix(chi: float = DEFAULT_CHI) -> np.ndarray:
    """
    Matriz canônica 5×5 de admissibilidade (naval_salvo, doc 1.4 §2.2).

    Linhas = domínio do atacante; colunas = domínio do defensor.

        Atacante \\ Defensor |  S    U    A    C    X
        --------------------+------------------------
        S (superfície)      |  1    χ    χ    1    χ
        U (submarino)       |  1    1    0    χ    0
        A (aéreo)           |  1    χ    1    1    χ
        C (costeiro)        |  1    χ    χ    1    χ
        X (cibernético)     |  χ    0    χ    χ    1
    """
    c = float(chi)
    return np.array([
        # S    U    A    C    X
        [1.0, c,   c,   1.0, c],    # S
        [1.0, 1.0, 0.0, c,   0.0],  # U
        [1.0, c,   1.0, 1.0, c],    # A
        [1.0, c,   c,   1.0, c],    # C
        [c,   0.0, c,   c,   1.0],  # X
    ], dtype=np.float64)


def admissibility(attacker_category: str, defender_category: str,
                  chi: float = DEFAULT_CHI,
                  matrix: np.ndarray | None = None) -> float:
    """Coeficiente 1^{(d', d)} para um par atacante→defensor."""
    M = matrix if matrix is not None else canonical_matrix(chi)
    da = CATEGORY_TO_DOMAIN.get(attacker_category, "S")
    dd = CATEGORY_TO_DOMAIN.get(defender_category, "S")
    return float(M[DOMAIN_INDEX[da], DOMAIN_INDEX[dd]])


# ── Calibração das tabelas d6 → letalidade esperada ─────────────────────────

def _expected_damage(table: dict) -> float:
    """Valor esperado de dano por disparo, dado uma linha da tabela d6."""
    total = 0.0
    for face in range(1, 7):
        v = table.get(str(face), 0)
        total += 3.5 if v == "1d6" else float(v)
    return total / 6.0


def lethality(team: str, weapon_type: str, target_category: str) -> float:
    """η_of·p_of — dano esperado em SP por míssil/disparo vazador."""
    profile = WEAPON_PROFILES.get(weapon_type)
    if not profile:
        return 0.0
    table = (DAMAGE_TABLES.get(team, {})
             .get(profile["damageProfile"], {})
             .get(target_category))
    if not table:
        return 0.0
    return _expected_damage(table)


def intercept_probability(team: str, defense_weapon: str) -> float:
    """η_def·p_int — probabilidade de um interceptador abater um míssil."""
    profile = WEAPON_PROFILES.get(defense_weapon)
    if not profile:
        return 0.0
    table = (DAMAGE_TABLES.get(team, {})
             .get(profile["damageProfile"], {})
             .get("missile"))
    if not table:
        return 0.0
    # Interceptação é sucesso/fracasso: prob. de dano > 0.
    hits = sum(1 for face in range(1, 7) if table.get(str(face), 0) not in (0, "0"))
    return hits / 6.0


def _roll_damage(table: dict, rng: np.random.Generator,
                 advantage: bool = False) -> tuple[int, float]:
    """Rola a tabela d6 (com vantagem = 2d6 pega maior); retorna (roll, dano)."""
    roll = int(rng.integers(1, 7))
    if advantage:
        roll = max(roll, int(rng.integers(1, 7)))
    v = table.get(str(roll), 0)
    dmg = float(rng.integers(1, 7)) if v == "1d6" else float(v)
    return roll, dmg


# ── Resolução de um engajamento ──────────────────────────────────────────────

@dataclass
class SalvoOutcome:
    """Resultado da adjudicação de uma salva (um atacante → um alvo)."""
    ok: bool
    reason: str = ""
    weapon_type: str = ""
    weapon_label: str = ""
    launched: int = 0
    chi: float = 1.0
    t_atq: float = 0.0            # T_atq — poder ofensivo da salva (SP esperado)
    t_def: float = 0.0            # T_def — poder de interceptação (mísseis abatidos esp.)
    intercepted: float = 0.0
    leakers: float = 0.0
    damage: float = 0.0           # dano em SP efetivamente aplicado
    destroyed: bool = False
    remaining_hp: float = 0.0
    detail: dict = field(default_factory=dict)


def resolve_salvo(
    *,
    attacker,
    defender,
    defenders_stack: list | None = None,
    weapon_type: str,
    amount: int,
    distance: int,
    rng: np.random.Generator,
    stochastic: bool = True,
    chi: float = DEFAULT_CHI,
    adm_matrix: np.ndarray | None = None,
    advantage: bool = False,
    phi_offense: float = 1.0,
    phi_defense: float = 1.0,
) -> SalvoOutcome:
    """
    Adjudica uma salva pelo modelo multidomínio.

    ``attacker`` / ``defender`` são unidades do motor (``engine.Unit``).
    ``defenders_stack`` é a pilha defensora (grupo-tarefa no mesmo hex) que
    soma capacidade de interceptação; se None, apenas o alvo defende.

    ``phi_offense`` (Φ sofrido pelo atacante) modula a letalidade da salva
    e ``phi_defense`` (Φ sofrido pelo defensor) modula a interceptação —
    efeitos do domínio cibernético (módulo ``cyber``), conforme o
    modulador Φ do naval_salvo.

    Modos:
    - ``stochastic=True``  — interceptação e dano sorteados das tabelas d6
      do jogo original (mecânica idêntica ao wargame OAS).
    - ``stochastic=False`` — regime determinístico da equação de salva:
      dano = χ·Φ·[n·η_of − z·η_def·λ]_+ (valores esperados).
    """
    profile = WEAPON_PROFILES.get(weapon_type)
    if not profile:
        return SalvoOutcome(ok=False, reason=f"Arma desconhecida: {weapon_type}")

    if defender.category not in profile["targets"]:
        return SalvoOutcome(
            ok=False, reason=f"{weapon_type} não engaja alvo {defender.category}")

    rng_range = attacker.weapon_range(weapon_type)
    if distance > rng_range:
        return SalvoOutcome(ok=False, reason="Fora de alcance")

    qty = attacker.weapon_quantity(weapon_type)
    if qty <= 0:
        return SalvoOutcome(ok=False, reason="Sem armamento disponível")

    launched = min(amount, qty) if profile.get("expendable") else 1
    attacker.spend_weapon(weapon_type, launched)

    chi_coef = admissibility(attacker.category, defender.category,
                             chi=chi, matrix=adm_matrix)
    if chi_coef <= 0.0:
        return SalvoOutcome(
            ok=False, weapon_type=weapon_type, launched=launched,
            reason=("Engajamento estruturalmente inadmissível "
                    f"({CATEGORY_TO_DOMAIN[attacker.category]}→"
                    f"{CATEGORY_TO_DOMAIN[defender.category]}, χ=0)"))

    stack = defenders_stack if defenders_stack is not None else [defender]

    # ── T_def: capacidade de interceptação agrupada da pilha ────────────────
    det = {"interception": []}
    remaining = float(launched)
    expected_intercepted = 0.0
    for def_weapon in profile.get("interceptableBy", []):
        capacity = sum(u.weapon_quantity(def_weapon) for u in stack)
        if capacity <= 0:
            continue
        team_def = stack[0].team
        p_int = intercept_probability(team_def, def_weapon) * phi_defense
        shots = min(remaining, float(capacity))
        if stochastic:
            kills = float(rng.binomial(int(shots), p_int)) if shots >= 1 else 0.0
        else:
            kills = shots * p_int
        kills = min(kills, remaining)
        expected_intercepted += kills
        remaining -= kills
        det["interception"].append(
            {"weapon": def_weapon, "capacity": capacity,
             "shots": shots, "intercepted": kills})
        if remaining <= 0:
            break

    leakers = max(0.0, remaining)

    # ── T_atq: dano dos vazadores ────────────────────────────────────────────
    lam = lethality(attacker.team, weapon_type, defender.category)
    if stochastic:
        table = (DAMAGE_TABLES.get(attacker.team, {})
                 .get(profile["damageProfile"], {})
                 .get(defender.category, {}))
        damage = 0.0
        rolls = []
        for _ in range(int(round(leakers))):
            roll, dmg = _roll_damage(table, rng, advantage=advantage)
            rolls.append(roll)
            damage += dmg
        det["rolls"] = rolls
        # admissibilidade marginal e Φ ciber atenuam o dano
        damage *= chi_coef * phi_offense
    else:
        damage = chi_coef * phi_offense * leakers * lam
        if advantage:
            damage *= 1.15            # bônus de iniciativa (aprox. 2d6-take-max)

    t_atq = chi_coef * phi_offense * launched * lam
    t_def = chi_coef * expected_intercepted * lam

    # Aplica dano: SP da unidade é o poder de permanência (s ≡ 1 hit/SP).
    damage = min(damage, defender.hp)
    defender.hp = max(0.0, defender.hp - damage)

    return SalvoOutcome(
        ok=True,
        weapon_type=weapon_type,
        weapon_label=profile.get("label", weapon_type.upper()),
        launched=launched,
        chi=chi_coef,
        t_atq=t_atq,
        t_def=t_def,
        intercepted=expected_intercepted,
        leakers=leakers,
        damage=damage,
        destroyed=defender.hp <= 0,
        remaining_hp=defender.hp,
        detail=det,
    )
