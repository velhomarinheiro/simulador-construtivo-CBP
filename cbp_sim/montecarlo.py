"""
Execução em lote (Monte Carlo) de partidas construtivas e cálculo de MOEs.

Medidas de eficácia (MOEs) alinhadas aos objetivos do cenário Operação
Atlântico Sul (defesa de infraestruturas críticas nas bacias de Campos e
Santos e portos da região):

- P(vitória Azul), razão de decisão (vitória × limite operacional)
- Sobrevivência das FPSOs e integridade dos portos
- Perdas de cada força (fração de SP) e razão de troca
- Duração da campanha (dias de jogo)
- Progresso médio nos objetivos de cada força
"""

from __future__ import annotations

import copy
from typing import Callable, Optional

import numpy as np
import pandas as pd

from .engine import GameState, OBJECTIVE_IDS, play_game, load_order_of_battle


def _team_sp(state: GameState, team: str, initial: bool = False) -> float:
    return sum((u.max_hp if initial else max(0.0, u.hp))
               for u in state.units if u.team == team)


def game_metrics(state: GameState) -> dict:
    """Extrai as MOEs de uma partida encerrada."""
    obj = state.compute_objectives()
    fpso_ids = OBJECTIVE_IDS["redTargets"]["fpsos"]
    port_ids = OBJECTIVE_IDS["redTargets"]["ports"]
    fpsos = [state.unit(i) for i in fpso_ids]
    fpsos = [u for u in fpsos if u is not None]
    ports = [state.unit(i) for i in port_ids]
    ports = [u for u in ports if u is not None]

    port_max = sum(u.max_hp for u in ports) or 1.0
    blue_sp0, red_sp0 = _team_sp(state, "blue", True), _team_sp(state, "red", True)
    blue_sp, red_sp = _team_sp(state, "blue"), _team_sp(state, "red")
    blue_loss = 1.0 - blue_sp / blue_sp0 if blue_sp0 else 0.0
    red_loss = 1.0 - red_sp / red_sp0 if red_sp0 else 0.0

    return {
        "winner": state.winner,
        "blue_win": int(state.winner == "blue"),
        "end_reason": state.end_reason,
        "turns": state.turn,
        "fpsos_surviving": sum(1 for u in fpsos if u.hp > 0),
        "port_integrity_pct": 100.0 * sum(max(0.0, u.hp) for u in ports) / port_max,
        "blue_losses_pct": 100.0 * blue_loss,
        "red_losses_pct": 100.0 * red_loss,
        "exchange_ratio": (red_loss / blue_loss) if blue_loss > 1e-9 else np.inf,
        "blue_obj_achieved": obj["blue"]["achieved"],
        "red_obj_achieved": obj["red"]["achieved"],
        "n_engagements": len(state.engagement_records),
    }


def run_batch(*,
              blue_bot_factory: Callable[[], object],
              red_bot_factory: Callable[[], object],
              n_runs: int = 30,
              oob: Optional[dict] = None,
              max_turns: int = 12,
              stochastic: bool = True,
              chi: float = 0.5,
              base_seed: int = 0,
              collect_events: bool = False,
              progress: Optional[Callable[[int, int], None]] = None):
    """
    Roda ``n_runs`` replicações bot × bot com sementes controladas.

    Retorna (DataFrame de MOEs por replicação, lista de trilhas de eventos).
    """
    oob = oob or load_order_of_battle()
    rows, event_trails = [], []
    for k in range(n_runs):
        state = play_game(
            blue_bot=blue_bot_factory(), red_bot=red_bot_factory(),
            oob=copy.deepcopy(oob), max_turns=max_turns,
            stochastic=stochastic, chi=chi, seed=base_seed + k)
        m = game_metrics(state)
        m["run"] = k
        m["seed"] = base_seed + k
        rows.append(m)
        if collect_events:
            event_trails.append({"run": k, "winner": state.winner,
                                 "events": state.events})
        if progress is not None:
            progress(k + 1, n_runs)
    df = pd.DataFrame(rows)
    return df, event_trails


def summarize(df: pd.DataFrame) -> dict:
    """Sumário agregado das MOEs de um lote (com IC 95% p/ P(vitória))."""
    n = len(df)
    p = df["blue_win"].mean() if n else 0.0
    se = np.sqrt(p * (1 - p) / n) if n else 0.0
    fin = df["exchange_ratio"].replace([np.inf, -np.inf], np.nan)
    return {
        "n_runs": n,
        "p_blue_win": p,
        "p_blue_win_ci95": (max(0.0, p - 1.96 * se), min(1.0, p + 1.96 * se)),
        "mean_turns": df["turns"].mean() if n else 0.0,
        "mean_fpsos_surviving": df["fpsos_surviving"].mean() if n else 0.0,
        "mean_port_integrity": df["port_integrity_pct"].mean() if n else 0.0,
        "mean_blue_losses": df["blue_losses_pct"].mean() if n else 0.0,
        "mean_red_losses": df["red_losses_pct"].mean() if n else 0.0,
        "mean_exchange_ratio": float(fin.mean()) if n else 0.0,
        "p_timeout": (df["end_reason"] == "timeout").mean() if n else 0.0,
    }
