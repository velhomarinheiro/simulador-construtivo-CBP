"""Página: doutrina do bot heurístico e treinamento do bot de ML."""

import copy

import pandas as pd
import plotly.express as px
import streamlit as st

from app_utils import get_oob, page_setup
from cbp_sim.bots import (BotTuning, HeuristicBot, MLBot, MLPolicy,
                          RLTrainer, RewardWeights, build_training_samples)
from cbp_sim.montecarlo import run_batch, summarize

page_setup("Bots")
st.title("🤖 Bots — doutrina heurística e aprendizado de máquina")

tab_h, tab_ml, tab_rl, tab_eval = st.tabs(
    ["⚙️ Bot heurístico", "🧠 Clonagem comportamental",
     "🎓 Aprendizado por reforço", "⚔️ Avaliação ML × Heurístico"])

# ── Heurístico ────────────────────────────────────────────────────────────────
with tab_h:
    st.markdown("""
    O bot heurístico porta a IA do wargame Operação Atlântico Sul: doutrina
    **orientada a objetivos** (persegue exatamente as condições de vitória,
    re-tarefando ao cumpri-las), proteção da logística própria com escolta,
    gerência de combustível e decisão de rodada de batalha por estado da
    própria unidade e do alvo.
    """)
    st.info("Os parâmetros abaixo são usados como padrão nas demais páginas "
            "quando o bot heurístico é selecionado nesta sessão.")
    t = st.session_state.get("bot_tuning", BotTuning())
    c1, c2, c3 = st.columns(3)
    aggressiveness = c1.slider("Agressividade", 0.0, 1.0,
                               t.aggressiveness, 0.05,
                               help="Menor = mais distraível para defesa "
                                    "oportunista.")
    opportunity = c2.slider("Raio de oportunidade (hex)", 0, 5,
                            t.opportunity_radius)
    flee = c3.slider("Raio de fuga da logística (hex)", 1, 8,
                     t.logistics_flee_radius)
    c1, c2, c3 = st.columns(3)
    stop_frac = c1.slider("Recuar abaixo de (fração de SP)", 0.1, 0.9,
                          t.stop_hp_frac, 0.05)
    finish = c2.slider("...exceto se alvo a (SP) de cair", 0.0, 5.0,
                       float(t.finish_hp_threshold), 0.5)
    escort = c3.slider("Escolta cerrada de FPSOs (Azul)", 0, 4,
                       int(t.defend_assets),
                       help="Combatentes de superfície destacados para "
                            "empilhar sobre as FPSOs, somando interceptação "
                            "à defesa do ativo. 0 = doutrina original. "
                            "Alavanca de análise: mais escolta protege a "
                            "infraestrutura, mas drena a força ofensiva.")
    if st.button("Salvar doutrina", type="primary"):
        st.session_state["bot_tuning"] = BotTuning(
            aggressiveness=aggressiveness, opportunity_radius=int(opportunity),
            logistics_flee_radius=int(flee), stop_hp_frac=stop_frac,
            finish_hp_threshold=finish, defend_assets=int(escort))
        st.success("Doutrina do bot heurístico atualizada.")

# ── Treinamento ML ────────────────────────────────────────────────────────────
with tab_ml:
    st.markdown("""
    O bot de ML aprende por **clonagem comportamental** (imitation
    learning), como no pipeline `ml/train_bot.py` do wargame: o estado do
    tabuleiro vira um tensor 9×10×16 e duas redes aprendem a pontuar os 160
    hexes — uma para o **destino de movimento**, outra para o **hex do
    alvo**. O dataset vem de partidas construtivas registradas (self-play).
    """)

    trails = st.session_state.get("event_trails", [])
    c1, c2 = st.columns([2, 3])
    with c1:
        st.metric("Partidas registradas na sessão", len(trails))
        n_extra = st.slider("Gerar partidas adicionais (self-play)",
                            0, 200, 30 if not trails else 0, 10)
        if st.button("🎮 Gerar dataset de self-play"):
            prog = st.progress(0.0)
            _, new_trails = run_batch(
                blue_bot_factory=HeuristicBot, red_bot_factory=HeuristicBot,
                n_runs=int(n_extra), oob=copy.deepcopy(get_oob()),
                collect_events=True, base_seed=len(trails) * 1000,
                progress=lambda d, t: prog.progress(d / t))
            prog.empty()
            trails = trails + new_trails
            st.session_state["event_trails"] = trails
            st.success(f"{n_extra} partidas geradas — total {len(trails)}.")
            st.rerun()
    with c2:
        imitate_winner = st.toggle("Imitar apenas o lado vencedor", value=True,
                                   help="Filtra o dataset para clonar somente "
                                        "as decisões da força que venceu cada "
                                        "partida.")
        hidden = st.select_slider("Neurônios na camada oculta",
                                  [64, 128, 256, 512], 256)
        epochs = st.slider("Épocas", 5, 60, 20, 5)

    if st.button("🧠 Treinar redes (movimento + ataque)", type="primary",
                 disabled=not trails):
        mv_all, atk_all = [], []
        for tr in trails:
            mv, atk = build_training_samples(
                tr["events"], winner=tr.get("winner"),
                imitate_winner_only=imitate_winner)
            mv_all += mv
            atk_all += atk
        st.write(f"Dataset: **{len(mv_all)}** exemplos de movimento, "
                 f"**{len(atk_all)}** de ataque.")
        hist_area = st.empty()
        prog = st.progress(0.0, text="Treinando move_net...")

        def cb_factory(label, offset):
            def cb(ep, total, hist):
                prog.progress(offset + ep / total / 2,
                              text=f"{label} — época {ep}/{total} · "
                                   f"val acc {hist['val_acc'][-1]:.1%}")
            return cb

        move_pol = MLPolicy(hidden=int(hidden))
        h1 = move_pol.train(mv_all, epochs=int(epochs),
                            progress=cb_factory("move_net", 0.0))
        atk_pol = MLPolicy(hidden=int(hidden))
        h2 = atk_pol.train(atk_all, epochs=int(epochs),
                           progress=cb_factory("attack_net", 0.5))
        prog.empty()
        st.session_state["ml_policies"] = {"move": move_pol, "attack": atk_pol}
        st.session_state["ml_history"] = {"move": h1, "attack": h2}
        st.success(f"Treino concluído — move_net val acc "
                   f"{h1['best_val_acc']:.1%}, attack_net "
                   f"{h2['best_val_acc']:.1%}. O bot **ML** já está "
                   "disponível nas demais páginas.")

    hist = st.session_state.get("ml_history")
    if hist:
        dfs = []
        for name, h in hist.items():
            dfs.append(pd.DataFrame({"época": h["epochs"],
                                     "val acc": h["val_acc"], "rede": name}))
        fig = px.line(pd.concat(dfs), x="época", y="val acc", color="rede",
                      title="Acurácia de validação por época")
        st.plotly_chart(fig, use_container_width=True)

    st.divider()
    c1, c2 = st.columns(2)
    pol = st.session_state.get("ml_policies")
    with c1:
        st.markdown("#### ⬇️ Exportar modelo treinado")
        if pol and pol.get("move") is not None:
            c1a, c1b = st.columns(2)
            c1a.download_button("move_net (.npz)", pol["move"].to_bytes(),
                                "move_net.npz", use_container_width=True)
            c1b.download_button("attack_net (.npz)", pol["attack"].to_bytes(),
                                "attack_net.npz", use_container_width=True)
        else:
            st.caption("Treine um modelo para habilitar o download.")
    with c2:
        st.markdown("#### ⬆️ Importar modelo")
        up_m = st.file_uploader("move_net.npz", type=["npz"], key="up_move")
        up_a = st.file_uploader("attack_net.npz", type=["npz"], key="up_atk")
        if up_m is not None and up_a is not None:
            try:
                st.session_state["ml_policies"] = {
                    "move": MLPolicy.from_bytes(up_m.read()),
                    "attack": MLPolicy.from_bytes(up_a.read())}
                st.success("Modelos carregados — bot ML habilitado.")
            except Exception as e:  # noqa: BLE001
                st.error(f"Arquivo inválido: {e}")

# ── Aprendizado por reforço ───────────────────────────────────────────────────
with tab_rl:
    st.markdown("""
    Refina o bot por **REINFORCE em auto-jogo**: o agente joga partidas
    construtivas completas contra o bot heurístico, amostrando ações da
    softmax mascarada sobre os hexes legais, e recebe ao fim de cada
    episódio uma **recompensa orientada à missão** (vitória + proteção/
    destruição da infraestrutura − perdas próprias). As redes são
    atualizadas por gradiente de política com baseline de lote e bônus de
    entropia.

    Pipeline recomendado (como no AlphaGo): **1)** pré-treine por clonagem
    comportamental na aba anterior (*warm start*); **2)** refine aqui por
    reforço — assim o agente parte de uma política competente e o RL
    otimiza as MOEs, não apenas a imitação.
    """)
    has_bc = st.session_state.get("ml_policies") is not None
    c1, c2, c3 = st.columns(3)
    with c1:
        rl_team = st.radio("Lado do agente RL", ["blue", "red"],
                           format_func=lambda t: "🔵 Força Azul"
                           if t == "blue" else "🔴 Força Vermelha",
                           horizontal=True)
        warm = st.toggle("Warm start (redes da clonagem)", value=has_bc,
                         disabled=not has_bc,
                         help="Parte das redes treinadas por clonagem "
                              "comportamental. Sem warm start, o RL parte "
                              "de redes aleatórias (aprendizado lento).")
        rl_hidden = st.select_slider("Neurônios (se sem warm start)",
                                     [64, 128, 256], 128)
    with c2:
        iterations = st.slider("Iterações", 2, 100, 15)
        episodes = st.slider("Episódios por iteração", 4, 40, 12, 2)
        rl_fog = st.toggle("Treinar com névoa de guerra", value=False,
                           key="rl_fog")
    with c3:
        temperature = st.slider("Temperatura de exploração", 0.2, 2.0,
                                0.8, 0.1)
        entropy = st.slider("Bônus de entropia", 0.0, 0.05, 0.01, 0.005)
        st.caption("**Pesos da recompensa**")
        w_win = st.slider("Vitória", 0.0, 2.0, 1.0, 0.1, key="rl_w_win")
        w_mis = st.slider("Missão (infraestrutura)", 0.0, 2.0, 1.0, 0.1,
                          key="rl_w_mis")
        w_los = st.slider("Perdas próprias", 0.0, 2.0, 0.5, 0.1,
                          key="rl_w_los")

    if st.button("🎓 Treinar por reforço", type="primary"):
        if warm and has_bc:
            base = st.session_state["ml_policies"]
            mv_pol = MLPolicy.from_bytes(base["move"].to_bytes())
            atk_pol = MLPolicy.from_bytes(base["attack"].to_bytes())
        else:
            mv_pol = MLPolicy(hidden=int(rl_hidden), seed=1)
            atk_pol = MLPolicy(hidden=int(rl_hidden), seed=2)
        trainer = RLTrainer(
            move_policy=mv_pol, attack_policy=atk_pol, team=rl_team,
            opponent_factory=lambda: HeuristicBot(
                st.session_state.get("bot_tuning")),
            reward_weights=RewardWeights(win=w_win, mission=w_mis,
                                         losses=w_los),
            temperature=temperature, entropy_coef=entropy,
            fog_of_war=rl_fog, oob=copy.deepcopy(get_oob()))
        prog = st.progress(0.0, text="Treinando por reforço...")

        def cb(it, total, hist):
            prog.progress(it / total,
                          text=f"Iteração {it}/{total} · vitórias "
                               f"{hist['win_rate'][-1]:.0%} · recompensa "
                               f"{hist['mean_reward'][-1]:+.2f}")

        hist = trainer.train(iterations=int(iterations),
                             episodes_per_iter=int(episodes), progress=cb)
        prog.empty()
        st.session_state["ml_policies"] = {"move": mv_pol, "attack": atk_pol}
        st.session_state["rl_history"] = {"team": rl_team, **hist}
        st.success(f"Treino RL concluído — taxa de vitória final "
                   f"{hist['win_rate'][-1]:.0%} (média das últimas 3 "
                   f"iterações: {sum(hist['win_rate'][-3:]) / 3:.0%}). "
                   "As redes refinadas passam a ser o bot **ML** nas "
                   "demais páginas.")

    rl_hist = st.session_state.get("rl_history")
    if rl_hist:
        dfh = pd.DataFrame({"iteração": rl_hist["iteration"],
                            "taxa de vitória": rl_hist["win_rate"],
                            "recompensa média": rl_hist["mean_reward"]})
        c1, c2 = st.columns(2)
        with c1:
            fig = px.line(dfh, x="iteração", y="taxa de vitória",
                          title=f"Curva de aprendizado — lado "
                                f"{'Azul' if rl_hist.get('team') == 'blue' else 'Vermelho'}",
                          markers=True, range_y=[0, 1])
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            fig = px.line(dfh, x="iteração", y="recompensa média",
                          title="Recompensa média por iteração",
                          markers=True)
            st.plotly_chart(fig, use_container_width=True)

# ── Avaliação ─────────────────────────────────────────────────────────────────
with tab_eval:
    st.markdown("Avalie o bot ML jogando de **Azul** contra o heurístico "
                "de Vermelho (e vice-versa).")
    n_eval = st.slider("Partidas de avaliação por lado", 5, 100, 20, 5)
    if st.button("⚔️ Avaliar", type="primary",
                 disabled=st.session_state.get("ml_policies") is None):
        pol = st.session_state["ml_policies"]
        prog = st.progress(0.0)
        df1, _ = run_batch(
            blue_bot_factory=lambda: MLBot(pol["move"], pol["attack"]),
            red_bot_factory=HeuristicBot, n_runs=int(n_eval),
            oob=copy.deepcopy(get_oob()),
            progress=lambda d, t: prog.progress(d / t / 2,
                                                text="ML de Azul..."))
        df2, _ = run_batch(
            blue_bot_factory=HeuristicBot,
            red_bot_factory=lambda: MLBot(pol["move"], pol["attack"]),
            n_runs=int(n_eval), oob=copy.deepcopy(get_oob()),
            base_seed=777,
            progress=lambda d, t: prog.progress(0.5 + d / t / 2,
                                                text="ML de Vermelho..."))
        prog.empty()
        s1, s2 = summarize(df1), summarize(df2)
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("##### ML joga de 🔵 Azul")
            st.metric("P(vitória do ML)", f"{100 * s1['p_blue_win']:.0f}%")
            st.metric("FPSOs preservadas", f"{s1['mean_fpsos_surviving']:.2f}/4")
        with c2:
            st.markdown("##### ML joga de 🔴 Vermelho")
            st.metric("P(vitória do ML)", f"{100 * (1 - s2['p_blue_win']):.0f}%")
            st.metric("FPSOs destruídas",
                      f"{4 - s2['mean_fpsos_surviving']:.2f}/4")
        st.caption("Referência: heurístico × heurístico na página Monte "
                   "Carlo. Um ML bem treinado deve ao menos reproduzir o "
                   "desempenho do professor (clonagem) — ganhos além disso "
                   "exigem mais dados ou aprendizado por reforço.")
