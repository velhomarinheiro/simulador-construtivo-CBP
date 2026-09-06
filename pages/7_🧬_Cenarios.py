"""Página: extração de cenários e fatores de bifurcação (log-cluster)."""

import copy

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app_utils import get_oob, page_setup
from cbp_sim.bots import BotTuning, HeuristicBot
from cbp_sim.logcluster import (SYMBOL_LABELS, compare_scenarios,
                                dendrogram_coords, describe_feature,
                                encode_trails, run_log_cluster_analysis,
                                suggest_horizon, trail_outcomes)
from cbp_sim.montecarlo import run_batch

page_setup("Cenários")
st.title("🧬 Cenários e fatores de bifurcação")

st.markdown("""
Aplica **log-cluster analysis** (Sakata et al., JACIII 2023) às trilhas de
partidas: a história de decisões de cada campanha vira um **código-string**
— um símbolo por turno, indicando **contra que grupo de capacidade** o
esforço foi dirigido —, os códigos são agrupados por **distância de
Levenshtein** em *cenários*, e uma **árvore de decisão** revela *quando e
qual decisão* separa esses cenários.
""")

trails = st.session_state.get("event_trails", [])

with st.sidebar:
    st.header("Trilhas")
    st.metric("Partidas disponíveis", len(trails))
    st.caption("Use as trilhas do lote Monte Carlo, importe um JSONL na "
               "página Relatórios e Dados, ou gere abaixo uma varredura "
               "de doutrina.")
    st.divider()
    st.subheader("Gerar varredura de doutrina")
    st.caption("Desenho experimental do artigo: agentes com **regras "
               "distintas** jogam a mesma simulação, de modo que o espaço "
               "de cenários seja efetivamente povoado.")
    n_por_doutrina = st.slider("Partidas por doutrina", 5, 100, 30, 5)
    fog_gen = st.toggle("Névoa de guerra", value=True, key="lc_fog")
    if st.button("🎲 Gerar trilhas", use_container_width=True):
        doutrinas = {
            "Ofensiva": BotTuning(aggressiveness=1.0, defend_assets=0),
            "Escolta cerrada": BotTuning(aggressiveness=0.6, defend_assets=3),
            "Defesa da missão": BotTuning(aggressiveness=0.3, defend_assets=2),
        }
        prog = st.progress(0.0)
        novas = []
        for i, (nome, t) in enumerate(doutrinas.items()):
            _, tr = run_batch(
                blue_bot_factory=lambda t=t: HeuristicBot(t),
                red_bot_factory=HeuristicBot, n_runs=int(n_por_doutrina),
                oob=copy.deepcopy(get_oob()), collect_events=True,
                fog_of_war=fog_gen, base_seed=1000 * (i + 1),
                progress=lambda d, tot, i=i: prog.progress(
                    (i + d / tot) / len(doutrinas),
                    text=f"{nome} — {d}/{tot}"))
            for x in tr:
                x["doutrina"] = nome
            novas += tr
        prog.empty()
        st.session_state["event_trails"] = novas
        st.success(f"{len(novas)} trilhas geradas.")
        st.rerun()

if len(trails) < 2:
    st.info("São necessárias ao menos duas partidas. Gere uma varredura de "
            "doutrina na barra lateral, execute um lote na página Monte "
            "Carlo (com “Guardar trilhas”), ou importe um JSONL.")
    st.stop()

# ── Configuração da análise ──────────────────────────────────────────────────
brutos = encode_trails(trails, side="blue")
h_sug = suggest_horizon(brutos, coverage=0.8)
comprimentos = [len(c) for c in brutos]

c1, c2, c3, c4 = st.columns(4)
side = c1.selectbox("Força analisada", ["blue", "red"],
                    format_func=lambda s: "🔵 Azul" if s == "blue" else "🔴 Vermelha")
n_clusters = c2.slider("Nº de cenários", 2, 6, 3)
metodo = c3.selectbox(
    "Ligação", ["ward", "average", "complete"],
    help="O artigo usa Ward. Ward pressupõe distâncias euclidianas — sobre "
         "Levenshtein é prática comum, porém frouxa; average/complete são "
         "válidos para matrizes de distância arbitrárias.")
horizonte = c4.number_input(
    "Horizonte comum (turnos)", 1, max(comprimentos), int(h_sug),
    help="Campanhas terminam em turnos diferentes. Sem um horizonte comum, "
         "a distância de Levenshtein é dominada pela diferença de "
         "comprimento e o agrupamento captura apenas a duração — não a "
         "decisão. Sugerido: maior turno em que 80% das partidas ainda "
         "estavam em curso.")

d1, d2 = st.columns(2)
prof = d1.slider("Profundidade da árvore", 1, 5, 3)
folds = d2.slider("Dobras da validação cruzada", 2, 10, 4)

res = run_log_cluster_analysis(trails, side=side, n_clusters=int(n_clusters),
                               method=metodo, max_depth=int(prof),
                               cv_folds=int(folds), horizon=int(horizonte))
outcomes = trail_outcomes(trails)

st.caption("**Alfabeto** (grupo de capacidade mais visado no turno): "
           + " · ".join(f"`{s}` {r}" for s, r in SYMBOL_LABELS.items()))

# ── Cenários ─────────────────────────────────────────────────────────────────
st.subheader("Cenários extraídos")
tab = res.scenario_table()
st.dataframe(tab.style.format({"Proporção": "{:.1%}",
                               "Comprimento médio": "{:.1f}"}),
             use_container_width=True, hide_index=True)

e1, e2 = st.columns(2)
with e1:
    icoord, dcoord, _ = dendrogram_coords(res.Z)
    fig = go.Figure()
    for xs, ys in zip(icoord, dcoord):
        fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines",
                                 line=dict(color="#1f4e79", width=1),
                                 hoverinfo="skip", showlegend=False))
    fig.update_layout(title=f"Dendrograma ({metodo}, Levenshtein)",
                      xaxis=dict(showticklabels=False, title="partidas"),
                      yaxis_title="distância de fusão", height=380,
                      margin=dict(l=10, r=10, t=50, b=10))
    st.plotly_chart(fig, use_container_width=True)
with e2:
    cont = pd.Series(res.labels).value_counts().sort_index()
    fig = go.Figure(go.Bar(x=[f"S{i}" for i in cont.index], y=cont.values,
                           marker_color="#1f4e79",
                           text=cont.values, textposition="auto"))
    fig.update_layout(title="Partidas por cenário", height=380,
                      yaxis_title="nº de partidas",
                      margin=dict(l=10, r=10, t=50, b=10))
    st.plotly_chart(fig, use_container_width=True)

# se as trilhas vieram da varredura, mostra a composição por doutrina
if any("doutrina" in t for t in trails):
    comp = pd.crosstab(pd.Series([t.get("doutrina", "—") for t in trails],
                                 name="Doutrina"),
                       pd.Series([f"S{c}" for c in res.labels],
                                 name="Cenário"))
    with st.expander("🎛️ Composição dos cenários por doutrina do bot"):
        st.dataframe(comp, use_container_width=True)
        st.caption("Mostra em que medida os cenários emergentes recuperam as "
                   "doutrinas que geraram as partidas.")

# ── Fatores de bifurcação ────────────────────────────────────────────────────
st.subheader("Fatores de bifurcação")
raiz = res.tree.root_factor()
if raiz is None:
    st.info("A árvore não encontrou corte informativo — os cenários não são "
            "separáveis por uma decisão isolada nesta configuração.")
else:
    nome, ganho = raiz
    st.success(f"**Fator principal:** {describe_feature(nome)}  "
               f"·  ganho de informação {ganho:.3f}")

cvm = res.cv
st.markdown(f"**Validação cruzada ({cvm['k']} dobras) — acurácia "
            f"{cvm['acuracia']:.1%}**")
st.dataframe(pd.DataFrame([
    {"Cenário": f"S{c}", "Partidas": m["n"], "Precisão": m["precisao"],
     "Revocação": m["revocacao"], "F1": m["f1"]}
    for c, m in cvm["por_cenario"].items()
]).style.format({"Precisão": "{:.1%}", "Revocação": "{:.1%}", "F1": "{:.1%}"}),
    use_container_width=True, hide_index=True)


def _legivel(cond: str) -> str:
    return ("NÃO " + describe_feature(cond[4:]) if cond.startswith("NÃO ")
            else describe_feature(cond))


st.markdown("**Regras (raiz → folha)** — o caminho de decisões que leva a "
            "cada cenário:")
for reg in sorted(res.tree.rules(), key=lambda r: -r["n"]):
    st.markdown(f"- SE {' **E** '.join(_legivel(c) for c in reg['condicoes'])} "
                f"→ **S{reg['cenario']}** ({reg['n']} partidas)")

# ── Teste de hipótese entre cenários ─────────────────────────────────────────
st.subheader("Contraste entre cenários (Mann-Whitney U)")
cenarios = sorted({int(c) for c in res.labels})
m1, m2, m3 = st.columns(3)
metrica = m1.selectbox("MOE", ["turns", "fpsos_surviving",
                               "port_integrity_pct"],
                       format_func=lambda m: {
                           "turns": "Duração (dias)",
                           "fpsos_surviving": "FPSOs sobreviventes",
                           "port_integrity_pct": "Integridade portuária (%)"}[m])
ca = m2.selectbox("Cenário A", cenarios, index=0,
                  format_func=lambda c: f"S{c}")
cb = m3.selectbox("Cenário B", cenarios,
                  index=1 if len(cenarios) > 1 else 0,
                  format_func=lambda c: f"S{c}")

vals = outcomes[metrica].to_numpy(dtype=float)
ok = ~np.isnan(vals)
if ok.sum() < 2 or ca == cb:
    st.info("Selecione dois cenários distintos com dados suficientes.")
else:
    mw = compare_scenarios(vals[ok], res.labels[ok], ca, cb)
    q1, q2, q3 = st.columns(3)
    q1.metric(f"Mediana S{ca}", f"{mw['mediana_a']:.2f}", f"n={mw['n_a']}")
    q2.metric(f"Mediana S{cb}", f"{mw['mediana_b']:.2f}", f"n={mw['n_b']}")
    sig = "diferença significativa" if mw["p"] < 0.05 else "sem diferença"
    q3.metric("p-valor", f"{mw['p']:.4g}", sig)

    fig = go.Figure()
    for c, cor in ((ca, "#1f4e79"), (cb, "#b4341f")):
        fig.add_trace(go.Box(y=vals[ok][res.labels[ok] == c], name=f"S{c}",
                             marker_color=cor, boxmean=True))
    fig.update_layout(height=340, showlegend=False,
                      margin=dict(l=10, r=10, t=30, b=10))
    st.plotly_chart(fig, use_container_width=True)

# ── Exportação ───────────────────────────────────────────────────────────────
export = pd.DataFrame({
    "run": [t.get("run") for t in trails],
    "doutrina": [t.get("doutrina", "") for t in trails],
    "codigo": res.codes,
    "cenario": [f"S{c}" for c in res.labels],
}).join(outcomes.drop(columns=["run"], errors="ignore"))
st.download_button("⬇️ Códigos e cenários (CSV)",
                   export.to_csv(index=False).encode("utf-8"),
                   "cenarios_logcluster.csv", "text/csv")
