"""Página: cenário, mapa, ordem de batalha e objetivos."""

import copy
import json

import pandas as pd
import streamlit as st

from app_utils import page_setup, get_oob, map_figure
from cbp_sim.engine import load_order_of_battle, OBJECTIVE_IDS
from cbp_sim.oob_io import oob_to_csv, csv_to_oob

page_setup("Cenário")
st.title("🗺️ Cenário — Operação Atlântico Sul")

oob = get_oob()

tab_map, tab_oob, tab_obj, tab_io = st.tabs(
    ["Mapa", "Ordem de Batalha", "Objetivos", "Importar / Exportar"])

with tab_map:
    units = []
    for team in ("blue", "red"):
        for s in oob["forces"][team]:
            units.append({
                "id": s["id"], "name": s["name"], "team": team,
                "category": s["category"],
                "col": s["position"]["col"], "row": s["position"]["row"],
                "hp": s["stayingPower"], "maxHp": s["stayingPower"]})
    st.plotly_chart(map_figure(units, height=620,
                               title="Disposição inicial das forças"),
                    use_container_width=True)
    st.markdown("""
    **Terrenos** — terra (bases, portos e baterias), águas rasas (patrulha
    costeira), plataforma continental, águas profundas e campos de petróleo
    (FPSOs do pré-sal). Submarinos não operam em águas rasas; navios de
    superfície não entram em terra.
    """)

with tab_oob:
    team_sel = st.radio("Força", ["blue", "red"], horizontal=True,
                        format_func=lambda t: "🔵 Força Azul (MB)"
                        if t == "blue" else "🔴 Força Vermelha")
    rows = []
    for s in oob["forces"][team_sel]:
        wpns = ", ".join(f"{k}×{v.get('quantity', 0)}"
                         for k, v in (s.get("weapons") or {}).items())
        caps = ", ".join(f"{k}:{v}"
                         for k, v in (s.get("capabilities") or {}).items())
        comp = " + ".join(f"{c['quantity']}× {c['type']}"
                          for c in (s.get("composition") or []))
        rows.append({
            "ID": s["id"], "Nome": s["name"], "Categoria": s["category"],
            "SP": s["stayingPower"], "Mov": s.get("movement", 0),
            "Composição": comp, "Armas": wpns or "—",
            "Capacidades": caps or "—", "Notas": s.get("notes", ""),
        })
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True, height=520)
    st.caption(f"{len(rows)} grupos-tarefa · SP total "
               f"{sum(r['SP'] for r in rows)}")

    with st.expander("✏️ Editar grupo-tarefa"):
        ids = [s["id"] for s in oob["forces"][team_sel]]
        sel = st.selectbox("Grupo", ids)
        spec = next(s for s in oob["forces"][team_sel] if s["id"] == sel)
        c1, c2, c3 = st.columns(3)
        new_sp = c1.number_input("Poder de permanência (SP)", 1, 40,
                                 int(spec["stayingPower"]))
        new_mov = c2.number_input("Movimento", 0, 15,
                                  int(spec.get("movement", 0)))
        remove = c3.checkbox("Remover grupo da força")
        if st.button("Aplicar alteração", type="primary"):
            if remove:
                oob["forces"][team_sel] = [
                    s for s in oob["forces"][team_sel] if s["id"] != sel]
            else:
                spec["stayingPower"] = int(new_sp)
                spec["movement"] = int(new_mov)
            st.session_state["oob"] = oob
            st.success("Ordem de batalha atualizada para esta sessão.")
            st.rerun()

with tab_obj:
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("### 🔵 Força Azul — precisa de **3 de 5**")
        st.markdown("""
        1. **Destruir o Porta-Aviões** (CSG `RED-GBPA`)
        2. **Neutralizar ≥ 50% da logística** (2 de 3 navios: AOR, GLOG, AKE)
        3. **Neutralizar o Grupo-Tarefa Anfíbio** (`RED-GANF`)
        4. **Destruir o Submarino Nuclear** (`RED-KSN`)
        5. **Degradar ≥ 50% dos navios combatentes** vermelhos
        """)
    with c2:
        st.markdown("### 🔴 Força Vermelha — precisa de **2 de 2**")
        st.markdown("""
        1. **Neutralizar as 4 FPSOs** (campos de petróleo do pré-sal)
        2. **Degradar ≥ 50% dos portos** (Santos, Rio, Vitória e Açu)
        """)
    st.info("Limite operacional de **12 dias** (24 turnos dia/noite). "
            "Atingido o limite, adjudica-se pela maior fração de objetivos "
            "cumpridos (empate favorece o defensor).")

with tab_io:
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### ⬇️ Exportar ordem de batalha")
        e1, e2 = st.columns(2)
        e1.download_button(
            "JSON", json.dumps(oob, ensure_ascii=False, indent=2),
            file_name="ordem_de_batalha.json", mime="application/json",
            use_container_width=True)
        e2.download_button(
            "CSV (planilha)", oob_to_csv(oob),
            file_name="ordem_de_batalha.csv", mime="text/csv",
            use_container_width=True)
        st.caption("O CSV traz uma linha por grupo-tarefa — editável em "
                   "Excel/LibreOffice. Campos aninhados (armas, "
                   "capacidades, alcances) usam a convenção "
                   "`tipo:qtd[:alcance]` separada por `;`.")
        if st.button("Restaurar OOB padrão", use_container_width=True):
            st.session_state["oob"] = load_order_of_battle()
            st.success("Ordem de batalha padrão restaurada.")
            st.rerun()
    with c2:
        st.markdown("#### ⬆️ Importar ordem de batalha")
        up = st.file_uploader(
            "Arquivo JSON (formato do wargame OAS, chave "
            "`forces.blue`/`forces.red`) ou CSV (uma linha por grupo).",
            type=["json", "csv"])
        if up is not None:
            try:
                if up.name.lower().endswith(".csv"):
                    data = csv_to_oob(up.getvalue())
                else:
                    data = json.load(up)
                    assert "forces" in data and "blue" in data["forces"] \
                        and "red" in data["forces"], \
                        "JSON sem a estrutura forces.blue / forces.red"
                st.session_state["oob"] = data
                st.success(f"OOB carregada: "
                           f"{len(data['forces']['blue'])} grupos azuis, "
                           f"{len(data['forces']['red'])} vermelhos.")
            except Exception as e:  # noqa: BLE001
                st.error(f"Arquivo inválido: {e}")
