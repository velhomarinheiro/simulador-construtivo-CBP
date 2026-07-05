"""
Bot de aprendizado de máquina — clonagem comportamental (imitation learning).

Inspirado em ``wargame-naval/ml/train_bot.py``: o estado do tabuleiro é
codificado como um tensor de 9 canais × 10 × 16 (presença, equipe, SP
normalizado, categoria one-hot, combustível e armas normalizados) e duas
redes prevêem, respectivamente, o hex de destino de movimento (move_net)
e o hex do alvo de ataque (attack_net) como classificação sobre os 160
hexes da grade.

Implementação em numpy puro (MLP com Adam) para dispensar PyTorch no
deploy Streamlit; o dataset vem de partidas construtivas (self-play do
bot heurístico ou partidas anteriores), com opção de imitar apenas o
lado vencedor.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field

import numpy as np

from .. import hexmap as hx
from ..engine import GameState, Unit
from .heuristic import HeuristicBot

GRID_H, GRID_W = hx.GRID_H, hx.GRID_W
N_CHANNELS = 9
N_HEX = GRID_H * GRID_W
INPUT_DIM = N_CHANNELS * N_HEX


# ── Features (espelho de state_to_array do train_bot.py) ─────────────────────

def state_to_array(state_snapshot: dict) -> np.ndarray:
    """Converte um snapshot de estado em tensor (9, 10, 16)."""
    grid = np.zeros((N_CHANNELS, GRID_H, GRID_W), dtype=np.float32)
    for u in state_snapshot["units"]:
        if u["hp"] <= 0:
            continue
        c, r = u["col"], u["row"]
        if not (0 <= c < GRID_W and 0 <= r < GRID_H):
            continue
        team_sign = 1.0 if u["team"] == "blue" else -1.0
        cat = u.get("category", "")
        fuel = u.get("fuel") or {}
        weapons = u.get("weapons") or {}
        wpn_total = sum(w.get("quantity", 0) for w in weapons.values()
                        if isinstance(w, dict))
        grid[0, r, c] = 1.0
        grid[1, r, c] = team_sign
        grid[2, r, c] = u["hp"] / u["maxHp"] if u["maxHp"] else 0.0
        grid[3, r, c] = float(cat == "surface")
        grid[4, r, c] = float(cat == "submarine")
        grid[5, r, c] = float(cat == "air")
        grid[6, r, c] = float(cat == "land")
        grid[7, r, c] = (fuel.get("current", 1) or 1) / (fuel.get("max", 1) or 1)
        grid[8, r, c] = min(wpn_total / 20.0, 1.0)
    return grid


def build_training_samples(events: list[dict],
                           winner: str | None = None,
                           imitate_winner_only: bool = False):
    """
    Extrai exemplos (X, hex_destino) e (X, hex_alvo) da trilha de eventos
    de uma partida (``GameState.events``).
    """
    move_samples: list[tuple[np.ndarray, int]] = []
    attack_samples: list[tuple[np.ndarray, int]] = []
    for ev in events:
        team = ev.get("team")
        if imitate_winner_only and winner is not None and team != winner:
            continue
        if ev["event"] == "movement_committed":
            X = state_to_array(ev["state"])
            for mv in ev.get("moves") or []:
                path = mv.get("path") or []
                if len(path) < 2:
                    continue
                dst = path[-1]
                dc, dr = dst["col"], dst["row"]
                if 0 <= dc < GRID_W and 0 <= dr < GRID_H:
                    move_samples.append((X, dr * GRID_W + dc))
        elif ev["event"] == "attacks_declared":
            atks = ev.get("attacks") or []
            if not atks:
                continue
            X = state_to_array(ev["state"])
            pos = {u["id"]: (u["col"], u["row"])
                   for u in ev["state"]["units"] if u["hp"] > 0}
            for atk in atks:
                tid = atk.get("targetId")
                if tid in pos:
                    tc, tr = pos[tid]
                    attack_samples.append((X, tr * GRID_W + tc))
    return move_samples, attack_samples


# ── Rede MLP em numpy (com Adam) ─────────────────────────────────────────────

@dataclass
class MLPolicy:
    """MLP 1440 → hidden → 160 treinado por entropia cruzada."""
    hidden: int = 256
    lr: float = 1e-3
    seed: int = 42
    W1: np.ndarray = field(default=None, repr=False)
    b1: np.ndarray = field(default=None, repr=False)
    W2: np.ndarray = field(default=None, repr=False)
    b2: np.ndarray = field(default=None, repr=False)
    trained_epochs: int = 0

    def __post_init__(self):
        if self.W1 is None:
            rng = np.random.default_rng(self.seed)
            s1 = np.sqrt(2.0 / INPUT_DIM)
            s2 = np.sqrt(2.0 / self.hidden)
            self.W1 = rng.normal(0, s1, (INPUT_DIM, self.hidden)).astype(np.float32)
            self.b1 = np.zeros(self.hidden, dtype=np.float32)
            self.W2 = rng.normal(0, s2, (self.hidden, N_HEX)).astype(np.float32)
            self.b2 = np.zeros(N_HEX, dtype=np.float32)
        self._adam_state = None

    # forward
    def logits(self, X: np.ndarray) -> np.ndarray:
        """X: (batch, 9, 10, 16) ou (batch, 1440) → (batch, 160)."""
        X = X.reshape(X.shape[0], -1).astype(np.float32)
        h = np.maximum(0.0, X @ self.W1 + self.b1)
        return h @ self.W2 + self.b2

    def _adam_init(self):
        self._adam_state = {
            k: (np.zeros_like(getattr(self, k)), np.zeros_like(getattr(self, k)))
            for k in ("W1", "b1", "W2", "b2")}
        self._adam_t = 0

    def _adam_step(self, grads: dict):
        if self._adam_state is None:
            self._adam_init()
        self._adam_t += 1
        beta1, beta2, eps = 0.9, 0.999, 1e-8
        for k, g in grads.items():
            m, v = self._adam_state[k]
            m[:] = beta1 * m + (1 - beta1) * g
            v[:] = beta2 * v + (1 - beta2) * g * g
            m_hat = m / (1 - beta1 ** self._adam_t)
            v_hat = v / (1 - beta2 ** self._adam_t)
            param = getattr(self, k)
            param -= self.lr * m_hat / (np.sqrt(v_hat) + eps)

    def train(self, samples: list[tuple[np.ndarray, int]], *,
              epochs: int = 20, batch_size: int = 64,
              val_split: float = 0.15, seed: int = 0,
              progress=None) -> dict:
        """Treina por clonagem comportamental; retorna histórico."""
        if not samples:
            return {"epochs": [], "val_acc": [], "loss": []}
        rng = np.random.default_rng(seed)
        X = np.stack([s[0] for s in samples]).reshape(len(samples), -1)
        y = np.array([s[1] for s in samples], dtype=np.int64)
        idx = rng.permutation(len(y))
        n_val = max(1, int(len(y) * val_split))
        val_idx, tr_idx = idx[:n_val], idx[n_val:]
        Xtr, ytr, Xval, yval = X[tr_idx], y[tr_idx], X[val_idx], y[val_idx]

        hist = {"epochs": [], "loss": [], "val_acc": []}
        best_acc, best_params = -1.0, None
        for ep in range(1, epochs + 1):
            order = rng.permutation(len(ytr))
            total_loss, n_batches = 0.0, 0
            for start in range(0, len(order), batch_size):
                bi = order[start:start + batch_size]
                xb, yb = Xtr[bi], ytr[bi]
                # forward
                h_pre = xb @ self.W1 + self.b1
                h = np.maximum(0.0, h_pre)
                logits = h @ self.W2 + self.b2
                logits -= logits.max(axis=1, keepdims=True)
                exp = np.exp(logits)
                probs = exp / exp.sum(axis=1, keepdims=True)
                loss = -np.log(probs[np.arange(len(yb)), yb] + 1e-9).mean()
                total_loss += float(loss)
                n_batches += 1
                # backward
                dlogits = probs
                dlogits[np.arange(len(yb)), yb] -= 1.0
                dlogits /= len(yb)
                gW2 = h.T @ dlogits
                gb2 = dlogits.sum(axis=0)
                dh = dlogits @ self.W2.T
                dh[h_pre <= 0] = 0.0
                gW1 = xb.T @ dh
                gb1 = dh.sum(axis=0)
                self._adam_step({"W1": gW1, "b1": gb1, "W2": gW2, "b2": gb2})

            val_logits = self.logits(Xval)
            acc = float((val_logits.argmax(axis=1) == yval).mean())
            hist["epochs"].append(ep)
            hist["loss"].append(total_loss / max(1, n_batches))
            hist["val_acc"].append(acc)
            if acc > best_acc:
                best_acc = acc
                best_params = {k: getattr(self, k).copy()
                               for k in ("W1", "b1", "W2", "b2")}
            if progress is not None:
                progress(ep, epochs, hist)
        if best_params is not None:
            for k, v in best_params.items():
                setattr(self, k, v)
        self.trained_epochs += epochs
        hist["best_val_acc"] = best_acc
        return hist

    # ── Persistência ─────────────────────────────────────────────────────────
    def to_bytes(self) -> bytes:
        buf = io.BytesIO()
        np.savez_compressed(buf, W1=self.W1, b1=self.b1, W2=self.W2,
                            b2=self.b2,
                            meta=np.array([self.hidden, self.trained_epochs]))
        return buf.getvalue()

    @classmethod
    def from_bytes(cls, data: bytes) -> "MLPolicy":
        with np.load(io.BytesIO(data)) as z:
            pol = cls(hidden=int(z["meta"][0]))
            pol.W1, pol.b1 = z["W1"], z["b1"]
            pol.W2, pol.b2 = z["W2"], z["b2"]
            pol.trained_epochs = int(z["meta"][1])
        return pol


# ── Bot ML ───────────────────────────────────────────────────────────────────

class MLBot:
    """
    Bot por clonagem comportamental com salvaguarda heurística.

    As redes pontuam hexes; o bot escolhe, entre as opções **legais**
    (destinos alcançáveis / alvos ao alcance), a de maior score. Decisões
    de rodada de batalha e situações sem política treinada recaem na
    heurística — mesma abordagem do bot híbrido planejado no wargame.
    """

    name = "ML (clonagem comportamental)"

    def __init__(self, move_policy: MLPolicy | None = None,
                 attack_policy: MLPolicy | None = None):
        self.move_policy = move_policy
        self.attack_policy = attack_policy
        self._fallback = HeuristicBot()

    def moves(self, state: GameState, team: str) -> list[dict]:
        if self.move_policy is None:
            return self._fallback.moves(state, team)
        X = state_to_array(state.snapshot())[None, ...]
        scores = self.move_policy.logits(X)[0]          # (160,)
        moves = []
        for unit in state.alive_units(team):
            if (unit.moved or unit.movement <= 0 or unit.category == "land"
                    or unit.is_fuel_disabled()):
                continue
            paths = self._reachable_paths(unit)
            if not paths:
                continue
            best_hex, best_path = max(
                paths.items(), key=lambda kv: scores[kv[0][1] * GRID_W + kv[0][0]])
            cur_score = scores[unit.row * GRID_W + unit.col]
            if scores[best_hex[1] * GRID_W + best_hex[0]] <= cur_score:
                continue                                # ficar parado é melhor
            moves.append({"unitId": unit.id,
                          "path": [{"col": c, "row": r} for c, r in best_path]})
        return moves

    def _reachable_paths(self, unit: Unit) -> dict:
        """BFS: hexes alcançáveis → caminho (limitado ao movimento da unidade)."""
        from collections import deque
        start = (unit.col, unit.row)
        out: dict[tuple, list] = {}
        queue = deque([(start, [start], 0)])
        visited = {start}
        max_steps = unit.air_movement_range()
        while queue:
            pos, path, steps = queue.popleft()
            if steps > 0:
                out[pos] = path
            if steps >= max_steps:
                continue
            for nb in hx.hex_neighbors(*pos):
                if nb in visited:
                    continue
                if not hx.can_enter_terrain(unit.category,
                                            hx.get_terrain(*nb)):
                    continue
                visited.add(nb)
                queue.append((nb, path + [nb], steps + 1))
        return out

    def attacks(self, state: GameState, team: str) -> list[dict]:
        if self.attack_policy is None:
            return self._fallback.attacks(state, team)
        X = state_to_array(state.snapshot())[None, ...]
        scores = self.attack_policy.logits(X)[0]
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
            best = max(in_range, key=lambda e: scores[e.row * GRID_W + e.col])
            attacks.append({"attackerId": unit.id, "targetId": best.id})
        return attacks

    def battle_round_decision(self, state: GameState, eng: dict,
                              team: str) -> str:
        return self._fallback.battle_round_decision(state, eng, team)
