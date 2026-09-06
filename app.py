"""
Simulador Construtivo CBP — ponto de entrada e roteador de navegação.

Usa a API ``st.navigation`` para rotular explicitamente cada página (em
especial a inicial, que no modo de descoberta automática herdaria o nome
do arquivo de entrada). O conteúdo de cada página vive em seu próprio
arquivo; aqui apenas montamos a navegação.
"""

import streamlit as st

from app_utils import PAGE_ICON

st.set_page_config(
    page_title="Simulador Construtivo CBP",
    page_icon=PAGE_ICON,
    layout="wide",
    initial_sidebar_state="expanded",
)

pages = [
    st.Page("home.py", title="Página Inicial", icon="⚓", default=True),
    st.Page("pages/1_🗺️_Cenario.py", title="Cenário", icon="🗺️"),
    st.Page("pages/2_🎯_Simulacao.py", title="Simulação", icon="🎯"),
    st.Page("pages/3_🎲_Monte_Carlo.py", title="Monte Carlo", icon="🎲"),
    st.Page("pages/4_📊_Analise_CBP.py", title="Análise CBP", icon="📊"),
    st.Page("pages/5_🤖_Bots.py", title="Bots", icon="🤖"),
    st.Page("pages/7_🧬_Cenarios.py", title="Cenários", icon="🧬"),
    st.Page("pages/6_📄_Relatorios_e_Dados.py",
            title="Relatórios e Dados", icon="📄"),
]

st.navigation(pages).run()
