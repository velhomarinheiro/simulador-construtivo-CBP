"""Página: partida construtiva única (bot × bot), turno a turno."""

import copy

import pandas as pd
import streamlit as st

from app_utils import (BOT_OPTIONS, get_oob, make_bot, map_figure, page_setup)
from cbp_sim.bots import BotTuning
from cbp_sim.engine import play_game
from cbp_sim.montecarlo import game_metrics

page_setup("Simulação")
st.title("🎯 Simulação Construtiva — partida única")

with st.sidebar:
    st.header("Configuração")
    blue_kind = st.selectbox("Bot Força Azul", BOT_OPTIONS, key="sim_blue")
    red_kind = st.selectbox("Bot Força Vermelha", BOT_OPTIONS, key="sim_red")
    stochastic = st.toggle("Modo estocástico (tabelas d6)", value=True,
                           help="Desligado: regime determinístico da equação "
                                "de salva (valores esperados).")
    chi = st.slider("χ — admissibilidade marginal", 0.0, 1.0, 0.5, 0.05,
                    help="Nível marginal da matriz de admissibilidade "
                         "multidomínio (ex.: ASW aéreo contra submarino).")
    max_turns = st.slider("Limite operacional (dias)", 4, 24, 12)
    seed = st.number_input("Semente aleatória", 0, 999_999, 42)
    fog = st.toggle("Névoa de guerra (detecção limitada)", value=False,
                    help="Bots só engajam alvos detectados pelos alcances "
                         "de detecção (noite reduz 1 hex; infraestrutura "
                         "fixa é sempre conhecida). Sem contato, o Azul "
                         "assume estações defensivas junto às FPSOs/portos.")
    aggr_blue = st.slider("Agressividade bot Azul", 0.0, 1.0, 1.0, 0.1)
    aggr_red = st.slider("Agressividade bot Vermelho", 0.0, 1.0, 1.0, 0.1)
    escort = st.slider("Escolta cerrada de FPSOs (Azul)", 0, 4, 0,
                       help="Combatentes de superfície destacados para "
                            "empilhar sobre as FPSOs, somando interceptação "
                            "à defesa do ativo (defesa em grupo). 0 = "
                            "doutrina original do wargame.")
    with st.expander("⚡ Guerra cibernética (domínio X)"):
        st.caption("Estoques por subtipo. O ciber oponente degrada a "
                   "eficácia cinética via modulador Φ (naval_salvo): "
                   "ofensiva (C2/WPN), interceptação (SEN/WPN), detecção "
                   "(SEN/C2) e logística (LOG).")
        c1, c2 = st.columns(2)
        blue_cyber, red_cyber = {}, {}
        with c1:
            st.markdown("**🔵 Azul**")
            for s in ("C2", "SEN", "WPN", "LOG"):
                blue_cyber[s] = st.slider(s, 0, 5, 0, key=f"sim_bc_{s}")
        with c2:
            st.markdown("**🔴 Vermelha**")
            for s in ("C2", "SEN", "WPN", "LOG"):
                red_cyber[s] = st.slider(s, 0, 5, 0, key=f"sim_rc_{s}")
    run = st.button("▶️ Executar partida", type="primary",
                    use_container_width=True)

if run:
    blue_bot = make_bot(blue_kind, BotTuning(aggressiveness=aggr_blue,
                                             defend_assets=int(escort)))
    red_bot = make_bot(red_kind, BotTuning(aggressiveness=aggr_red))
    snapshots = []

    def on_turn(state):
        snapshots.append({
            "turn": state.turn, "period": state.period,
            "units": copy.deepcopy(state.snapshot()["units"]),
            "objectives": state.compute_objectives(),
            "log_len": len(state.log),
        })

    with st.spinner("Simulando..."):
        state = play_game(
            blue_bot=blue_bot, red_bot=red_bot,
            oob=copy.deepcopy(get_oob()), max_turns=max_turns,
            stochastic=stochastic, chi=chi, seed=int(seed),
            blue_cyber=blue_cyber, red_cyber=red_cyber,
            fog_of_war=fog, on_turn=on_turn)
    st.session_state["single_game"] = {
        "state_log": state.log,
        "snapshots": snapshots,
        "metrics": game_metrics(state),
        "objectives": state.compute_objectives(),
        "engagements": state.engagement_records,
        "events": state.events,
        "winner": state.winner,
        "config": {"blue": blue_kind, "red": red_kind,
                   "estocástico": stochastic, "χ": chi,
                   "semente": int(seed), "névoa": fog,
                   "ciber Azul": blue_cyber, "ciber Vermelha": red_cyber},
    }

game = st.session_state.get("single_game")
if not game:
    st.info("Configure os bots na barra lateral e clique em "
            "**Executar partida**.")
    st.stop()

m = game["metrics"]
winner_txt = "🔵 Força Azul" if game["winner"] == "blue" else "🔴 Força Vermelha"
st.success(f"**{winner_txt} venceu** — "
           f"{'vitória por objetivos' if m['end_reason'] == 'victory' else 'adjudicação por limite operacional'} "
           f"no dia {m['turns']}.")

c = st.columns(6)
c[0].metric("Dias de campanha", m["turns"])
c[1].metric("FPSOs sobreviventes", f"{m['fpsos_surviving']}/4")
c[2].metric("Integridade dos portos", f"{m['port_integrity_pct']:.0f}%")
c[3].metric("Perdas Azul (SP)", f"{m['blue_losses_pct']:.0f}%")
c[4].metric("Perdas Vermelha (SP)", f"{m['red_losses_pct']:.0f}%")
xr = m["exchange_ratio"]
c[5].metric("Razão de troca", "∞" if xr == float("inf") else f"{xr:.2f}")

tab_map, tab_obj, tab_eng, tab_log = st.tabs(
    ["🗺️ Evolução no mapa", "🎯 Objetivos", "⚔️ Engajamentos", "📜 Log"])

with tab_map:
    snaps = game["snapshots"]
    if snaps:
        labels = [f"Fim do turno {s['turn']}·"
                  f"{'D' if s['period'] == 'day' else 'N'}" for s in snaps]
        idx = st.select_slider("Instante", options=list(range(len(snaps))),
                               value=len(snaps) - 1,
                               format_func=lambda i: labels[i])
        snap = snaps[idx]
        st.plotly_chart(
            map_figure(snap["units"], height=560,
                       title=f"Situação — {labels[idx]}"),
            use_container_width=True)

with tab_obj:
    obj = game["objectives"]
    c1, c2 = st.columns(2)
    for col, side, label in ((c1, "blue", "🔵 Força Azul"),
                             (c2, "red", "🔴 Força Vermelha")):
        with col:
            o = obj[side]
            st.markdown(f"### {label} — {o['achieved']}/{o['needed']}")
            for cond in o["conditions"]:
                icon = "✅" if cond["met"] else "❌"
                cur = f" · {cond['current']}" if cond.get("current") else ""
                st.markdown(f"{icon} {cond['label']}{cur}")

with tab_eng:
    rows = []
    for e in game["engagements"]:
        for r in e["results"]:
            out = r["outcome"]
            rows.append({
                "Engajamento": e["id"], "Rodada": r["battleRound"],
                "Atacante": e["attackerId"], "Alvo": e["targetId"],
                "Arma": out.get("weapon", e["weaponType"]),
                "Lançados": out.get("launched", 0),
                "χ": out.get("chi", 1.0),
                "T_atq": out.get("t_atq", 0.0),
                "T_def": out.get("t_def", 0.0),
                "Intercept.": out.get("intercepted", 0),
                "Dano (SP)": out.get("damage", 0.0),
                "Destruído": "💥" if out.get("destroyed") else "",
            })
    if rows:
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True, height=480)
        st.caption("T_atq / T_def são os termos ofensivo e defensivo da "
                    "equação de salva (valores esperados em SP); o dano "
                    "aplicado é o resultado adjudicado.")
        st.download_button("⬇️ Baixar engajamentos (CSV)",
                           df.to_csv(index=False).encode("utf-8"),
                           "engajamentos.csv", "text/csv")
    else:
        st.info("Sem engajamentos registrados.")

with tab_log:
    st.code("\n".join(game["state_log"]), language=None)
