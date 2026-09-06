"""Simulador Construtivo CBP — página inicial."""

import streamlit as st

from app_utils import page_setup, get_oob, map_figure

page_setup("Página Inicial")

st.markdown("""
<div class="cbp-hero">
  <h1>⚓ Simulador Construtivo · Planejamento Baseado em Capacidades</h1>
  <p><b>Cenário Operação Atlântico Sul</b> — defesa das infraestruturas
  críticas nas bacias de Campos e Santos e dos portos da região Sudeste,
  com a Força Azul (Marinha do Brasil) opondo-se a uma força expedicionária
  adversária (Força Vermelha).</p>
  <p>Simulação construtiva (bot × bot) para análise de planejamento de
  força: compare pacotes de força alternativos, execute lotes Monte Carlo
  e avalie custo-efetividade com medidas de eficácia orientadas à missão.</p>
  <span class="cbp-badge">Mecânica: wargame Operação Atlântico Sul</span>
  <span class="cbp-badge">Adjudicação: equação de salva multidomínio</span>
  <span class="cbp-badge">Bots: heurístico + aprendizado de máquina</span>
</div>
""", unsafe_allow_html=True)

col1, col2 = st.columns([3, 2], gap="large")

with col1:
    st.subheader("Teatro de operações")
    oob = get_oob()
    units = ([{**{"team": "blue"}, **{
        "id": s["id"], "name": s["name"], "category": s["category"],
        "col": s["position"]["col"], "row": s["position"]["row"],
        "hp": s["stayingPower"], "maxHp": s["stayingPower"]}}
        for s in oob["forces"]["blue"]]
        + [{**{"team": "red"}, **{
            "id": s["id"], "name": s["name"], "category": s["category"],
            "col": s["position"]["col"], "row": s["position"]["row"],
            "hp": s["stayingPower"], "maxHp": s["stayingPower"]}}
           for s in oob["forces"]["red"]])
    st.plotly_chart(map_figure(units, height=480), use_container_width=True)
    st.caption("Grade hexagonal 16×10 (odd-q) sobre a costa Sudeste. "
               "■ superfície · ▼ submarino · ▲ aéreo · ⬢ terrestre · ✚ OpEsp")

with col2:
    st.subheader("Como usar")
    st.markdown("""
    <div class="cbp-card"><h4>1 · 🗺️ Cenário</h4>
    <p>Explore o mapa, a ordem de batalha e os objetivos. Edite forças ou
    carregue uma ordem de batalha própria (JSON).</p></div>
    <div class="cbp-card"><h4>2 · 🎯 Simulação</h4>
    <p>Execute uma partida construtiva bot × bot e acompanhe turno a turno:
    movimentos, engajamentos e a adjudicação pela equação de salva.</p></div>
    <div class="cbp-card"><h4>3 · 🎲 Monte Carlo</h4>
    <p>Rode lotes de replicações com sementes controladas e analise a
    distribuição das medidas de eficácia (MOEs).</p></div>
    <div class="cbp-card"><h4>4 · 📊 Análise CBP</h4>
    <p>Compare pacotes de força alternativos: eficácia × custo, perfil de
    capacidades e ranking por MOE ponderada.</p></div>
    <div class="cbp-card"><h4>5 · 🤖 Bots</h4>
    <p>Ajuste a doutrina do bot heurístico e treine o bot de aprendizado
    de máquina por clonagem comportamental (self-play).</p></div>
    <div class="cbp-card"><h4>6 · 📄 Relatórios e Dados</h4>
    <p>Baixe relatórios (Markdown), resultados (CSV/JSON) e logs de
    partidas (JSONL); carregue dados de sessões anteriores.</p></div>
    """, unsafe_allow_html=True)

st.divider()

st.subheader("Metodologia")
m1, m2, m3 = st.columns(3, gap="large")
with m1:
    st.markdown("""
    ##### 🎲 Mecânica de jogo
    Porte fiel do wargame **Operação Atlântico Sul**: grade hexagonal com
    terrenos, turnos com períodos diurno/noturno (limite operacional de 12
    dias), movimentação simultânea, rodadas de batalha com contra-ataque em
    grupo, logística (combustível, recompletamento em portos/bases),
    **névoa de guerra opcional** (detecção por categoria, reduzida à noite)
    e vitória por objetivos assimétricos — Azul precisa de 3 de 5
    objetivos; Vermelho, de seus 2.
    """)
with m2:
    st.markdown("""
    ##### 🧮 Equação de salva multidomínio
    Os engajamentos são adjudicados pelo modelo do pacote **naval_salvo**:
    `ΔSP = (1/s)·𝟙⁽ᵈ'ᵈ⁾·[T_atq − T_def]₊`, com matriz de admissibilidade
    5×5 entre domínios (superfície, submarino, aéreo, costeiro, ciber) e
    nível marginal χ calibrável. Letalidade e interceptação calibradas nas
    tabelas do jogo original; modos estocástico e determinístico. O
    **domínio cibernético** atua pelo modulador Φ, degradando ofensiva,
    interceptação, detecção e logística do oponente.
    """)
with m3:
    st.markdown("""
    ##### 🤖 Bots
    **Heurístico**: doutrina orientada a objetivos portada do jogo (persegue
    exatamente o que pontua, protege logística, gerencia combustível).
    **ML**: clonagem comportamental — redes que pontuam os 160 hexes para
    movimento e ataque, treinadas em partidas registradas (self-play),
    como no pipeline `ml/train_bot.py` do wargame.
    """)

st.divider()
st.caption("Simulador Construtivo CBP v0.1 · Ferramenta de apoio à análise "
           "de planejamento de força. Parâmetros e custos ilustrativos — "
           "calibrar com fontes doutrinárias antes de uso em estudos reais.")
