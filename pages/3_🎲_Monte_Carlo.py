"""Página: lote Monte Carlo de replicações e distribuição de MOEs."""

import copy

import pandas as pd
import plotly.express as px
import streamlit as st

from app_utils import BOT_OPTIONS, get_oob, make_bot, page_setup
from cbp_sim.montecarlo import run_batch, summarize
from cbp_sim.reporting import batch_report_md

page_setup("Monte Carlo")
st.title("🎲 Monte Carlo — lote de replicações")

with st.sidebar:
    st.header("Configuração do lote")
    n_runs = st.slider("Replicações", 5, 500, 50, 5)
    blue_kind = st.selectbox("Bot Força Azul", BOT_OPTIONS, key="mc_blue")
    red_kind = st.selectbox("Bot Força Vermelha", BOT_OPTIONS, key="mc_red")
    stochastic = st.toggle("Modo estocástico", value=True, key="mc_sto")
    chi = st.slider("χ — admissibilidade marginal", 0.0, 1.0, 0.5, 0.05,
                    key="mc_chi")
    max_turns = st.slider("Limite operacional (dias)", 4, 24, 12, key="mc_mt")
    base_seed = st.number_input("Semente base", 0, 999_999, 0, key="mc_seed")
    fog = st.toggle("Névoa de guerra (detecção limitada)", value=False,
                    key="mc_fog")
    with st.expander("⚡ Guerra cibernética"):
        c1, c2 = st.columns(2)
        blue_cyber, red_cyber = {}, {}
        with c1:
            st.markdown("**🔵 Azul**")
            for s in ("C2", "SEN", "WPN", "LOG"):
                blue_cyber[s] = st.slider(s, 0, 5, 0, key=f"mc_bc_{s}")
        with c2:
            st.markdown("**🔴 Verm.**")
            for s in ("C2", "SEN", "WPN", "LOG"):
                red_cyber[s] = st.slider(s, 0, 5, 0, key=f"mc_rc_{s}")
    collect = st.toggle("Guardar trilhas p/ treino de ML", value=True,
                        help="Armazena os eventos das partidas para treinar "
                             "o bot de clonagem comportamental na página Bots.")
    run = st.button("▶️ Executar lote", type="primary",
                    use_container_width=True)

if run:
    prog = st.progress(0.0, text="Executando replicações...")

    def cb(done, total):
        prog.progress(done / total, text=f"Replicação {done}/{total}")

    df, trails = run_batch(
        blue_bot_factory=lambda: make_bot(blue_kind),
        red_bot_factory=lambda: make_bot(red_kind),
        n_runs=int(n_runs), oob=copy.deepcopy(get_oob()),
        max_turns=int(max_turns), stochastic=stochastic, chi=chi,
        base_seed=int(base_seed), blue_cyber=blue_cyber,
        red_cyber=red_cyber, fog_of_war=fog,
        collect_events=collect, progress=cb)
    prog.empty()
    st.session_state["mc_df"] = df
    st.session_state["mc_config"] = {
        "replicações": int(n_runs), "bot Azul": blue_kind,
        "bot Vermelho": red_kind, "estocástico": stochastic, "χ": chi,
        "limite (dias)": int(max_turns), "semente base": int(base_seed),
        "névoa": fog, "ciber Azul": blue_cyber, "ciber Vermelha": red_cyber}
    if collect:
        st.session_state["event_trails"] = trails

df = st.session_state.get("mc_df")
if df is None:
    st.info("Configure e execute um lote na barra lateral.")
    st.stop()

s = summarize(df)
st.subheader("Medidas de eficácia (MOEs)")
c = st.columns(6)
ci = s["p_blue_win_ci95"]
c[0].metric("P(vitória Azul)", f"{100 * s['p_blue_win']:.0f}%",
            help=f"IC95%: {100 * ci[0]:.0f}%–{100 * ci[1]:.0f}%")
c[1].metric("FPSOs sobrev. (média)", f"{s['mean_fpsos_surviving']:.2f}/4")
c[2].metric("Integr. portos (média)", f"{s['mean_port_integrity']:.0f}%")
c[3].metric("Perdas Azul (média)", f"{s['mean_blue_losses']:.0f}%")
c[4].metric("Perdas Verm. (média)", f"{s['mean_red_losses']:.0f}%")
c[5].metric("Duração média", f"{s['mean_turns']:.1f} dias")

tab_dist, tab_data = st.tabs(["📈 Distribuições", "🗃️ Dados e download"])

with tab_dist:
    c1, c2 = st.columns(2)
    with c1:
        fig = px.histogram(df, x="fpsos_surviving", color="winner",
                           nbins=5, barmode="group",
                           title="FPSOs sobreviventes por replicação",
                           color_discrete_map={"blue": "#1f77e0",
                                               "red": "#e04a3a"})
        st.plotly_chart(fig, use_container_width=True)
        fig = px.histogram(df, x="turns", color="winner",
                           title="Duração da campanha (dias)",
                           color_discrete_map={"blue": "#1f77e0",
                                               "red": "#e04a3a"})
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        fig = px.box(df.melt(value_vars=["blue_losses_pct", "red_losses_pct"],
                             var_name="força", value_name="perdas (%SP)")
                     .replace({"blue_losses_pct": "Azul",
                               "red_losses_pct": "Vermelha"}),
                     x="força", y="perdas (%SP)", color="força",
                     title="Perdas por força (% do SP inicial)",
                     color_discrete_map={"Azul": "#1f77e0",
                                         "Vermelha": "#e04a3a"})
        st.plotly_chart(fig, use_container_width=True)
        fig = px.scatter(df, x="blue_losses_pct", y="port_integrity_pct",
                         color="winner", size="fpsos_surviving",
                         title="Integridade portuária × perdas Azul",
                         labels={"blue_losses_pct": "Perdas Azul (%SP)",
                                 "port_integrity_pct": "Integridade portos (%)"},
                         color_discrete_map={"blue": "#1f77e0",
                                             "red": "#e04a3a"})
        st.plotly_chart(fig, use_container_width=True)

with tab_data:
    st.dataframe(df, use_container_width=True, hide_index=True, height=420)
    report = batch_report_md(s, df, config=st.session_state.get("mc_config"))
    c1, c2 = st.columns(2)
    c1.download_button("⬇️ Resultados (CSV)",
                       df.to_csv(index=False).encode("utf-8"),
                       "monte_carlo_resultados.csv", "text/csv",
                       use_container_width=True)
    c2.download_button("⬇️ Relatório (Markdown)", report.encode("utf-8"),
                       "relatorio_monte_carlo.md", "text/markdown",
                       use_container_width=True)
