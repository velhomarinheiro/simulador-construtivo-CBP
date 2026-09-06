"""
Motor de simulação construtiva — cenário Operação Atlântico Sul.

Porte em Python da mecânica do wargame OAS (repos wargame-naval /
simulacao-construtiva-OAS): grade hexagonal 16×10, turnos com períodos
diurno/noturno, movimentação simultânea, fase de combate com rodadas de
batalha, contra-ataques em grupo, logística (FP naval/aéreo, recompletamento
de munição em portos/bases) e vitória por objetivos assimétricos.

Diferença central em relação ao jogo original: os engajamentos são
adjudicados pela **equação de salva multidomínio** (módulo ``salvo``),
em modo estocástico (distribuição d6 original) ou determinístico
(valores esperados da equação canônica).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from . import hexmap as hx
from . import salvo as sv
from .cyber import CyberForce, PhiFactors, compute_phi

DATA_DIR = Path(__file__).parent / "data"

MAX_TURNS_DEFAULT = 12          # limite operacional em dias (turnos dia+noite)
FUEL_TURN_LIMIT = 4             # FP naval máximo gasto por turno

# FP por unidade (espelho de fuel_model.js)
NAVAL_FP = {"surface": 12, "submarine": 20}
UNIT_FP = {
    "BLUE-SAG-P": 12, "BLUE-SAG-S1": 10, "BLUE-SAG-S2": 10, "BLUE-ANFIB": 8,
    "BLUE-LOG-A": 30, "BLUE-LOG-T": 40, "BLUE-PAT-O1": 10, "BLUE-PAT-O2": 10,
    "BLUE-PAT-C1": 6, "BLUE-PAT-C2": 6,
    "RED-GE-1": 12, "RED-GE-2": 12, "RED-GE-3": 10, "RED-AOR-G": 24,
    "RED-GANF": 12, "RED-GLOG": 30, "RED-AKE": 8,
}
RED_NUCLEAR_CARRIER = "RED-GBPA"

COMP_DISPLAY_TYPE = {
    "operacoes_especiais": "specops", "navio_aeródromo": "carrier",
    "navio_doca": "amphib", "navio_desembarque": "amphib",
    "fragata": "fragata", "corveta": "corveta", "destroier": "destroier",
    "destroyer": "destroier", "cruzador": "cruzador",
    "navio_patoc": "patrulha_oc", "navio_patrulha": "patrulha_c",
    "navio_logistico": "logistico", "navio_tanque": "tanque",
    "submarino_nuclear": "sub_nuclear", "submarino_convencional": "submarino",
    "patrulha_maritima": "patrulha", "caca": "caca", "ataque": "ataque",
    "aew": "aew", "helicoptero_ASW": "helicoptero",
    "helicoptero_ASup": "helicoptero", "bateria_costeira": "bateria_costeira",
    "bateria_ada": "bateria_ada", "base_naval": "bateria_ada",
    "plataforma": "fpso", "porto": "porto", "aeroporto": "aeroporto",
}
DISPLAY_TYPE_FALLBACK = {
    "surface": "fragata", "submarine": "submarino", "air": "patrulha",
    "land": "corveta", "specops": "specops",
}

WEAPON_PRIORITY = {
    "surface": ["ascm", "asbm", "mss", "torpedo", "airAttack", "navalGun", "raid"],
    "submarine": ["asw", "torpedo"],
    "air": ["airDefense", "airAttack"],
    "land": ["lacm", "airAttack", "navalGun", "raid"],
}

OBJECTIVE_IDS = {
    "blueTargets": {
        "carrier": "RED-GBPA",
        "logistics": ["RED-AOR-G", "RED-GLOG", "RED-AKE"],
        "amphib": "RED-GANF",
        "nucsub": "RED-KSN",
        "surface": ["RED-GBPA", "RED-GE-1", "RED-GE-2", "RED-GE-3", "RED-GANF"],
    },
    "redTargets": {
        "fpsos": ["BLUE-FPSO1", "BLUE-FPSO2", "BLUE-FPSO3", "BLUE-FPSO4"],
        "ports": ["BLUE-PORTO-S", "BLUE-PORTO-RJ", "BLUE-PORTO-V", "BLUE-PORTO-ACU"],
    },
}


def load_order_of_battle() -> dict:
    """Ordem de batalha padrão (exportada do wargame-naval)."""
    with open(DATA_DIR / "order_of_battle.json", encoding="utf-8") as f:
        return json.load(f)


# ── Unidade ──────────────────────────────────────────────────────────────────

class Unit:
    """Grupo-tarefa / meio operativo no tabuleiro (espelho de makeUnit)."""

    def __init__(self, team: str, spec: dict):
        pos = spec.get("position", {"col": 0, "row": 0})
        comp = spec.get("composition") or []
        self.id: str = spec["id"]
        self.team: str = team
        self.name: str = spec.get("name", spec["id"])
        self.category: str = spec["category"]
        self.type: str = (COMP_DISPLAY_TYPE.get(comp[0]["type"])
                          if comp else None) or DISPLAY_TYPE_FALLBACK.get(
                              spec["category"], "fragata")
        self.composition = comp
        self.movement: int = spec.get("movement", 0)
        self.detection_range: dict = dict(spec.get("detectionRange") or {})
        self.attack_range: dict = dict(spec.get("attackRange") or {})
        self.col: int = pos["col"]
        self.row: int = pos["row"]
        self.hp: float = float(spec["stayingPower"])
        self.max_hp: float = float(spec["stayingPower"])
        self.stealthy: bool = spec["category"] == "submarine" or bool(
            spec.get("stealthy"))
        self.moved: bool = False
        self.weapons: dict = copy.deepcopy(spec.get("weapons") or {})
        self.init_weapons: dict = copy.deepcopy(self.weapons)
        self.capabilities: dict = dict(spec.get("capabilities") or {})
        self.init_movement = self.movement
        self.init_detection_range = copy.deepcopy(self.detection_range)
        self.init_capabilities = copy.deepcopy(self.capabilities)
        self.base_hex = {"col": pos["col"], "row": pos["row"]}
        self.base_unit_id: Optional[str] = spec.get("embarked")
        self.host_id: Optional[str] = spec.get("hostId")
        self.notes: str = spec.get("notes", "")
        self._init_fuel()

    # ── Combustível (espelho de fuel_model.js) ──────────────────────────────
    def _init_fuel(self):
        if self.category == "air":
            fp = self.movement * 2
            self.air_status = "ready"
            self.fuel = {"usesFuel": True, "fuelType": "air", "current": fp,
                         "max": fp, "wasAtRefuelLocation": False}
        elif self._uses_naval_fuel():
            mx = (NAVAL_FP["submarine"] if self._is_conventional_sub()
                  else UNIT_FP.get(self.id, NAVAL_FP["surface"]))
            self.air_status = None
            self.fuel = {"usesFuel": True, "fuelType": "naval", "current": mx,
                         "max": mx, "spentThisTurn": 0}
        else:
            self.air_status = None
            self.fuel = {"usesFuel": False, "fuelType": "none"}
        self.init_fuel_max = self.fuel.get("max", 0)

    def _is_nuclear_sub(self):
        return self.category == "submarine" and self.type == "sub_nuclear"

    def _is_conventional_sub(self):
        return self.category == "submarine" and not self._is_nuclear_sub()

    def _uses_naval_fuel(self):
        if self.id == RED_NUCLEAR_CARRIER or self._is_nuclear_sub():
            return False
        if self.type == "fpso":
            return False
        if self.category == "surface":
            return True
        return self._is_conventional_sub()

    @property
    def alive(self) -> bool:
        return self.hp > 0

    def is_refuel_provider(self) -> bool:
        return self.alive and self.type in ("tanque", "logistico", "porto")

    def is_fuel_disabled(self) -> bool:
        return (self.fuel.get("fuelType") == "naval"
                and self.fuel.get("current", 1) <= 0)

    def can_move(self) -> bool:
        return not self.is_fuel_disabled()

    def can_attack(self) -> bool:
        if self.category == "air":
            return True
        return not self.is_fuel_disabled()

    def can_defend(self) -> bool:
        if self.category == "air":
            return True
        return not self.is_fuel_disabled()

    def spend_naval_fuel(self, amount: int):
        if self.fuel.get("fuelType") != "naval":
            return
        cap = max(0, FUEL_TURN_LIMIT - self.fuel.get("spentThisTurn", 0))
        actual = min(amount, cap, self.fuel.get("current", 0))
        self.fuel["current"] = max(0, self.fuel.get("current", 0) - actual)
        self.fuel["spentThisTurn"] = self.fuel.get("spentThisTurn", 0) + actual

    def spend_air_fuel(self, amount: int):
        if self.category != "air" or self.air_status != "airborne":
            return
        self.fuel["current"] = max(0, self.fuel.get("current", 0) - amount)

    def spend_engagement_fuel(self):
        if self.category == "air":
            self.spend_air_fuel(1)
        else:
            self.spend_naval_fuel(1)

    def air_movement_range(self) -> int:
        if self.category != "air":
            return self.movement
        return int(self.fuel.get("current", self.movement)) // 2

    # ── Armas ────────────────────────────────────────────────────────────────
    def weapon_quantity(self, weapon_type: str) -> int:
        if weapon_type in self.weapons:
            return int(self.weapons[weapon_type].get("quantity", 0))
        if weapon_type in self.capabilities:
            return int(self.capabilities[weapon_type])
        return 0

    def weapon_range(self, weapon_type: str) -> int:
        if weapon_type in self.weapons and "range" in self.weapons[weapon_type]:
            return int(self.weapons[weapon_type]["range"])
        profile = sv.WEAPON_PROFILES.get(weapon_type)
        return int(profile.get("defaultRange", 0)) if profile else 0

    def spend_weapon(self, weapon_type: str, amount: int):
        profile = sv.WEAPON_PROFILES.get(weapon_type)
        if not profile or not profile.get("expendable"):
            return
        if weapon_type in self.weapons:
            q = self.weapons[weapon_type].get("quantity", 0)
            self.weapons[weapon_type]["quantity"] = max(0, q - amount)

    def range_against(self, target_category: str) -> int:
        return int(self.attack_range.get(target_category, 0) or 0)

    def select_best_weapon(self, target: "Unit", dist: int) -> Optional[str]:
        for wpn in WEAPON_PRIORITY.get(target.category, []):
            if self.weapon_quantity(wpn) <= 0:
                continue
            profile = sv.WEAPON_PROFILES.get(wpn)
            if not profile or target.category not in profile["targets"]:
                continue
            if dist <= self.weapon_range(wpn):
                return wpn
        return None

    def snapshot(self) -> dict:
        """Estado mínimo p/ logs e features de ML (formato do game_logger)."""
        return {
            "id": self.id, "team": self.team, "name": self.name,
            "category": self.category, "type": self.type,
            "col": self.col, "row": self.row,
            "hp": self.hp, "maxHp": self.max_hp,
            "fuel": {k: self.fuel.get(k) for k in ("current", "max")}
            if self.fuel.get("usesFuel") else None,
            "weapons": copy.deepcopy(self.weapons),
        }


def naval_move_cost(distance: int) -> int:
    if distance == 0:
        return 1
    return 3 if distance >= 3 else distance


def is_single_round_weapon(weapon_type: str) -> bool:
    return weapon_type in ("lacm", "asbm")


# ── Estado do jogo ───────────────────────────────────────────────────────────

class GameState:
    """Estado completo de uma partida construtiva (bot × bot)."""

    def __init__(self, oob: Optional[dict] = None, *,
                 max_turns: int = MAX_TURNS_DEFAULT,
                 stochastic: bool = True,
                 chi: float = sv.DEFAULT_CHI,
                 seed: Optional[int] = None,
                 blue_cyber: Optional[CyberForce | dict] = None,
                 red_cyber: Optional[CyberForce | dict] = None,
                 fog_of_war: bool = False):
        oob = oob or load_order_of_battle()
        self.units: list[Unit] = (
            [Unit("blue", s) for s in oob["forces"]["blue"]]
            + [Unit("red", s) for s in oob["forces"]["red"]])
        self.turn = 1
        self.period = "day"                 # day | night
        self.max_turns = max_turns
        self.stochastic = stochastic
        self.chi = chi
        self.adm_matrix = sv.canonical_matrix(chi)
        self.rng = np.random.default_rng(seed)
        self.winner: Optional[str] = None
        self.end_reason: Optional[str] = None
        self.log: list[str] = [f"──── Turno 1 · Período Diurno ────"]
        self.events: list[dict] = []        # trilha JSONL p/ ML e auditoria
        self.engagement_records: list[dict] = []
        self.fog_of_war = fog_of_war

        # ── Domínio cibernético: Φ que cada força SOFRE (do ciber oponente) ──
        self.blue_cyber = (blue_cyber if isinstance(blue_cyber, CyberForce)
                           else CyberForce.from_dict(blue_cyber))
        self.red_cyber = (red_cyber if isinstance(red_cyber, CyberForce)
                          else CyberForce.from_dict(red_cyber))
        self.phi: dict[str, PhiFactors] = {
            "blue": compute_phi(self.blue_cyber, self.red_cyber),
            "red": compute_phi(self.red_cyber, self.blue_cyber),
        }
        if self.blue_cyber.total or self.red_cyber.total:
            pb, pr = self.phi["blue"], self.phi["red"]
            self._log(f"⚡ Guerra cibernética ativa — Φ Azul (of/def/det/log): "
                      f"{pb.offense:.2f}/{pb.defense:.2f}/"
                      f"{pb.detection:.2f}/{pb.logistics:.2f} · Φ Vermelha: "
                      f"{pr.offense:.2f}/{pr.defense:.2f}/"
                      f"{pr.detection:.2f}/{pr.logistics:.2f}")

    # ── Consultas ────────────────────────────────────────────────────────────
    def unit(self, unit_id: str) -> Optional[Unit]:
        return next((u for u in self.units if u.id == unit_id), None)

    def alive_units(self, team: Optional[str] = None) -> list[Unit]:
        return [u for u in self.units
                if u.alive and (team is None or u.team == team)]

    def snapshot(self) -> dict:
        return {"turn": self.turn, "period": self.period,
                "units": [u.snapshot() for u in self.units]}

    def _log(self, msg: str):
        self.log.append(msg)

    # ── Detecção / névoa de guerra ────────────────────────────────────────────
    STATIC_TYPES = ("fpso", "porto", "aeroporto")

    def detected_enemy_ids(self, team: str) -> set[str]:
        """
        Inimigos detectados pela força ``team`` neste instante.

        Regras (espelho da névoa de guerra do wargame OAS):
        - um inimigo é detectado se algum meio amigo vivo o alcança dentro
          do alcance de detecção da categoria do alvo;
        - no período noturno os alcances caem 1 hex (mínimo 1);
        - o Φ de detecção (ciber SEN/C2 do oponente) multiplica os alcances;
        - infraestruturas fixas (FPSOs, portos, aeródromos) são sempre
          conhecidas — posição pública.
        """
        night = self.period == "night"
        phi_det = self.phi[team].detection
        enemies = [u for u in self.alive_units() if u.team != team]
        own = self.alive_units(team)
        visible: set[str] = set()
        for e in enemies:
            if e.type in self.STATIC_TYPES:
                visible.add(e.id)
                continue
            for f in own:
                r = f.detection_range.get(e.category, 0) * phi_det
                if night and r > 0:
                    r = max(1.0, r - 1.0)
                if r > 0 and hx.hex_dist(f.col, f.row, e.col, e.row) <= r:
                    visible.add(e.id)
                    break
        return visible

    def _event(self, event: str, **payload):
        self.events.append({"event": event, "turn": self.turn,
                            "period": self.period, **payload})

    # ── Objetivos e vitória (porte de computeObjectives) ─────────────────────
    def compute_objectives(self) -> dict:
        u = {x.id: x for x in self.units}
        bt, rt = OBJECTIVE_IDS["blueTargets"], OBJECTIVE_IDS["redTargets"]

        carrier = u.get(bt["carrier"])
        carrier_met = carrier is None or carrier.hp <= 0

        log_units = [u[i] for i in bt["logistics"] if i in u]
        log_dead = sum(1 for x in log_units if x.hp <= 0)
        log_met = log_dead >= 2

        amphib = u.get(bt["amphib"])
        amphib_met = amphib is None or amphib.hp <= 0

        nucsub = u.get(bt["nucsub"])
        nucsub_met = nucsub is None or nucsub.hp <= 0

        surf_units = [u[i] for i in bt["surface"] if i in u]
        surf_max = sum(x.max_hp for x in surf_units)
        surf_cur = sum(max(0.0, x.hp) for x in surf_units)
        surf_deg = round((1 - surf_cur / surf_max) * 100) if surf_max else 0
        surf_met = surf_deg >= 50

        blue_conds = [
            {"id": "carrier", "label": "Destruir Porta-Aviões", "met": carrier_met},
            {"id": "logistics", "label": "Neutralizar ≥50% Logística",
             "met": log_met, "current": f"{log_dead}/{len(log_units)}"},
            {"id": "amphib", "label": "Neutralizar GT Anfíbio", "met": amphib_met},
            {"id": "nucsub", "label": "Destruir Submarino Nuclear", "met": nucsub_met},
            {"id": "surface", "label": "Degradar ≥50% Nav. Combatentes",
             "met": surf_met, "current": f"{surf_deg}%"},
        ]
        blue_achieved = sum(1 for c in blue_conds if c["met"])

        fpso_units = [u[i] for i in rt["fpsos"] if i in u]
        fpso_neut = sum(1 for x in fpso_units if x.hp <= 0)
        fpso_met = fpso_neut >= 4

        port_units = [u[i] for i in rt["ports"] if i in u]
        port_max = sum(x.max_hp for x in port_units)
        port_cur = sum(max(0.0, x.hp) for x in port_units)
        port_deg = round((1 - port_cur / port_max) * 100) if port_max else 0
        ports_met = port_deg >= 50

        red_conds = [
            {"id": "fpsos", "label": "Neutralizar 4 FPSOs", "met": fpso_met,
             "current": f"{fpso_neut}/4"},
            {"id": "ports", "label": "Degradar ≥50% Portos", "met": ports_met,
             "current": f"{port_deg}%"},
        ]
        red_achieved = sum(1 for c in red_conds if c["met"])

        return {
            "blue": {"conditions": blue_conds, "needed": 3,
                     "achieved": blue_achieved, "won": blue_achieved >= 3},
            "red": {"conditions": red_conds, "needed": 2,
                    "achieved": red_achieved, "won": red_achieved >= 2},
        }

    def check_winner(self) -> Optional[str]:
        obj = self.compute_objectives()
        if obj["blue"]["won"]:
            return "blue"          # empate simultâneo → Azul (tiebreak)
        if obj["red"]["won"]:
            return "red"
        return None

    # ── Movimentação ─────────────────────────────────────────────────────────
    def apply_moves(self, team: str, moves: list[dict]):
        """Aplica movimentos {unitId, path:[{col,row},...]} de um time."""
        self._event("movement_committed", team=team, state=self.snapshot(),
                    moves=moves)
        for mv in moves:
            unit = self.unit(mv["unitId"])
            if unit is None or not unit.alive or unit.moved:
                continue
            if not unit.can_move():
                continue
            path = mv.get("path") or []
            if len(path) < 2:
                continue
            dest = path[-1]
            dist = len(path) - 1
            if unit.category == "air":
                if dist > unit.air_movement_range():
                    continue
                unit.air_status = "airborne"
                unit.spend_air_fuel(2 * dist)
            else:
                if dist > unit.movement:
                    continue
                unit.spend_naval_fuel(naval_move_cost(dist))
            unit.col, unit.row = dest["col"], dest["row"]
            unit.moved = True
            self._log(f"{unit.name} ({unit.team}) → "
                      f"{hx.hex_label(unit.col, unit.row)}")
        # Unidades navais paradas mantêm posição (custo de 1 FP)
        for u in self.alive_units(team):
            if not u.moved and u.fuel.get("fuelType") == "naval":
                u.spend_naval_fuel(1)

    # ── Combate ──────────────────────────────────────────────────────────────
    def _defending_group(self, col: int, row: int, team: str,
                         category: str) -> Optional[list[Unit]]:
        if category != "surface":
            return None
        stack = [u for u in self.units
                 if u.alive and u.team == team and u.col == col and u.row == row]
        return stack if len(stack) > 1 else None

    def _resolve_battle_round(self, eng: dict,
                              initiative_team: Optional[str] = None) -> Optional[sv.SalvoOutcome]:
        att = self.unit(eng["attackerId"])
        dfd = self.unit(eng["targetId"])
        if att is None or not att.alive or dfd is None or not dfd.alive:
            eng["status"] = "ended"
            return None
        if not att.can_attack():
            return None

        stack = self._defending_group(dfd.col, dfd.row, dfd.team, dfd.category)
        if stack is not None:
            interceptors = [u for u in stack if u.can_defend()]
        else:
            interceptors = [] if dfd.is_fuel_disabled() else [dfd]

        dist = hx.hex_dist(att.col, att.row, dfd.col, dfd.row)
        out = sv.resolve_salvo(
            attacker=att, defender=dfd,
            defenders_stack=interceptors or [dfd],
            weapon_type=eng["weaponType"], amount=eng["amount"],
            distance=dist, rng=self.rng, stochastic=self.stochastic,
            chi=self.chi, adm_matrix=self.adm_matrix,
            advantage=(initiative_team is not None
                       and initiative_team == att.team),
            phi_offense=self.phi[att.team].offense,
            phi_defense=self.phi[dfd.team].defense,
        )
        if out.ok:
            att.spend_engagement_fuel()
            if out.destroyed:
                self._log(f"💥 {dfd.name} DESTRUÍDO por {att.name} "
                          f"[{out.weapon_label}]")
                # Cascata: aeronaves embarcadas e OpEsp hospedadas
                for u in self.units:
                    if u.alive and (u.base_unit_id == dfd.id or u.host_id == dfd.id):
                        u.hp = 0
                        self._log(f"💥 {u.name} perdido com {dfd.name}")
            elif out.damage > 0:
                self._log(f"✓ {att.name} → {dfd.name} −{out.damage:.1f}SP "
                          f"[{out.weapon_label}] (χ={out.chi:.2f}, "
                          f"{out.intercepted:.0f} intercept.)")
                dfd.spend_engagement_fuel()
                deg = self._apply_degradation(dfd, out.damage)
                if deg:
                    self._log(f"  ↘ {dfd.name}: {deg}")
            else:
                self._log(f"✗ {att.name} → {dfd.name} sem efeito "
                          f"[{out.weapon_label}]")
        eng["results"].append({
            "battleRound": eng["battleRound"],
            "initiative": initiative_team,
            "outcome": _outcome_dict(out),
        })
        return out

    def _apply_degradation(self, unit: Unit, damage: float) -> Optional[str]:
        """Degradação de capacidades proporcional ao dano (porte do server)."""
        ratio = damage / (unit.max_hp or 1)
        pool = []
        if unit.init_detection_range and any(
                v > 1 for v in unit.detection_range.values()):
            pool.append("detection")
        if unit.movement > 1:
            pool.append("movement")
        if any(v > 1 for v in unit.capabilities.values()):
            pool.append("combat")
        if unit.fuel.get("fuelType") == "naval" and unit.fuel.get("max", 0) > 1:
            pool.append("fuel")
        if not pool:
            return None
        cat = pool[int(self.rng.integers(0, len(pool)))]
        if cat == "detection":
            init_max = max(1, *unit.init_detection_range.values())
            red = max(1, int(ratio * init_max))
            for k, v in unit.detection_range.items():
                if v > 0:
                    unit.detection_range[k] = max(1, v - red)
            return f"Detecção −{red}"
        if cat == "movement":
            red = max(1, int(ratio * (unit.init_movement or 1)))
            unit.movement = max(1, unit.movement - red)
            return f"Movimentação −{red}"
        if cat == "combat":
            caps = [(k, v) for k, v in unit.capabilities.items() if v > 1]
            caps.sort(key=lambda kv: -kv[1])
            k, v = caps[0]
            red = max(1, int(ratio * unit.init_capabilities.get(k, v)))
            unit.capabilities[k] = max(1, v - red)
            return f"{k} −{red}"
        if cat == "fuel":
            red = max(1, int(ratio * (unit.init_fuel_max or 1) * 0.5))
            unit.fuel["max"] = max(1, unit.fuel["max"] - red)
            unit.fuel["current"] = min(unit.fuel["current"], unit.fuel["max"])
            return f"Combustível −{red}FP"
        return None

    def _build_combat_queue(self, blue_attacks: list[dict],
                            red_attacks: list[dict]) -> list[dict]:
        blue_first = (self.turn % 2) == 1
        first, second = ((blue_attacks, red_attacks) if blue_first
                         else (red_attacks, blue_attacks))
        interleaved = []
        for i in range(max(len(first), len(second))):
            if i < len(first):
                interleaved.append(first[i])
            if i < len(second):
                interleaved.append(second[i])

        detected = {"blue": self.detected_enemy_ids("blue"),
                    "red": self.detected_enemy_ids("red")} \
            if self.fog_of_war else None

        queue = []
        for i, atk in enumerate(interleaved):
            att = self.unit(atk["attackerId"])
            dfd = self.unit(atk["targetId"])
            if att is None or not att.alive or dfd is None or not dfd.alive:
                continue
            # Névoa de guerra: ataque exige alvo detectado no momento da
            # declaração (infraestrutura fixa é sempre conhecida).
            if detected is not None and dfd.id not in detected[att.team]:
                self._log(f"🌫 {att.name}: alvo {dfd.name} não detectado — "
                          "ataque abortado.")
                continue
            dist = hx.hex_dist(att.col, att.row, dfd.col, dfd.row)
            wpn = atk.get("weaponType")
            if not wpn or att.weapon_quantity(wpn) <= 0:
                wpn = att.select_best_weapon(dfd, dist)
            if not wpn:
                continue
            profile = sv.WEAPON_PROFILES.get(wpn, {})
            requested = atk.get("amount", sv.SALVO_SIZE.get(wpn, 1))
            amount = (min(att.weapon_quantity(wpn), max(1, requested))
                      if profile.get("expendable") else 1)
            queue.append({
                "id": f"ENG-{i + 1:02d}",
                "attackerId": atk["attackerId"], "targetId": atk["targetId"],
                "weaponType": wpn, "amount": amount,
                "battleRound": 1,
                "maxBattleRounds": 1 if is_single_round_weapon(wpn) else 2,
                "status": "pending", "results": [],
                "targetCol": dfd.col, "targetRow": dfd.row,
                "targetTeam": dfd.team, "targetCategory": dfd.category,
            })
        return queue

    def _resolve_counter_attacks(self, eng: dict, blue_dec: str, red_dec: str):
        att = self.unit(eng["attackerId"])
        if att is None or not att.alive:
            return
        if eng["targetCategory"] == "surface":
            group = [u for u in self.units
                     if u.alive and u.team == eng["targetTeam"]
                     and u.col == eng["targetCol"] and u.row == eng["targetRow"]]
        else:
            dfd = self.unit(eng["targetId"])
            group = [dfd] if dfd is not None and dfd.alive else []

        def_dec = blue_dec if eng["targetTeam"] == "blue" else red_dec
        att_dec = blue_dec if att.team == "blue" else red_dec
        counter_init = (eng["targetTeam"]
                        if def_dec == "continue" and att_dec == "stop" else None)

        idx = 0
        for unit in group:
            if not unit.alive or not unit.can_attack() or unit.id == att.id:
                continue
            dist = hx.hex_dist(unit.col, unit.row, att.col, att.row)
            wpn = unit.select_best_weapon(att, dist)
            if not wpn or is_single_round_weapon(wpn):
                continue
            profile = sv.WEAPON_PROFILES.get(wpn, {})
            amt = (min(unit.weapon_quantity(wpn), sv.SALVO_SIZE.get(wpn, 1))
                   if profile.get("expendable") else 1)
            idx += 1
            counter = {
                "id": f"{eng['id']}-CTR{idx}",
                "attackerId": unit.id, "targetId": att.id,
                "weaponType": wpn, "amount": amt,
                "battleRound": 2, "maxBattleRounds": 2,
                "status": "pending", "results": [],
                "targetCol": att.col, "targetRow": att.row,
                "targetTeam": att.team, "targetCategory": att.category,
            }
            self._resolve_battle_round(counter, counter_init)
            self.engagement_records.append(counter)
            if not (self.unit(att.id) and self.unit(att.id).alive):
                break

    def resolve_combat(self, blue_attacks: list[dict], red_attacks: list[dict],
                       decision_fn: Optional[Callable] = None):
        """
        Fase de combate completa.

        ``decision_fn(state, engagement, team) -> 'continue'|'stop'`` é a
        política de decisão de rodada de batalha de cada time (bots).
        """
        self._event("attacks_declared", team="blue", state=self.snapshot(),
                    attacks=blue_attacks)
        self._event("attacks_declared", team="red", state=self.snapshot(),
                    attacks=red_attacks)
        queue = self._build_combat_queue(blue_attacks, red_attacks)

        for eng in queue:
            eng["battleRound"] = 1
            result = self._resolve_battle_round(eng)
            done = (result is None or not result.ok
                    or eng["maxBattleRounds"] == 1 or result.destroyed)
            if not done:
                if decision_fn is not None:
                    blue_dec = decision_fn(self, eng, "blue")
                    red_dec = decision_fn(self, eng, "red")
                else:
                    blue_dec = red_dec = "stop"
                if not (blue_dec == "stop" and red_dec == "stop"):
                    init_team = None
                    if blue_dec == "continue" and red_dec == "stop":
                        init_team = "blue"
                    if red_dec == "continue" and blue_dec == "stop":
                        init_team = "red"
                    eng["battleRound"] = 2
                    self._resolve_battle_round(eng, init_team)
                    self._resolve_counter_attacks(eng, blue_dec, red_dec)
            eng["status"] = "ended"
            self.engagement_records.append(eng)

        self._finish_combat_phase()

    def _return_aircraft_to_bases(self):
        for u in self.units:
            if u.category != "air" or not u.alive or u.air_status != "airborne":
                continue
            if u.base_unit_id:
                base = self.unit(u.base_unit_id)
                if base is not None and base.alive:
                    u.col, u.row = base.col, base.row
            else:
                u.col, u.row = u.base_hex["col"], u.base_hex["row"]
            u.fuel["wasAtRefuelLocation"] = True

    def _finish_combat_phase(self):
        self._return_aircraft_to_bases()
        winner = self.check_winner()
        if winner:
            self._end_game(winner, "victory")
            return
        self._next_turn()
        if self.turn > self.max_turns:
            obj = self.compute_objectives()
            blue_prog = obj["blue"]["achieved"] / obj["blue"]["needed"]
            red_prog = obj["red"]["achieved"] / obj["red"]["needed"]
            winner = "red" if red_prog > blue_prog else "blue"
            self._log(f"⏱ Limite operacional de {self.max_turns} dias — "
                      "adjudicação por progresso.")
            self._end_game(winner, "timeout")

    def _end_game(self, winner: str, reason: str):
        self.winner = winner
        self.end_reason = reason
        side = "Força Azul" if winner == "blue" else "Força Vermelha"
        self._log(f"🏆 {side} VENCEU! ({reason})")
        self._event("game_over", winner=winner, reason=reason,
                    objectives=self.compute_objectives(), state=self.snapshot())

    def _next_turn(self):
        # Recompletamento de munição (porte de nextTurn)
        port_hexes = {(u.col, u.row) for u in self.units
                      if u.team == "blue" and u.alive and u.type == "porto"}
        for u in self.units:
            if not u.alive or not u.init_weapons:
                continue
            reload_ok = False
            if u.team == "blue":
                if u.category == "land":
                    reload_ok = True
                elif u.category == "air":
                    reload_ok = u.fuel.get("wasAtRefuelLocation") is True
                elif not u.moved and u.category in ("surface", "submarine"):
                    reload_ok = (u.col, u.row) in port_hexes
            else:
                if u.category == "air":
                    reload_ok = u.fuel.get("wasAtRefuelLocation") is True
            if reload_ok:
                # Φ logístico (ciber): recompletamento parcial sob ataque
                # cibernético à cadeia logística.
                phi_log = self.phi[u.team].logistics
                restored = []
                for wpn, init in u.init_weapons.items():
                    cur = u.weapons.get(wpn, {}).get("quantity", 0)
                    target_qty = max(1, round(init["quantity"] * phi_log))
                    if cur < target_qty:
                        u.weapons[wpn] = {**copy.deepcopy(init),
                                          "quantity": target_qty}
                        restored.append(wpn.upper())
                if restored:
                    self._log(f"🔄 {u.name} recompletou: {', '.join(restored)}"
                              + (f" (Φlog={phi_log:.2f})"
                                 if phi_log < 1.0 else ""))

        # Reabastecimento naval por empilhamento com provedor
        for u in self.units:
            if not u.alive or u.fuel.get("fuelType") != "naval":
                continue
            has_provider = any(
                o.id != u.id and o.team == u.team and o.col == u.col
                and o.row == u.row and o.is_refuel_provider()
                for o in self.units)
            if has_provider and u.fuel["current"] < u.fuel["max"]:
                phi_log = self.phi[u.team].logistics
                u.fuel["current"] = max(u.fuel["current"],
                                        round(u.fuel["max"] * phi_log))
                self._log(f"⛽ {u.name} reabasteceu.")

        # Aeronaves em base → prontas com FP cheio
        for u in self.units:
            if u.category == "air" and u.fuel.get("wasAtRefuelLocation"):
                u.air_status = "ready"
                u.fuel["current"] = u.fuel["max"]
                u.fuel["wasAtRefuelLocation"] = False

        for u in self.units:
            u.moved = False
            if "spentThisTurn" in u.fuel:
                u.fuel["spentThisTurn"] = 0

        self.period = "night" if self.period == "day" else "day"
        if self.period == "day":
            self.turn += 1
        per = "Diurno" if self.period == "day" else "Noturno"
        self._log(f"──── Turno {self.turn} · Período {per} ────")


def _outcome_dict(out: sv.SalvoOutcome) -> dict:
    return {
        "ok": out.ok, "reason": out.reason, "weapon": out.weapon_type,
        "launched": out.launched, "chi": out.chi,
        "t_atq": round(out.t_atq, 3), "t_def": round(out.t_def, 3),
        "intercepted": round(out.intercepted, 2),
        "leakers": round(out.leakers, 2), "damage": round(out.damage, 2),
        "destroyed": out.destroyed, "remainingHp": out.remaining_hp,
    }


# ── Laço de partida completa (bot × bot) ─────────────────────────────────────

def play_game(*,
              blue_bot, red_bot,
              oob: Optional[dict] = None,
              max_turns: int = MAX_TURNS_DEFAULT,
              stochastic: bool = True,
              chi: float = sv.DEFAULT_CHI,
              seed: Optional[int] = None,
              blue_cyber=None, red_cyber=None,
              fog_of_war: bool = False,
              on_turn: Optional[Callable[["GameState"], None]] = None) -> GameState:
    """
    Executa uma partida construtiva completa entre dois bots.

    Cada bot implementa ``moves(state, team)``, ``attacks(state, team)`` e
    ``battle_round_decision(state, engagement, team)``.
    """
    state = GameState(oob=oob, max_turns=max_turns, stochastic=stochastic,
                      chi=chi, seed=seed, blue_cyber=blue_cyber,
                      red_cyber=red_cyber, fog_of_war=fog_of_war)

    def decision(st, eng, team):
        bot = blue_bot if team == "blue" else red_bot
        return bot.battle_round_decision(st, eng, team)

    guard = 0
    while state.winner is None and guard < max_turns * 2 + 4:
        guard += 1
        state.apply_moves("blue", blue_bot.moves(state, "blue"))
        state.apply_moves("red", red_bot.moves(state, "red"))
        blue_atk = blue_bot.attacks(state, "blue")
        red_atk = red_bot.attacks(state, "red")
        state.resolve_combat(blue_atk, red_atk, decision_fn=decision)
        if on_turn is not None:
            on_turn(state)
    if state.winner is None:
        # salvaguarda: adjudicação por progresso
        obj = state.compute_objectives()
        blue_prog = obj["blue"]["achieved"] / obj["blue"]["needed"]
        red_prog = obj["red"]["achieved"] / obj["red"]["needed"]
        state._end_game("red" if red_prog > blue_prog else "blue", "timeout")
    return state
