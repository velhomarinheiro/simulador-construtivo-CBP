"""
Aprendizado por reforço — REINFORCE por auto-jogo contra o bot heurístico.

Pipeline clássico em duas etapas (mesma filosofia do AlphaGo e a evolução
natural do ``ml/train_bot.py`` do wargame):

1. **Clonagem comportamental** (módulo ``ml``) — pré-treino supervisionado
   opcional que dá ao agente uma política inicial competente (*warm start*).
2. **REINFORCE** (este módulo) — o agente joga partidas construtivas
   completas contra um oponente (bot heurístico), amostrando ações da
   softmax mascarada sobre os hexes legais; ao fim de cada episódio recebe
   uma recompensa composta (vitória + cumprimento da missão − perdas) e as
   redes são atualizadas por gradiente de política com baseline de lote e
   bônus de entropia.

A recompensa é orientada à missão do cenário: para o Azul, proteger as
FPSOs e os portos preservando a força; para o Vermelho, o espelho. Isso
permite treinar agentes que otimizam as MOEs do planejamento, e não
apenas a condição formal de vitória.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .. import hexmap as hx
from ..engine import GameState, play_game
from ..montecarlo import game_metrics
from .heuristic import HeuristicBot
from .ml import GRID_W, MLBot, MLPolicy, state_to_array


# ── Recompensa ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class RewardWeights:
    """Pesos da recompensa de episódio (normalizada aprox. em [−2, +2])."""
    win: float = 1.0        # vitória formal (±1)
    mission: float = 1.0    # proteção (Azul) / destruição (Verm.) da infra
    losses: float = 0.5     # penalidade pelas perdas próprias (% SP)


def episode_reward(metrics: dict, team: str,
                   w: RewardWeights | None = None) -> float:
    """Recompensa composta de um episódio para o time ``team``."""
    w = w or RewardWeights()
    win = 1.0 if metrics["winner"] == team else -1.0
    infra = (metrics["fpsos_surviving"] / 4.0
             + metrics["port_integrity_pct"] / 100.0) / 2.0
    mission = infra if team == "blue" else 1.0 - infra
    losses = (metrics["blue_losses_pct"] if team == "blue"
              else metrics["red_losses_pct"]) / 100.0
    return w.win * win + w.mission * mission - w.losses * losses


# ── Agente de treino (amostra ações e grava a trajetória) ────────────────────

class RLBot(MLBot):
    """
    Variante do MLBot para treino: amostra da softmax mascarada (com
    temperatura) e registra (features, ação, máscara) de cada decisão.
    O estado é codificado uma vez por fase; as decisões referenciam-no
    por índice para economizar memória.
    """

    name = "RL (REINFORCE)"

    def __init__(self, move_policy: MLPolicy, attack_policy: MLPolicy,
                 rng: np.random.Generator, temperature: float = 1.0):
        super().__init__(move_policy, attack_policy)
        self.rng = rng
        self.temperature = max(0.05, float(temperature))
        self.phase_features: list[np.ndarray] = []
        self.move_decisions: list[tuple[int, int, np.ndarray]] = []
        self.attack_decisions: list[tuple[int, int, np.ndarray]] = []

    def _sample(self, scores: np.ndarray, candidates: list[int]) -> int:
        z = scores[candidates] / self.temperature
        z -= z.max()
        p = np.exp(z)
        p /= p.sum()
        return candidates[int(self.rng.choice(len(candidates), p=p))]

    def moves(self, state: GameState, team: str) -> list[dict]:
        X = state_to_array(state.snapshot())
        self.phase_features.append(X)
        phase_id = len(self.phase_features) - 1
        scores = self.move_policy.logits(X[None, ...])[0]
        moves = []
        for unit in state.alive_units(team):
            if (unit.moved or unit.movement <= 0 or unit.category == "land"
                    or unit.is_fuel_disabled()):
                continue
            paths = self._reachable_paths(unit)
            # incluir "manter posição" no espaço de ação
            cur = (unit.col, unit.row)
            candidates = {cur: [cur], **paths}
            if len(candidates) < 2:
                continue
            cand_idx = [r * GRID_W + c for (c, r) in candidates]
            action = self._sample(scores, cand_idx)
            mask = np.zeros(scores.shape[0], dtype=bool)
            mask[cand_idx] = True
            self.move_decisions.append((phase_id, action, mask))
            dest = (action % GRID_W, action // GRID_W)
            if dest == cur:
                continue
            path = candidates[dest]
            moves.append({"unitId": unit.id,
                          "path": [{"col": c, "row": r} for c, r in path]})
        return moves

    def attacks(self, state: GameState, team: str) -> list[dict]:
        X = state_to_array(state.snapshot())
        self.phase_features.append(X)
        phase_id = len(self.phase_features) - 1
        scores = self.attack_policy.logits(X[None, ...])[0]
        enemies = [u for u in state.alive_units() if u.team != team]
        attacks = []
        for unit in state.alive_units(team):
            if not unit.can_attack():
                continue
            in_range = [e for e in enemies
                        if unit.range_against(e.category) > 0
                        and hx.hex_dist(unit.col, unit.row, e.col, e.row)
                        <= unit.range_against(e.category)]
            if not in_range:
                continue
            by_hex = {}
            for e in in_range:
                by_hex.setdefault(e.row * GRID_W + e.col, e)
            cand_idx = list(by_hex)
            if len(cand_idx) > 1:
                action = self._sample(scores, cand_idx)
                mask = np.zeros(scores.shape[0], dtype=bool)
                mask[cand_idx] = True
                self.attack_decisions.append((phase_id, action, mask))
            else:
                action = cand_idx[0]      # sem escolha → sem gradiente
            attacks.append({"attackerId": unit.id,
                            "targetId": by_hex[action].id})
        return attacks


# ── Treinador REINFORCE ───────────────────────────────────────────────────────

@dataclass
class RLTrainer:
    """
    Treina (move_policy, attack_policy) por REINFORCE em auto-jogo.

    O agente joga do lado ``team`` contra ``opponent_factory()`` (por
    padrão o bot heurístico com doutrina padrão). A vantagem de cada
    episódio é a recompensa normalizada pelo baseline do lote (média/DP).
    """
    move_policy: MLPolicy
    attack_policy: MLPolicy
    team: str = "blue"
    opponent_factory: object = HeuristicBot
    reward_weights: RewardWeights = field(default_factory=RewardWeights)
    temperature: float = 1.0
    entropy_coef: float = 0.01
    fog_of_war: bool = False
    oob: dict | None = None
    max_turns: int = 12
    seed: int = 0

    def train(self, *, iterations: int = 10, episodes_per_iter: int = 12,
              progress=None) -> dict:
        """
        Executa o laço de treino; retorna histórico por iteração
        (taxa de vitória, recompensa média, perda e entropia das redes).
        """
        rng = np.random.default_rng(self.seed)
        hist = {"iteration": [], "win_rate": [], "mean_reward": [],
                "move_loss": [], "move_entropy": [],
                "attack_loss": [], "attack_entropy": []}
        ep_seed = self.seed
        for it in range(1, iterations + 1):
            episodes = []
            rewards, wins = [], 0
            for _ in range(episodes_per_iter):
                ep_seed += 1
                agent = RLBot(self.move_policy, self.attack_policy,
                              rng=np.random.default_rng(ep_seed),
                              temperature=self.temperature)
                opponent = self.opponent_factory()
                blue, red = ((agent, opponent) if self.team == "blue"
                             else (opponent, agent))
                state = play_game(blue_bot=blue, red_bot=red, oob=self.oob,
                                  max_turns=self.max_turns, seed=ep_seed,
                                  fog_of_war=self.fog_of_war)
                m = game_metrics(state)
                r = episode_reward(m, self.team, self.reward_weights)
                episodes.append(agent)
                rewards.append(r)
                wins += int(state.winner == self.team)

            rewards = np.array(rewards, dtype=np.float32)
            adv = rewards - rewards.mean()
            std = adv.std()
            if std > 1e-6:
                adv = adv / std

            stats = {}
            for kind in ("move", "attack"):
                X_rows, actions, masks, advs = [], [], [], []
                for agent, a in zip(episodes, adv):
                    decisions = (agent.move_decisions if kind == "move"
                                 else agent.attack_decisions)
                    for phase_id, action, mask in decisions:
                        X_rows.append(agent.phase_features[phase_id])
                        actions.append(action)
                        masks.append(mask)
                        advs.append(a)
                if not actions:
                    stats[kind] = {"loss": 0.0, "entropy": 0.0}
                    continue
                policy = (self.move_policy if kind == "move"
                          else self.attack_policy)
                stats[kind] = policy.reinforce_update(
                    np.stack(X_rows), np.array(actions),
                    np.stack(masks), np.array(advs, dtype=np.float32),
                    entropy_coef=self.entropy_coef)

            hist["iteration"].append(it)
            hist["win_rate"].append(wins / episodes_per_iter)
            hist["mean_reward"].append(float(rewards.mean()))
            hist["move_loss"].append(stats["move"]["loss"])
            hist["move_entropy"].append(stats["move"]["entropy"])
            hist["attack_loss"].append(stats["attack"]["loss"])
            hist["attack_entropy"].append(stats["attack"]["entropy"])
            if progress is not None:
                progress(it, iterations, hist)
        return hist
