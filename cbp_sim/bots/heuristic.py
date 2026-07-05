"""
Bot heurístico — porte da IA do wargame Operação Atlântico Sul (server.js).

Doutrina do bot (deliberadamente onisciente, como no modo solo do jogo):
1. Logística própria foge de combatentes inimigos próximos.
2. Um combatente de superfície escolta o logístico mais valioso.
3. Demais unidades: reabastecem quando FP baixo, decolam com critério e
   avançam sobre o alvo priorizado pelos pesos derivados das condições de
   vitória (o bot persegue exatamente o que pontua; objetivos cumpridos
   são re-tarefados).
4. Ataques: melhor alvo ao alcance por peso de objetivo → prioridade
   genérica → distância.
5. Decisão CONTINUAR/PARAR por rodada de batalha: atacante recua sem
   munição ou muito ferido (a menos que o alvo esteja por cair); defensor
   continua se o grupo tem contra-arma utilizável.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from .. import hexmap as hx
from ..engine import GameState, Unit, OBJECTIVE_IDS, is_single_round_weapon


@dataclass
class BotTuning:
    """Parâmetros de doutrina do bot (espelho de BOT_TUNING)."""
    aggressiveness: float = 1.0      # 0..1 — menor = mais distraível p/ defesa
    opportunity_radius: int = 2      # combatente inimigo a este raio vira alvo
    refuel_floor: int = 4            # FP mínimo antes de buscar reabastecimento
    logistics_flee_radius: int = 4   # logística foge de combatentes a este raio
    stop_hp_frac: float = 0.4        # recua abaixo desta fração de SP
    finish_hp_threshold: float = 2.0  # ...exceto se o alvo está a isto de cair


COMBATANT_TYPES = {"carrier", "amphib", "fragata", "destroier", "corveta",
                   "cruzador", "sub_nuclear", "submarino", "caca", "ataque"}


def is_combatant(u: Unit) -> bool:
    return u.type in COMBATANT_TYPES


def generic_prio(u: Unit) -> int:
    if u.type == "carrier":
        return 0
    if u.type == "amphib":
        return 1
    if u.type in ("fragata", "destroier", "corveta", "cruzador"):
        return 2
    if u.type in ("sub_nuclear", "submarino"):
        return 3
    if u.type in ("caca", "ataque", "patrulha", "patrulha_oc", "patrulha_c"):
        return 4
    return 5


class HeuristicBot:
    """Política heurística orientada a objetivos, parametrizável."""

    name = "Heurístico"

    def __init__(self, tuning: BotTuning | None = None):
        self.tuning = tuning or BotTuning()

    # ── Pesos de alvo derivados das condições de vitória ─────────────────────
    def objective_weights(self, state: GameState, team: str) -> dict[str, int]:
        w: dict[str, int] = {}
        obj = state.compute_objectives()
        if team == "blue":
            met = {c["id"]: c["met"] for c in obj["blue"]["conditions"]}
            T = OBJECTIVE_IDS["blueTargets"]
            if not met["carrier"]:
                w[T["carrier"]] = 0
            if not met["logistics"]:
                for i in T["logistics"]:
                    w[i] = 0
            if not met["amphib"]:
                w[T["amphib"]] = 0
            if not met["nucsub"]:
                w[T["nucsub"]] = 0
            if not met["surface"]:
                for i in T["surface"]:
                    w.setdefault(i, 1)
        else:
            met = {c["id"]: c["met"] for c in obj["red"]["conditions"]}
            T = OBJECTIVE_IDS["redTargets"]
            if not met["fpsos"]:
                for i in T["fpsos"]:
                    w[i] = 0
            if not met["ports"]:
                for i in T["ports"]:
                    w[i] = 0
        return w

    def pick_target(self, unit: Unit, enemies: list[Unit],
                    obj_w: dict[str, int]) -> Unit | None:
        attackable = [e for e in enemies
                      if unit.range_against(e.category) > 0]
        if not attackable:
            return None

        def d(e: Unit) -> int:
            return hx.hex_dist(unit.col, unit.row, e.col, e.row)

        opp_radius = round(self.tuning.opportunity_radius
                           * (2 - self.tuning.aggressiveness))
        near = [e for e in attackable if is_combatant(e) and d(e) <= opp_radius]
        if near:
            return min(near, key=lambda e: (generic_prio(e), d(e)))
        return min(attackable,
                   key=lambda e: (obj_w.get(e.id, 9), generic_prio(e), d(e)))

    # ── Reabastecimento ──────────────────────────────────────────────────────
    def refuel_provider(self, unit: Unit, state: GameState) -> Unit | None:
        best, best_d = None, 10 ** 9
        for o in state.units:
            if o.id == unit.id or o.team != unit.team or not o.alive:
                continue
            if not o.is_refuel_provider():
                continue
            if not hx.can_enter_terrain(unit.category,
                                        hx.get_terrain(o.col, o.row)):
                continue
            dd = hx.hex_dist(unit.col, unit.row, o.col, o.row)
            if dd < best_d:
                best, best_d = o, dd
        return best

    def needs_refuel(self, unit: Unit, provider: Unit | None) -> bool:
        if unit.fuel.get("fuelType") != "naval" or provider is None:
            return False
        if unit.is_refuel_provider():
            return False
        dist = hx.hex_dist(unit.col, unit.row, provider.col, provider.row)
        trip = -(-dist // max(1, unit.movement)) * 3 + 1
        return unit.fuel.get("current", 0) <= max(self.tuning.refuel_floor, trip)

    # ── BFS de movimento ─────────────────────────────────────────────────────
    def _bfs(self, unit: Unit, score_fn, best_score, maximize: bool):
        best_path = None
        start = (unit.col, unit.row)
        queue = deque([(start, [start], 0)])
        visited = {start}
        max_steps = unit.air_movement_range()
        while queue:
            (pos, path, steps) = queue.popleft()
            if steps > 0:
                s = score_fn(*pos)
                better = s > best_score if maximize else s < best_score
                if better:
                    best_score, best_path = s, path
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
        return best_path

    def move_toward(self, unit: Unit, target: Unit) -> list | None:
        d0 = hx.hex_dist(unit.col, unit.row, target.col, target.row)
        return self._bfs(unit,
                         lambda c, r: hx.hex_dist(c, r, target.col, target.row),
                         d0, maximize=False)

    def move_away(self, unit: Unit, threats: list[Unit]) -> list | None:
        if not threats:
            return None

        def min_d(c, r):
            return min(hx.hex_dist(c, r, t.col, t.row) for t in threats)

        return self._bfs(unit, min_d, min_d(unit.col, unit.row), maximize=True)

    @staticmethod
    def _path_dicts(path: list) -> list[dict]:
        return [{"col": c, "row": r} for c, r in path]

    # ── Interface do bot ─────────────────────────────────────────────────────
    def moves(self, state: GameState, team: str) -> list[dict]:
        moves: list[dict] = []
        handled: set[str] = set()
        enemies = state.alive_units()
        enemies = [u for u in enemies if u.team != team]
        own = [u for u in state.alive_units(team) if not u.moved]
        obj_w = self.objective_weights(state, team)
        enemy_combatants = [e for e in enemies if is_combatant(e)]

        def mobile(u: Unit) -> bool:
            return (u.movement > 0 and u.category != "land"
                    and not u.is_fuel_disabled())

        def nearest(u: Unit, lst: list[Unit]) -> Unit | None:
            return min(lst, key=lambda e: hx.hex_dist(u.col, u.row, e.col, e.row),
                       default=None)

        # 1. Logística foge de combatentes próximos
        planned_dest: dict[str, tuple[int, int]] = {}
        providers = [u for u in own
                     if u.is_refuel_provider() and u.category == "surface"]
        for logi in providers:
            if not mobile(logi):
                continue
            threat = nearest(logi, enemy_combatants)
            if (threat is None or hx.hex_dist(logi.col, logi.row, threat.col,
                                              threat.row)
                    > self.tuning.logistics_flee_radius):
                continue
            path = self.move_away(logi, enemy_combatants)
            if path and len(path) >= 2:
                moves.append({"unitId": logi.id, "path": self._path_dicts(path)})
                planned_dest[logi.id] = path[-1]
            handled.add(logi.id)

        # 2. Escolta do logístico mais valioso
        prime = next(iter(sorted(
            [p for p in providers if mobile(p)],
            key=lambda p: 0 if p.type == "tanque" else 1)), None)
        if prime is not None:
            goal = planned_dest.get(prime.id, (prime.col, prime.row))
            escorts = [u for u in own
                       if is_combatant(u) and u.category == "surface"
                       and mobile(u) and u.id not in handled
                       and not self.needs_refuel(
                           u, self.refuel_provider(u, state))]
            escort = min(escorts, key=lambda u: hx.hex_dist(
                u.col, u.row, goal[0], goal[1]), default=None)
            if escort is not None:
                if hx.hex_dist(escort.col, escort.row, goal[0], goal[1]) > 1:
                    tgt = type("G", (), {"col": goal[0], "row": goal[1]})()
                    path = self.move_toward(escort, tgt)
                    if path and len(path) >= 2:
                        moves.append({"unitId": escort.id,
                                      "path": self._path_dicts(path)})
                handled.add(escort.id)

        # 3. Demais unidades
        for unit in own:
            if unit.id in handled or not mobile(unit):
                continue
            provider = self.refuel_provider(unit, state)
            if self.needs_refuel(unit, provider):
                if unit.col == provider.col and unit.row == provider.row:
                    continue
                path = self.move_toward(unit, provider)
                if path and len(path) >= 2:
                    moves.append({"unitId": unit.id,
                                  "path": self._path_dicts(path)})
                continue
            target = self.pick_target(unit, enemies, obj_w)
            if target is None:
                continue
            dist = hx.hex_dist(unit.col, unit.row, target.col, target.row)
            atk_r = unit.range_against(target.category)
            if dist <= atk_r:
                continue
            if (unit.category == "air" and unit.air_status == "ready"
                    and dist - atk_r > unit.air_movement_range()):
                continue
            path = self.move_toward(unit, target)
            if path and len(path) >= 2:
                moves.append({"unitId": unit.id, "path": self._path_dicts(path)})
        return moves

    def attacks(self, state: GameState, team: str) -> list[dict]:
        attacks: list[dict] = []
        obj_w = self.objective_weights(state, team)
        enemies = [u for u in state.alive_units() if u.team != team]
        for unit in state.alive_units(team):
            if not unit.can_attack():
                continue

            def d(e: Unit) -> int:
                return hx.hex_dist(unit.col, unit.row, e.col, e.row)

            in_range = [e for e in enemies
                        if unit.range_against(e.category) > 0
                        and d(e) <= unit.range_against(e.category)]
            if in_range:
                best = min(in_range, key=lambda e: (obj_w.get(e.id, 9),
                                                    generic_prio(e), d(e)))
                attacks.append({"attackerId": unit.id, "targetId": best.id})
        return attacks

    def battle_round_decision(self, state: GameState, eng: dict,
                              team: str) -> str:
        att = state.unit(eng["attackerId"])
        dfd = state.unit(eng["targetId"])
        att_alive = att is not None and att.alive
        def_alive = dfd is not None and dfd.alive

        if att is not None and att.team == team:
            if not att_alive or not def_alive:
                return "stop"
            if att.weapon_quantity(eng["weaponType"]) <= 0:
                return "stop"
            wounded = att.hp / att.max_hp < self.tuning.stop_hp_frac
            near_kill = dfd.hp <= self.tuning.finish_hp_threshold
            return "stop" if (wounded and not near_kill) else "continue"

        if not att_alive:
            return "stop"
        if eng["targetCategory"] == "surface":
            group = [u for u in state.units
                     if u.alive and u.team == eng["targetTeam"]
                     and u.col == eng["targetCol"] and u.row == eng["targetRow"]]
        else:
            group = [dfd] if def_alive else []
        can_counter = any(
            u.can_attack() and u.id != att.id
            and (w := u.select_best_weapon(
                att, hx.hex_dist(u.col, u.row, att.col, att.row))) is not None
            and not is_single_round_weapon(w)
            for u in group)
        return "continue" if can_counter else "stop"
