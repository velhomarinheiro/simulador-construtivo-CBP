"""Página: relatórios consolidados, downloads e uploads de dados."""

import json

import pandas as pd
import streamlit as st

from app_utils import get_oob, page_setup
from cbp_sim.montecarlo import summarize
from cbp_sim.reporting import batch_report_md, comparison_report_md

page_setup("Relatórios e Dados")
st.title("📄 Relatórios e Dados")

st.markdown("Central de importação/exportação da sessão: relatórios em "
            "Markdown, resultados em CSV/JSON e trilhas de partidas em "
            "JSONL (compatíveis com o pipeline de ML).")

tab_rep, tab_data, tab_up = st.tabs(
    ["📑 Relatórios", "🗃️ Dados da sessão", "⬆️ Importar"])

with tab_rep:
    any_report = False

    mc_df = st.session_state.get("mc_df")
    if mc_df is not None:
        any_report = True
        st.markdown("#### Lote Monte Carlo")
        report = batch_report_md(summarize(mc_df), mc_df,
                                 config=st.session_state.get("mc_config"))
        with st.expander("Pré-visualizar relatório Monte Carlo"):
            st.markdown(report)
        st.download_button("⬇️ Relatório Monte Carlo (Markdown)",
                           report.encode("utf-8"),
                           "relatorio_monte_carlo.md", "text/markdown")

    cbp_results = st.session_state.get("cbp_results")
    if cbp_results:
        any_report = True
        st.markdown("#### Análise de alternativas (CBP)")
        report = comparison_report_md(
            [{k: r[k] for k in ("package", "description", "cost", "summary")}
             for r in cbp_results],
            threat=st.session_state.get("cbp_threat"))
        with st.expander("Pré-visualizar relatório CBP"):
            st.markdown(report)
        st.download_button("⬇️ Relatório CBP (Markdown)",
                           report.encode("utf-8"), "analise_cbp.md",
                           "text/markdown")

    game = st.session_state.get("single_game")
    if game:
        any_report = True
        st.markdown("#### Partida única")
        m = game["metrics"]
        resumo = "\n".join([
            "# Relatório de Partida — Simulação Construtiva CBP", "",
            f"- **Vencedor**: {'Força Azul' if game['winner'] == 'blue' else 'Força Vermelha'}",
            f"- **Encerramento**: {m['end_reason']} no dia {m['turns']}",
            f"- **FPSOs sobreviventes**: {m['fpsos_surviving']}/4",
            f"- **Integridade dos portos**: {m['port_integrity_pct']:.0f}%",
            f"- **Perdas (SP)**: Azul {m['blue_losses_pct']:.0f}% · "
            f"Vermelha {m['red_losses_pct']:.0f}%",
            f"- **Configuração**: {game['config']}", "",
            "## Log da partida", "", "```",
            *game["state_log"], "```",
        ])
        st.download_button("⬇️ Relatório da partida (Markdown)",
                           resumo.encode("utf-8"), "relatorio_partida.md",
                           "text/markdown")

    if not any_report:
        st.info("Nenhum resultado na sessão ainda — execute uma Simulação, "
                "um lote Monte Carlo ou uma Análise CBP.")

with tab_data:
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### Resultados")
        if mc_df is not None:
            st.download_button("⬇️ Monte Carlo (CSV)",
                               mc_df.to_csv(index=False).encode("utf-8"),
                               "monte_carlo_resultados.csv", "text/csv",
                               use_container_width=True)
        if cbp_results:
            detail = pd.concat([r["df"].assign(pacote=r["package"])
                                for r in cbp_results])
            st.download_button("⬇️ Análise CBP (CSV)",
                               detail.to_csv(index=False).encode("utf-8"),
                               "analise_cbp_replicacoes.csv", "text/csv",
                               use_container_width=True)
        st.download_button(
            "⬇️ Ordem de batalha ativa (JSON)",
            json.dumps(get_oob(), ensure_ascii=False, indent=2),
            "ordem_de_batalha.json", "application/json",
            use_container_width=True)
    with c2:
        st.markdown("#### Trilhas de partidas (dataset de ML)")
        trails = st.session_state.get("event_trails", [])
        st.metric("Partidas registradas", len(trails))
        if trails:
            jsonl = "\n".join(
                json.dumps({"run": t["run"], "winner": t["winner"],
                            **ev}, ensure_ascii=False, default=str)
                for t in trails for ev in t["events"])
            st.download_button("⬇️ Trilhas de eventos (JSONL)",
                               jsonl.encode("utf-8"), "game_logs.jsonl",
                               "application/jsonl",
                               use_container_width=True)
        game = st.session_state.get("single_game")
        if game:
            jsonl_1 = "\n".join(json.dumps(ev, ensure_ascii=False,
                                           default=str)
                                for ev in game["events"])
            st.download_button("⬇️ Eventos da partida única (JSONL)",
                               jsonl_1.encode("utf-8"),
                               "partida_unica.jsonl", "application/jsonl",
                               use_container_width=True)

with tab_up:
    st.markdown("#### Importar resultados Monte Carlo (CSV)")
    up_csv = st.file_uploader("CSV exportado deste app", type=["csv"])
    if up_csv is not None:
        try:
            df = pd.read_csv(up_csv)
            required = {"winner", "blue_win", "turns", "fpsos_surviving"}
            assert required.issubset(df.columns), \
                f"Colunas obrigatórias ausentes: {required - set(df.columns)}"
            st.session_state["mc_df"] = df
            st.success(f"{len(df)} replicações carregadas — disponíveis nas "
                       "páginas Monte Carlo e Relatórios.")
        except Exception as e:  # noqa: BLE001
            st.error(f"Arquivo inválido: {e}")

    st.markdown("#### Importar trilhas de eventos (JSONL)")
    up_jsonl = st.file_uploader("JSONL exportado deste app", type=["jsonl"])
    if up_jsonl is not None:
        try:
            events_by_run: dict = {}
            for line in up_jsonl.read().decode("utf-8").splitlines():
                if not line.strip():
                    continue
                ev = json.loads(line)
                run = ev.pop("run", 0)
                winner = ev.pop("winner", None)
                events_by_run.setdefault(run, {"run": run, "winner": winner,
                                               "events": []})
                events_by_run[run]["events"].append(ev)
            trails = list(events_by_run.values())
            st.session_state["event_trails"] = trails
            st.success(f"{len(trails)} partidas carregadas — disponíveis "
                       "para treino do bot ML na página Bots.")
        except Exception as e:  # noqa: BLE001
            st.error(f"Arquivo inválido: {e}")
