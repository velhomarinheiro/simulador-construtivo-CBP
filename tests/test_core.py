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


# ── Domínio cibernético ──────────────────────────────────────────────────────

def test_phi_sigmoid_properties():
    from cbp_sim.cyber import phi_sigmoid
    assert phi_sigmoid(0.0) == 1.0
    assert phi_sigmoid(1.0, r0=1.0) == pytest.approx(0.5)
    assert phi_sigmoid(100.0) < 0.01


def test_compute_phi_asymmetry():
    from cbp_sim.cyber import CyberForce, compute_phi
    blue = CyberForce()                      # sem ciber
    red = CyberForce(c2=2, sen=2, wpn=3, log=2)
    phi_blue = compute_phi(blue, red)        # Azul sofre o ciber vermelho
    phi_red = compute_phi(red, blue)         # Vermelho não sofre nada
    assert phi_blue.offense < 1.0
    assert phi_blue.detection < 1.0
    assert phi_blue.logistics < 1.0
    assert phi_red.offense == 1.0
    assert phi_red.logistics == 1.0
    # contra-ciber próprio atenua a degradação
    blue2 = CyberForce(c2=2, sen=2, wpn=3, log=2)
    phi_blue2 = compute_phi(blue2, red)
    assert phi_blue2.offense > phi_blue.offense


def test_cyber_degrades_salvo_damage():
    st_plain = _mini_state(stochastic=False)
    st_cyber = GameState(seed=1, stochastic=False,
                         red_cyber={"C2": 3, "WPN": 4})
    for st in (st_plain, st_cyber):
        att = st.unit("RED-GE-1")
        dfd = st.unit("BLUE-FPSO1")
        dfd.col, dfd.row = att.col, att.row
    out_plain = sv.resolve_salvo(
        attacker=st_plain.unit("RED-GE-1"), defender=st_plain.unit("BLUE-FPSO1"),
        weapon_type="ascm", amount=2, distance=0, rng=st_plain.rng,
        stochastic=False, phi_offense=st_plain.phi["red"].offense)
    out_cyber = sv.resolve_salvo(
        attacker=st_cyber.unit("RED-GE-1"), defender=st_cyber.unit("BLUE-FPSO1"),
        weapon_type="ascm", amount=2, distance=0, rng=st_cyber.rng,
        stochastic=False, phi_offense=st_cyber.phi["red"].offense)
    # ciber azul inexistente → vermelho não é degradado; mas aqui o ciber é
    # VERMELHO, então é o AZUL que sofre — o ataque vermelho fica intacto
    assert out_cyber.damage == pytest.approx(out_plain.damage)
    # já o ataque azul é degradado pelo ciber vermelho
    assert st_cyber.phi["blue"].offense < 1.0


def test_cyber_game_runs_and_hurts_blue():
    base = play_game(blue_bot=HeuristicBot(), red_bot=HeuristicBot(),
                     seed=5, stochastic=False)
    cyber = play_game(blue_bot=HeuristicBot(), red_bot=HeuristicBot(),
                      seed=5, stochastic=False,
                      red_cyber={"C2": 4, "SEN": 4, "WPN": 5, "LOG": 4})
    assert cyber.winner in ("blue", "red")
    mb, mc = game_metrics(base), game_metrics(cyber)
    # sob ciber vermelho pesado, o desempenho azul não melhora
    assert mc["red_losses_pct"] <= mb["red_losses_pct"] + 1e-9


# ── Névoa de guerra ──────────────────────────────────────────────────────────

def test_detection_static_always_visible():
    st = GameState(seed=2, fog_of_war=True)
    visible_red = st.detected_enemy_ids("red")
    # infraestruturas azuis fixas são sempre conhecidas do vermelho
    assert "BLUE-FPSO1" in visible_red
    assert "BLUE-PORTO-S" in visible_red


def test_detection_limits_far_units():
    st = GameState(seed=2, fog_of_war=True)
    visible_blue = st.detected_enemy_ids("blue")
    # o CSG vermelho começa em P2 (col 15), longe de qualquer sensor azul
    assert "RED-GBPA" not in visible_blue


def test_fog_game_runs():
    st = play_game(blue_bot=HeuristicBot(), red_bot=HeuristicBot(),
                   seed=9, fog_of_war=True)
    assert st.winner in ("blue", "red")


# ── Custos calibráveis e pacotes de ameaça ───────────────────────────────────

def test_package_cost_with_custom_table_and_cyber():
    from cbp_sim.cbp import CYBER_COST_PER_POINT
    oob = load_order_of_battle()
    pkg = PRESET_PACKAGES[0]
    custom = {k: 1.0 for k in
              [s["id"] for s in oob["forces"]["blue"]]}
    assert package_cost(oob, pkg, custom) == pytest.approx(
        len(custom))
    cyber_pkg = next(p for p in PRESET_PACKAGES
                     if p.name == "Guerra Ciber Ofensiva")
    base = package_cost(oob, PRESET_PACKAGES[0])
    assert package_cost(oob, cyber_pkg) == pytest.approx(
        base + CYBER_COST_PER_POINT * sum(cyber_pkg.cyber.values()))


def test_threat_packages_apply_to_red():
    from cbp_sim.cbp import THREAT_PACKAGES
    oob = load_order_of_battle()
    reinforced = next(p for p in THREAT_PACKAGES
                      if p.name == "Ameaça Reforçada")
    oob2 = apply_package(oob, reinforced)
    ge1 = next(s for s in oob2["forces"]["red"] if s["id"] == "RED-GE-1")
    ge1_base = next(s for s in oob["forces"]["red"] if s["id"] == "RED-GE-1")
    assert ge1["stayingPower"] > ge1_base["stayingPower"]
    # lado azul intocado
    assert oob2["forces"]["blue"] == oob["forces"]["blue"]


def test_close_escort_doctrine_stacks_on_fpsos():
    from cbp_sim.bots import BotTuning
    bot = HeuristicBot(BotTuning(defend_assets=2))
    st = GameState(seed=4)
    moves = bot.moves(st, "blue")
    st.apply_moves("blue", moves)
    # após alguns turnos de aproximação, ao menos um combatente de
    # superfície deve estar empilhado sobre uma FPSO
    for _ in range(3):
        for u in st.units:
            u.moved = False
        st.apply_moves("blue", bot.moves(st, "blue"))
    fpso_hexes = {(u.col, u.row) for u in st.alive_units("blue")
                  if u.type == "fpso"}
    guards = [u for u in st.alive_units("blue")
              if u.category == "surface" and u.type != "fpso"
              and (u.col, u.row) in fpso_hexes]
    assert guards, "nenhum combatente estacionado sobre FPSO"


def test_escort_improves_fpso_survival():
    from cbp_sim.bots import BotTuning
    df0, _ = run_batch(blue_bot_factory=HeuristicBot,
                       red_bot_factory=HeuristicBot, n_runs=15)
    df2, _ = run_batch(
        blue_bot_factory=lambda: HeuristicBot(BotTuning(defend_assets=2)),
        red_bot_factory=HeuristicBot, n_runs=15)
    assert (df2["fpsos_surviving"].mean()
            >= df0["fpsos_surviving"].mean())


# ── Aprendizado por reforço ──────────────────────────────────────────────────

def test_episode_reward_mission_orientation():
    from cbp_sim.bots import RewardWeights, episode_reward
    m_good_blue = {"winner": "blue", "fpsos_surviving": 4,
                   "port_integrity_pct": 100.0, "blue_losses_pct": 0.0,
                   "red_losses_pct": 80.0}
    m_bad_blue = {"winner": "red", "fpsos_surviving": 0,
                  "port_integrity_pct": 20.0, "blue_losses_pct": 60.0,
                  "red_losses_pct": 10.0}
    w = RewardWeights()
    assert episode_reward(m_good_blue, "blue", w) > episode_reward(
        m_bad_blue, "blue", w)
    # espelho: o mesmo desfecho ruim p/ Azul é bom p/ Vermelho
    assert episode_reward(m_bad_blue, "red", w) > episode_reward(
        m_good_blue, "red", w)


def test_reinforce_update_raises_action_probability():
    rng = np.random.default_rng(0)
    pol = MLPolicy(hidden=32, seed=5)
    X = rng.normal(size=(4, 9, 10, 16)).astype(np.float32)
    actions = np.array([3, 17, 42, 99])
    masks = np.zeros((4, 160), dtype=bool)
    masks[:, :120] = True                       # ações legais
    adv = np.ones(4, dtype=np.float32)          # vantagem positiva

    def probs():
        z = pol.logits(X)
        z = np.where(masks, z, -1e9)
        z -= z.max(axis=1, keepdims=True)
        e = np.exp(z)
        p = e / e.sum(axis=1, keepdims=True)
        return p[np.arange(4), actions]

    before = probs()
    for _ in range(20):
        pol.reinforce_update(X, actions, masks, adv, entropy_coef=0.0)
    after = probs()
    assert (after > before).all()


def test_rl_trainer_end_to_end():
    from cbp_sim.bots import RLTrainer
    mv = MLPolicy(hidden=32, seed=1)
    atk = MLPolicy(hidden=32, seed=2)
    w1 = mv.W1.copy()
    tr = RLTrainer(move_policy=mv, attack_policy=atk, team="blue", seed=3)
    hist = tr.train(iterations=2, episodes_per_iter=3)
    assert len(hist["win_rate"]) == 2
    assert not np.allclose(w1, mv.W1)           # política atualizada
    # o par de redes refinadas joga uma partida completa
    st = play_game(blue_bot=MLBot(mv, atk), red_bot=HeuristicBot(),
                   seed=42, max_turns=4)
    assert st.winner in ("blue", "red")


def test_rlbot_records_trajectory():
    from cbp_sim.bots import RLBot
    import numpy as _np
    bot = RLBot(MLPolicy(hidden=32, seed=1), MLPolicy(hidden=32, seed=2),
                rng=_np.random.default_rng(0), temperature=1.0)
    st = GameState(seed=8)
    st.apply_moves("blue", bot.moves(st, "blue"))
    assert bot.move_decisions, "nenhuma decisão de movimento registrada"
    phase_id, action, mask = bot.move_decisions[0]
    assert mask[action], "ação amostrada fora da máscara legal"
    assert bot.phase_features[phase_id].shape == (9, 10, 16)


# ── Serialização OOB ↔ CSV ───────────────────────────────────────────────────

def test_oob_csv_roundtrip_preserves_fields():
    from cbp_sim.oob_io import csv_to_oob, oob_to_csv
    oob = load_order_of_battle()
    oob2 = csv_to_oob(oob_to_csv(oob))

    def nz(d):  # normaliza: entradas zero equivalem a ausência (idem no motor)
        return {k: v for k, v in (d or {}).items() if v}

    for team in ("blue", "red"):
        a = {s["id"]: s for s in oob["forces"][team]}
        b = {s["id"]: s for s in oob2["forces"][team]}
        assert set(a) == set(b)
        for uid in a:
            sa, sb = a[uid], b[uid]
            assert sa["stayingPower"] == sb["stayingPower"]
            assert sa.get("movement", 0) == sb.get("movement", 0)
            assert sa["category"] == sb["category"]
            assert sa.get("weapons", {}) == sb.get("weapons", {})
            assert sa.get("capabilities", {}) == sb.get("capabilities", {})
            assert nz(sa.get("detectionRange")) == nz(sb.get("detectionRange"))
            assert nz(sa.get("attackRange")) == nz(sb.get("attackRange"))
            assert (sa.get("composition") or []) == (sb.get("composition") or [])


def test_oob_from_csv_is_playable():
    from cbp_sim.oob_io import csv_to_oob, oob_to_csv
    oob = csv_to_oob(oob_to_csv(load_order_of_battle()))
    st = play_game(blue_bot=HeuristicBot(), red_bot=HeuristicBot(),
                   oob=oob, seed=1)
    assert st.winner in ("blue", "red")


def test_minimal_csv_produces_valid_oob():
    from cbp_sim.oob_io import csv_to_oob
    csv = (
        "id,team,category,stayingPower,movement,col,row,weapons\n"
        "BLUE-X,blue,surface,4,3,3,4,mss:8:3\n"
        "RED-Y,red,surface,3,4,12,5,ascm:6:6\n"
    )
    oob = csv_to_oob(csv)
    assert len(oob["forces"]["blue"]) == 1
    assert len(oob["forces"]["red"]) == 1
    bx = oob["forces"]["blue"][0]
    assert bx["weapons"]["mss"] == {"quantity": 8, "range": 3}
    assert bx["position"] == {"col": 3, "row": 4}


def test_csv_rejects_single_sided_force():
    from cbp_sim.oob_io import csv_to_oob
    with pytest.raises(ValueError):
        csv_to_oob("id,team,category,stayingPower\nBLUE-X,blue,surface,4\n")
