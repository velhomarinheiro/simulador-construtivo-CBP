"""
Análise Envoltória de Dados (DEA) para pacotes de força.

Implementa os modelos clássicos de DEA orientados a insumo:

- **CCR** (Charnes-Cooper-Rhodes) — retornos constantes de escala;
- **BCC** (Banker-Charnes-Cooper) — retornos variáveis de escala, em geral
  mais defensável para pacotes de força (dobrar o orçamento raramente
  dobra a capacidade operativa).

Cada **DMU** (*decision-making unit*) é um pacote de força; os *insumos*
são grandezas em que "menos é melhor" (custo, perdas próprias) e os
*produtos* são as MOEs em que "mais é melhor" (FPSOs sobreviventes,
integridade portuária, P(vitória)…).

O ganho metodológico sobre uma eficácia composta de pesos fixos é que a
DEA deixa os pesos **endógenos**: cada DMU é avaliada sob o conjunto de
pesos que lhe é mais favorável, eliminando a arbitrariedade do analista.
Dois produtos interpretativos importam ao planejamento de força:

- o **reference set** (peers) de um pacote ineficiente — quais pacotes
  eficientes ele deveria imitar, e em que proporção (λ);
- os **pesos ótimos** (v*, u*) — sob que critério cada pacote é bem
  avaliado, o que permite agrupar DMUs que compartilham referências.

Referência: Sakata et al. (2021), *Methodology for Extracting Knowledge
from a Gaming Simulation Using Data Envelopment Analysis*, IJAS 14(1&2).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import linprog

#: Piso aplicado a insumos/produtos: a DEA clássica exige dados positivos.
EPS = 1e-6


@dataclass
class DEAResult:
    """Resultado de uma execução de DEA sobre um conjunto de DMUs."""
    dmu_names: list[str]
    model: str                       # "CCR" | "BCC"
    input_names: list[str]
    output_names: list[str]
    X: np.ndarray                    # (n, m) insumos
    Y: np.ndarray                    # (n, s) produtos
    efficiency: np.ndarray           # (n,) θ ∈ (0, 1]
    peers: list[dict[str, float]]    # reference set por DMU: {nome: λ}
    input_weights: np.ndarray        # (n, m) v*
    output_weights: np.ndarray       # (n, s) u*
    status: list[str] = field(default_factory=list)

    @property
    def is_efficient(self) -> np.ndarray:
        return self.efficiency >= 1.0 - 1e-6

    def targets(self, i: int) -> dict[str, float]:
        """Insumos-alvo da DMU ``i`` (θ·x): a redução radial necessária."""
        return {name: float(self.efficiency[i] * self.X[i, j])
                for j, name in enumerate(self.input_names)}

    def reference_groups(self) -> dict[tuple, list[str]]:
        """
        Agrupa DMUs pela **assinatura do reference set** (conjunto de peers
        eficientes que referenciam). DMUs de um mesmo grupo são avaliadas
        sob critério semelhante — a leitura de Sakata et al. (2021).
        DMUs eficientes formam grupo próprio (referenciam a si mesmas).
        """
        groups: dict[tuple, list[str]] = {}
        for i, name in enumerate(self.dmu_names):
            sig = tuple(sorted(self.peers[i]))
            groups.setdefault(sig, []).append(name)
        return groups


def _sanitize(M: np.ndarray) -> np.ndarray:
    """DEA exige dados positivos; aplica piso e zera não-finitos."""
    M = np.asarray(M, dtype=float).copy()
    M[~np.isfinite(M)] = EPS
    return np.maximum(M, EPS)


def _envelopment(X: np.ndarray, Y: np.ndarray, o: int, bcc: bool):
    """
    Forma envelope (orientada a insumo) para a DMU ``o``:

        min θ
        s.a.  Σ_j λ_j x_ij ≤ θ x_io      (i = 1..m)
              Σ_j λ_j y_rj ≥ y_ro        (r = 1..s)
              [BCC] Σ_j λ_j = 1
              λ ≥ 0

    Retorna (θ, λ, status). Fornece θ e o reference set.
    """
    n, m = X.shape
    s = Y.shape[1]
    # variáveis: [θ, λ_1..λ_n]
    c = np.zeros(1 + n)
    c[0] = 1.0

    # insumos:  Σ λ_j x_ij − θ x_io ≤ 0
    A_in = np.hstack([(-X[o]).reshape(m, 1), X.T])          # (m, 1+n)
    b_in = np.zeros(m)
    # produtos: −Σ λ_j y_rj ≤ −y_ro
    A_out = np.hstack([np.zeros((s, 1)), -Y.T])             # (s, 1+n)
    b_out = -Y[o]

    A_ub = np.vstack([A_in, A_out])
    b_ub = np.concatenate([b_in, b_out])

    A_eq = b_eq = None
    if bcc:                                                  # Σ λ = 1
        A_eq = np.concatenate([[0.0], np.ones(n)]).reshape(1, -1)
        b_eq = np.array([1.0])

    bounds = [(0.0, None)] * (1 + n)
    r = linprog(c, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq,
                bounds=bounds, method="highs")
    if not r.success:
        return 1.0, np.zeros(n), r.message
    theta = float(np.clip(r.x[0], 0.0, 1.0))
    lam = np.asarray(r.x[1:], dtype=float)
    return theta, lam, "ok"


def _multiplier(X: np.ndarray, Y: np.ndarray, o: int, bcc: bool):
    """
    Forma multiplicadora (dual) para a DMU ``o`` — fornece os pesos ótimos:

        max  Σ_r u_r y_ro  [− u₀]
        s.a. Σ_i v_i x_io = 1
             Σ_r u_r y_rj − Σ_i v_i x_ij [− u₀] ≤ 0   (j = 1..n)
             u, v ≥ 0   [u₀ livre no BCC]

    Retorna (u*, v*).
    """
    n, m = X.shape
    s = Y.shape[1]
    nvar = s + m + (1 if bcc else 0)

    c = np.zeros(nvar)
    c[:s] = -Y[o]                       # maximizar → minimizar o negativo
    if bcc:
        c[-1] = 1.0                     # −(−u₀) = +u₀

    A_ub = np.zeros((n, nvar))
    A_ub[:, :s] = Y
    A_ub[:, s:s + m] = -X
    if bcc:
        A_ub[:, -1] = -1.0
    b_ub = np.zeros(n)

    A_eq = np.zeros((1, nvar))
    A_eq[0, s:s + m] = X[o]
    b_eq = np.array([1.0])

    bounds = [(0.0, None)] * (s + m) + ([(None, None)] if bcc else [])
    r = linprog(c, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq,
                bounds=bounds, method="highs")
    if not r.success:
        return np.zeros(s), np.zeros(m)
    return np.asarray(r.x[:s]), np.asarray(r.x[s:s + m])


def run_dea(dmu_names: list[str], X, Y,
            input_names: list[str], output_names: list[str],
            model: str = "CCR") -> DEAResult:
    """
    Executa a DEA orientada a insumo sobre as DMUs informadas.

    Parameters
    ----------
    dmu_names : nomes das DMUs (pacotes de força)
    X : (n, m) insumos — "menos é melhor" (custo, perdas próprias…)
    Y : (n, s) produtos — "mais é melhor" (FPSOs, integridade, P(vitória)…)
    model : "CCR" (retornos constantes) ou "BCC" (retornos variáveis)

    Returns
    -------
    DEAResult com θ, reference sets (λ > 0) e pesos ótimos por DMU.
    """
    model = model.upper()
    if model not in ("CCR", "BCC"):
        raise ValueError(f"modelo deve ser 'CCR' ou 'BCC'; recebido {model!r}")
    X = _sanitize(X)
    Y = _sanitize(Y)
    if X.ndim != 2 or Y.ndim != 2 or X.shape[0] != Y.shape[0]:
        raise ValueError("X e Y devem ser 2-D com o mesmo número de DMUs")
    if len(dmu_names) != X.shape[0]:
        raise ValueError("dmu_names não corresponde ao número de linhas de X")

    bcc = model == "BCC"
    n = X.shape[0]
    eff = np.ones(n)
    peers: list[dict[str, float]] = []
    U = np.zeros((n, Y.shape[1]))
    V = np.zeros((n, X.shape[1]))
    status: list[str] = []

    for o in range(n):
        theta, lam, st = _envelopment(X, Y, o, bcc)
        eff[o] = theta
        peers.append({dmu_names[j]: float(lam[j])
                      for j in range(n) if lam[j] > 1e-6})
        u, v = _multiplier(X, Y, o, bcc)
        U[o], V[o] = u, v
        status.append(st)

    return DEAResult(dmu_names=list(dmu_names), model=model,
                     input_names=list(input_names),
                     output_names=list(output_names),
                     X=X, Y=Y, efficiency=eff, peers=peers,
                     input_weights=V, output_weights=U, status=status)


#: Insumos disponíveis — grandezas em que **menos é melhor**.
DEA_INPUTS: dict[str, callable] = {
    "Custo (UC)": lambda r: r["cost"],
    "Perdas Azul (%SP)": lambda r: r["summary"]["mean_blue_losses"],
    "Duração da campanha (dias)": lambda r: r["summary"]["mean_turns"],
}

#: Produtos disponíveis — MOEs em que **mais é melhor**.
DEA_OUTPUTS: dict[str, callable] = {
    "FPSOs sobreviventes": lambda r: r["summary"]["mean_fpsos_surviving"],
    "Integridade portuária (%)": lambda r: r["summary"]["mean_port_integrity"],
    "P(vitória Azul)": lambda r: r["summary"]["p_blue_win"],
    "Atrito imposto à Vermelha (%SP)": lambda r: r["summary"]["mean_red_losses"],
}


def build_matrices(results: list[dict], input_labels: list[str],
                   output_labels: list[str]):
    """
    Monta (nomes, X, Y) a partir dos resultados da análise CBP — a lista
    de dicts com ``package``, ``cost`` e ``summary`` produzida na página.
    """
    if not input_labels or not output_labels:
        raise ValueError("selecione ao menos um insumo e um produto")
    names = [r["package"] for r in results]
    X = np.array([[DEA_INPUTS[l](r) for l in input_labels] for r in results],
                 dtype=float)
    Y = np.array([[DEA_OUTPUTS[l](r) for l in output_labels] for r in results],
                 dtype=float)
    return names, X, Y


def discrimination_note(n_dmus: int, n_inputs: int, n_outputs: int) -> str | None:
    """
    Alerta de poder discriminatório: regra prática n ≥ 3·(m+s). Abaixo
    dela, a DEA tende a classificar quase tudo como eficiente.
    """
    minimo = 3 * (n_inputs + n_outputs)
    if n_dmus >= minimo:
        return None
    return (f"Poder discriminatório limitado: {n_dmus} DMUs para "
            f"{n_inputs} insumos + {n_outputs} produtos (regra prática: "
            f"n ≥ 3·(m+s) = {minimo}). Reduza dimensões ou acrescente "
            f"pacotes/réplicas para uma leitura mais robusta.")
