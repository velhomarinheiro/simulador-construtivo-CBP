"""
Domínio cibernético (X) — modulador Φ da equação de salva multidomínio.

Segue o modelo do ``naval_salvo`` (cyber.py / eq. 12 do paper SIGE 2026):
o efeito principal do ciber **não** é atrito cinético, e sim a modulação
da eficácia das unidades cinéticas do oponente via fator Φ ∈ (0, 1]:

    Φ(R) = 1 / [1 + (R / r₀)^k]

onde R é a razão de força cibernética do oponente no canal considerado,
r₀ é a referência de meia-degradação (Φ = 0.5 quando R = r₀) e k a
inclinação da sigmoide.

Cada força possui um estoque ciber por subtipo (como em
``BACIA_CAMPOS_PARAMETERS`` do naval_salvo):

    C2  — comando e controle      → degrada eficácia ofensiva (T_atq)
    SEN — sensores / ISR          → degrada detecção e interceptação
    WPN — sistemas de armas       → degrada ofensiva e interceptação
    LOG — logística               → degrada recompletamento/reabastecimento

O estoque próprio no mesmo subtipo atua como contra-ciber (defesa),
reduzindo a razão efetiva R = ofensiva_oponente / (1 + defesa_própria).
"""

from __future__ import annotations

from dataclasses import dataclass, field

CYBER_SUBTYPES = ("C2", "SEN", "WPN", "LOG")

# Pesos subtipo → canal de efeito (inspirados no ChannelPhi do naval_salvo)
CHANNEL_WEIGHTS = {
    # canal          C2    SEN   WPN   LOG
    "offense":     {"C2": 0.5, "SEN": 0.0, "WPN": 0.5, "LOG": 0.0},
    "defense":     {"C2": 0.0, "SEN": 0.5, "WPN": 0.5, "LOG": 0.0},
    "detection":   {"C2": 0.3, "SEN": 0.7, "WPN": 0.0, "LOG": 0.0},
    "logistics":   {"C2": 0.2, "SEN": 0.0, "WPN": 0.0, "LOG": 0.8},
}


def phi_sigmoid(R: float, r0: float = 1.0, k: float = 2.0) -> float:
    """Φ(R) = 1/[1+(R/r₀)^k]; Φ(0) = 1 (sem ciber oponente, sem modulação)."""
    if R <= 0.0:
        return 1.0
    return 1.0 / (1.0 + (R / r0) ** k)


@dataclass(frozen=True)
class CyberForce:
    """Estoque cibernético de uma força, por subtipo."""
    c2: float = 0.0
    sen: float = 0.0
    wpn: float = 0.0
    log: float = 0.0

    def stock(self, subtype: str) -> float:
        return {"C2": self.c2, "SEN": self.sen,
                "WPN": self.wpn, "LOG": self.log}[subtype]

    @property
    def total(self) -> float:
        return self.c2 + self.sen + self.wpn + self.log

    def as_dict(self) -> dict:
        return {"C2": self.c2, "SEN": self.sen,
                "WPN": self.wpn, "LOG": self.log}

    @classmethod
    def from_dict(cls, d: dict | None) -> "CyberForce":
        d = d or {}
        return cls(c2=float(d.get("C2", 0)), sen=float(d.get("SEN", 0)),
                   wpn=float(d.get("WPN", 0)), log=float(d.get("LOG", 0)))


@dataclass(frozen=True)
class PhiFactors:
    """Fatores Φ que uma força sofre (calculados do ciber do oponente)."""
    offense: float = 1.0     # multiplica a letalidade das próprias salvas
    defense: float = 1.0     # multiplica a própria capacidade de interceptação
    detection: float = 1.0   # multiplica os próprios alcances de detecção
    logistics: float = 1.0   # multiplica recompletamento/reabastecimento


def compute_phi(own: CyberForce, opponent: CyberForce, *,
                r0: float = 1.0, k: float = 2.0) -> PhiFactors:
    """
    Fatores Φ sofridos por uma força dado o estoque ciber do oponente.

    Para cada canal: R = Σ_s w_s·oponente_s / (1 + Σ_s w_s·próprio_s),
    Φ_canal = phi_sigmoid(R). O estoque próprio no mesmo canal atua como
    contra-ciber, elevando o denominador (defesa cibernética).
    """
    out = {}
    for channel, weights in CHANNEL_WEIGHTS.items():
        atk = sum(w * opponent.stock(s) for s, w in weights.items())
        dfn = sum(w * own.stock(s) for s, w in weights.items())
        R = atk / (1.0 + dfn)
        out[channel] = phi_sigmoid(R, r0=r0, k=k)
    return PhiFactors(offense=out["offense"], defense=out["defense"],
                      detection=out["detection"], logistics=out["logistics"])
