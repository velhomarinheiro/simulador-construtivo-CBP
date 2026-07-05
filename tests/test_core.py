"""Testes do núcleo do simulador construtivo."""

import copy

import numpy as np
import pytest

from cbp_sim import hexmap as hx
from cbp_sim import salvo as sv
from cbp_sim.bots import (HeuristicBot, MLBot, MLPolicy,
                          build_training_samples)
from cbp_sim.cbp import PRESET_PACKAGES, apply_package, package_cost
from cbp_sim.engine import GameState, load_order_of_battle, play_game
from cbp_sim.montecarlo import game_metrics, run_batch, summarize


# ── Hex ──────────────────────────────────────────────────────────────────────

def test_hex_dist_symmetry_and_neighbors():
    assert hx.hex_dist(0, 0, 0, 0) == 0
    assert hx.hex_dist(3, 4, 5, 4) == hx.hex_dist(5, 4, 3, 4)
    for nb in hx.hex_neighbors(5, 5):
        assert hx.hex_dist(5, 5, *nb) == 1


def test_terrain_rules():
    assert not hx.can_enter_terrain("surface", hx.T_LAND)
    assert not hx.can_enter_terrain("submarine", hx.T_SHALLOW)
    assert hx.can_enter_terrain("air", hx.T_LAND)
    assert hx.can_enter_terrain("land", hx.T_SHALLOW)


# ── Salva multidomínio ───────────────────────────────────────────────────────

def test_canonical_matrix_structure():
    M = sv.canonical_matrix(0.5)
    assert M.shape == (5, 5)
    # U→A é estruturalmente nulo (torpedo não alcança aeronave)
    assert M[sv.DOMAIN_INDEX["U"], sv.DOMAIN_INDEX["A"]] == 0.0
    # S→S é primário
    assert M[sv.DOMAIN_INDEX["S"], sv.DOMAIN_INDEX["S"]] == 1.0
    # χ aparece nas células marginais
    assert M[sv.DOMAIN_INDEX["S"], sv.DOMAIN_INDEX["U"]] == 0.5


def test_lethality_calibration_matches_d6_tables():
    # ASCM vs superfície: faces 4-6 dão 1d6 → E = 3 * 3.5 / 6 = 1.75
    assert sv.lethality("blue", "ascm", "surface") == pytest.approx(1.75)
    # defesa aérea intercepta com faces 5-6 → p = 1/3
    assert sv.intercept_probability("blue", "airDefense") == pytest.approx(1 / 3)


def _mini_state(**kwargs):
    return GameState(seed=1, **kwargs)


def test_salvo_deterministic_offense_minus_defense():
    st = _mini_state(stochastic=False)
    att = st.unit("RED-GE-1")       # 14 ASCM
    dfd = st.unit("BLUE-SAG-S1")    # airDefense 6
    dfd.col, dfd.row = att.col, att.row  # coloca ao alcance
    out = sv.resolve_salvo(
        attacker=att, defender=dfd, defenders_stack=[dfd],
        weapon_type="ascm", amount=4, distance=0, rng=st.rng,
        stochastic=False, chi=0.5)
    assert out.ok
    # T_atq = 4 lançados × 1.75; interceptação esperada = 4 × 1/3
    assert out.launched == 4
    assert out.intercepted == pytest.approx(4 / 3)
    assert out.leakers == pytest.approx(4 - 4 / 3)
    assert out.damage == pytest.approx(out.leakers * 1.75, rel=1e-6)


def test_salvo_inadmissible_pair_null():
    st = _mini_state()
    sub = st.unit("BLUE-SUB-1")
    caca = st.unit("RED-KMF-1")
    caca.col, caca.row = sub.col, sub.row
    # Torpedo (domínio U) contra aeronave (A): alvo nem consta do perfil,
    # e ainda que constasse, χ(U→A) = 0.
    out = sv.resolve_salvo(
        attacker=sub, defender=caca, weapon_type="torpedo", amount=1,
        distance=0, rng=st.rng)
    assert not out.ok


def test_salvo_spends_ammo():
    st = _mini_state(stochastic=False)
    att = st.unit("BLUE-SUB-N")
    dfd = st.unit("RED-GLOG")
    q0 = att.weapon_quantity("ascm")
    dfd.col, dfd.row = att.col, att.row
    sv.resolve_salvo(attacker=att, defender=dfd, weapon_type="ascm",
                     amount=2, distance=0, rng=st.rng, stochastic=False)
    assert att.weapon_quantity("ascm") == q0 - 2


# ── Motor ────────────────────────────────────────────────────────────────────

def test_objectives_initial_state():
    st = _mini_state()
    obj = st.compute_objectives()
    assert obj["blue"]["achieved"] == 0
    assert obj["red"]["achieved"] == 0
    assert st.check_winner() is None


def test_full_game_reproducible():
    a = play_game(blue_bot=HeuristicBot(), red_bot=HeuristicBot(), seed=7)
    b = play_game(blue_bot=HeuristicBot(), red_bot=HeuristicBot(), seed=7)
    assert a.winner == b.winner
    assert a.turn == b.turn
    assert [u.hp for u in a.units] == [u.hp for u in b.units]


def test_full_game_deterministic_mode():
    st = play_game(blue_bot=HeuristicBot(), red_bot=HeuristicBot(),
                   seed=3, stochastic=False)
    assert st.winner in ("blue", "red")
    m = game_metrics(st)
    assert 0 <= m["fpsos_surviving"] <= 4
    assert 0 <= m["port_integrity_pct"] <= 100


def test_batch_and_summary():
    df, trails = run_batch(blue_bot_factory=HeuristicBot,
                           red_bot_factory=HeuristicBot,
                           n_runs=5, collect_events=True)
    assert len(df) == 5
    s = summarize(df)
    assert 0.0 <= s["p_blue_win"] <= 1.0
    assert len(trails) == 5


# ── Bots ─────────────────────────────────────────────────────────────────────

def test_ml_pipeline_end_to_end():
    _, trails = run_batch(blue_bot_factory=HeuristicBot,
                          red_bot_factory=HeuristicBot,
                          n_runs=3, collect_events=True)
    mv, atk = [], []
    for t in trails:
        m, a = build_training_samples(t["events"])
        mv += m
        atk += a
    assert mv and atk
    pol = MLPolicy(hidden=32)
    hist = pol.train(mv, epochs=2)
    assert hist["best_val_acc"] >= 0.0
    # roundtrip de persistência
    pol2 = MLPolicy.from_bytes(pol.to_bytes())
    x = np.zeros((1, 9, 10, 16), dtype=np.float32)
    assert np.allclose(pol.logits(x), pol2.logits(x))
    # bot ML joga uma partida completa
    st = play_game(blue_bot=MLBot(pol, pol), red_bot=HeuristicBot(),
                   seed=11, max_turns=4)
    assert st.winner in ("blue", "red")


# ── CBP ──────────────────────────────────────────────────────────────────────

def test_packages_apply_and_cost():
    oob = load_order_of_battle()
    base_cost = package_cost(oob, PRESET_PACKAGES[0])
    no_sub = next(p for p in PRESET_PACKAGES
                  if p.name == "Sem Submarino Nuclear")
    oob2 = apply_package(oob, no_sub)
    ids = [s["id"] for s in oob2["forces"]["blue"]]
    assert "BLUE-SUB-N" not in ids
    assert package_cost(oob, no_sub) < base_cost
    # reforço escala SP e armas
    reinforce = next(p for p in PRESET_PACKAGES
                     if p.name == "Reforço de Escoltas")
    oob3 = apply_package(oob, reinforce)
    sag1 = next(s for s in oob3["forces"]["blue"] if s["id"] == "BLUE-SAG-S1")
    sag1_base = next(s for s in oob["forces"]["blue"]
                     if s["id"] == "BLUE-SAG-S1")
    assert sag1["stayingPower"] > sag1_base["stayingPower"]
    assert (sag1["weapons"]["mss"]["quantity"]
            > sag1_base["weapons"]["mss"]["quantity"])
    # pacote não muta a OOB original
    assert sag1_base["stayingPower"] == 9
