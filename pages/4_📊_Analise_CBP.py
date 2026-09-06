"""Página: análise de alternativas — Planejamento Baseado em Capacidades."""

import copy
import json

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app_utils import BOT_OPTIONS, get_oob, make_bot, page_setup
from cbp_sim.cbp import (CYBER_DOMAIN_LABEL, FORCE_TAXONOMY, PRESET_PACKAGES,
                         THREAT_PACKAGES, UNIT_COSTS, ForcePackage,
                         apply_package, capability_profile, classify_unit,
                         group_labels, package_composition, package_cost,
                         preset_overview, taxonomy_order)
from cbp_sim.dea import (DEA_INPUTS, DEA_OUTPUTS, build_matrices,
                         discrimination_note, run_dea)
from cbp_sim.montecarlo import run_batch, summarize, summarize_groups
from cbp_sim.reporting import comparison_report_md

page_setup("Análise CBP")
st.title("📊 Análise CBP — comparação de pacotes de força")

st.markdown("""
No **Planejamento Baseado em Capacidades**, alternativas de força são
avaliadas pela capacidade de cumprir a missão — aqui, **proteger as
infraestruturas críticas das bacias de Campos e Santos** — sob custo
conhecido. Selecione pacotes de força, rode as replicações e compare
eficácia, custo e perfil de capacidades.
""")

with st.sidebar:
    st.header("Configuração da análise")
    pkg_names = [p.name for p in PRESET_PACKAGES]
    selected = st.multiselect("Pacotes de força (Força Azul)", pkg_names,
                              default=pkg_names[:4])
    threat_names = [p.name for p in THREAT_PACKAGES]
    threat_sel = st.selectbox(
        "Pacote de ameaça (Força Vermelha)", threat_names,
        help="Variante da força adversária contra a qual as alternativas "
             "azuis serão avaliadas.")
    n_runs = st.slider("Replicações por pacote", 5, 200, 30, 5)
    red_kind = st.selectbox("Bot Força Vermelha", BOT_OPTIONS, key="cbp_red")
    blue_kind = st.selectbox("Bot Força Azul", BOT_OPTIONS, key="cbp_blue")
    stochastic = st.toggle("Modo estocástico", value=True, key="cbp_sto")
    fog = st.toggle("Névoa de guerra", value=False, key="cbp_fog")
    chi = st.slider("χ — admissibilidade", 0.0, 1.0, 0.5, 0.05, key="cbp_chi")
    seed = st.number_input("Semente base", 0, 999_999, 0, key="cbp_seed")
    st.divider()
    st.subheader("Pesos da eficácia composta")
    w_fpso = st.slider("Sobrevivência das FPSOs", 0.0, 1.0, 0.35, 0.05)
    w_port = st.slider("Integridade dos portos", 0.0, 1.0, 0.25, 0.05)
    w_win = st.slider("P(vitória Azul)", 0.0, 1.0, 0.25, 0.05)
    w_loss = st.slider("Preservação da força", 0.0, 1.0, 0.15, 0.05)
    run = st.button("▶️ Executar análise", type="primary",
                    use_container_width=True)

with st.expander("🧭 Composição dos pacotes de força", expanded=False):
    st.caption(
        "Meios organizados por **domínio** (naval-superfície, naval-submarino, "
        "aéreo, terrestre e cibernético) e por **grupo de capacidades**. Para "
        "os meios navais, a referência é a estrutura de classificação em três "
        "camadas (Artigo 1) — Camada 2, componentes de força de Coutau-Bégarie: "
        "**DISS** dissuasão · **INTERV** intervenção · **VIG** vigilância · "
        "**COST** costeira · **ANF** anfíbia · **LOG** logística. No cenário, "
        "o grupo aeronaval do NAM Atlântico (SAG-P) e a escolta do CSG "
        "vermelho (ESCCSG) são computados na componente de Intervenção.")
    tab_ov, tab_det, tab_threat = st.tabs(
        ["Visão geral (todos os pacotes)", "Detalhe por pacote",
         "Pacotes de ameaça (Vermelha)"])
    base_oob = get_oob()
    _cost_table = st.session_state.get("cost_table")

    with tab_ov:
        ov = preset_overview(base_oob, PRESET_PACKAGES, _cost_table)
        st.dataframe(ov, use_container_width=True, hide_index=True,
                     height=500)
        st.caption("“—” = grupo inalterado em relação à ordem de batalha de "
                   "referência. ✖ removido · ▲ reforçado · ⚡ estoque "
                   "cibernético do pacote. Última linha: custo total (UC).")

    with tab_det:
        det_sel = st.selectbox("Pacote", [p.name for p in PRESET_PACKAGES],
                               key="comp_det_sel")
        pkg_det = next(p for p in PRESET_PACKAGES if p.name == det_sel)
        desc = (pkg_det.description
                or "Ordem de batalha de referência, sem modificações.")
        st.markdown(f"**{pkg_det.name}** — {desc}")
        st.metric("Custo do pacote",
                  f"{package_cost(base_oob, pkg_det, _cost_table):.1f} UC")
        comp = package_composition(base_oob, pkg_det)
        st.dataframe(comp, use_container_width=True, hide_index=True,
                     height=480)

    with tab_threat:
        thr_sel = st.selectbox("Pacote de ameaça",
                               [p.name for p in THREAT_PACKAGES],
                               key="comp_thr_sel")
        thr_det = next(p for p in THREAT_PACKAGES if p.name == thr_sel)
        st.markdown(f"**{thr_det.name}** — {thr_det.description}")
        comp_r = package_composition(base_oob, thr_det)
        st.dataframe(comp_r, use_container_width=True, hide_index=True,
                     height=420)

with st.expander("💰 Tabela de custos (calibrável)"):
    st.caption("Custos ilustrativos por grupo-tarefa, em unidades de custo "
               "(UC ≈ R$ bi, ciclo de vida ~10 anos). Edite para calibrar "
               "com fontes orçamentárias; a tabela vale para toda a sessão.")
    cost_table = st.session_state.get("cost_table", dict(UNIT_COSTS))
    base_oob = get_oob()
    names = {s["id"]: s["name"] for s in base_oob["forces"]["blue"]}
    order = taxonomy_order("blue")
    cost_rows = []
    for k, v in sorted(cost_table.items(),
                       key=lambda kv: order.get(kv[0], 999)):
        dom, sigla, _label = classify_unit(k)
        cost_rows.append({"Domínio": dom, "Capac.": sigla, "ID": k,
                          "Grupo-tarefa": names.get(k, k), "Custo (UC)": v})
    cost_df = pd.DataFrame(cost_rows)
    edited = st.data_editor(
        cost_df, hide_index=True, use_container_width=True, height=340,
        disabled=["Domínio", "Capac.", "ID", "Grupo-tarefa"],
        key="cost_editor")
    c1, c2, c3 = st.columns(3)
    if c1.button("Salvar custos na sessão", use_container_width=True):
        st.session_state["cost_table"] = dict(
            zip(edited["ID"], edited["Custo (UC)"].astype(float)))
        st.success("Tabela de custos atualizada.")
    c2.download_button(
        "⬇️ Baixar tabela (JSON)",
        json.dumps(st.session_state.get("cost_table", dict(UNIT_COSTS)),
                   ensure_ascii=False, indent=2),
        "tabela_de_custos.json", "application/json",
        use_container_width=True)
    up_cost = c3.file_uploader("⬆️ Carregar tabela", type=["json"],
                               key="up_cost", label_visibility="collapsed")
    if up_cost is not None:
        try:
            data = json.load(up_cost)
            st.session_state["cost_table"] = {str(k): float(v)
                                              for k, v in data.items()}
            st.success("Tabela de custos carregada.")
        except Exception as e:  # noqa: BLE001
            st.error(f"Arquivo inválido: {e}")

with st.expander("➕ Pacote personalizado"):
    st.caption("Monte um pacote de força escalando os grupos-tarefa por "
               "**domínio** e **grupo de capacidade** (0 = remover, 1 = "
               "manter, 1.5 = reforçar, 2 = dobrar) e definindo o estoque "
               "cibernético. O custo é recalculado automaticamente.")
    base_oob = get_oob()
    specs = {s["id"]: s for s in base_oob["forces"]["blue"]}
    custom_name = st.text_input("Nome do pacote", "Personalizado 1")
    mods = {}
    for dom in FORCE_TAXONOMY["blue"]:
        dom_units = [u for g in dom["groups"] for u in g["units"]
                     if u in specs and u in UNIT_COSTS]
        if not dom_units:
            continue
        st.markdown(f"##### {dom['domain']}")
        for grp in dom["groups"]:
            units = [u for u in grp["units"]
                     if u in specs and u in UNIT_COSTS]
            if not units:
                continue
            st.markdown(f"**{grp['sigla']}** · {grp['label']}")
            gcols = st.columns(max(2, min(4, len(units))))
            for i, uid in enumerate(units):
                spec = specs[uid]
                comp = " + ".join(
                    f"{c['quantity']}× {c['type'].replace('_', ' ')}"
                    for c in (spec.get("composition") or []))
                with gcols[i % len(gcols)]:
                    mods[uid] = st.slider(
                        spec["name"], 0.0, 2.0, 1.0, 0.5,
                        key=f"mod_{uid}",
                        help=f"{comp or '—'} · SP {spec['stayingPower']} · "
                             f"custo base {UNIT_COSTS.get(uid, 0):.1f} UC")
    st.markdown(f"##### {CYBER_DOMAIN_LABEL}")
    st.markdown("**CIB** · Guerra cibernética — estoques por subtipo "
                "(C2 comando · SEN sensores · WPN armas · LOG logística)")
    ccols = st.columns(4)
    custom_cyber = {}
    for i, s in enumerate(("C2", "SEN", "WPN", "LOG")):
        custom_cyber[s] = ccols[i].slider(s, 0, 5, 0, key=f"cyb_{s}")

    preview = ForcePackage(
        name=custom_name, description="Pacote definido pelo usuário.",
        modifications={k: v for k, v in mods.items() if v != 1.0},
        cyber={k: v for k, v in custom_cyber.items() if v > 0})
    st.metric("Custo estimado do pacote",
              f"{package_cost(base_oob, preview, st.session_state.get('cost_table')):.1f} UC")
    if st.button("Adicionar pacote personalizado à análise"):
        st.session_state.setdefault("custom_packages", []).append(preview)
        st.success(f"Pacote “{custom_name}” adicionado.")

all_packages = {p.name: p for p in PRESET_PACKAGES}
for p in st.session_state.get("custom_packages", []):
    all_packages[p.name] = p
extra = [p.name for p in st.session_state.get("custom_packages", [])]

if run:
    to_run = [all_packages[n] for n in list(selected) + extra
              if n in all_packages]
    if not to_run:
        st.warning("Selecione ao menos um pacote.")
        st.stop()
    base_oob = get_oob()
    threat = next(p for p in THREAT_PACKAGES if p.name == threat_sel)
    cost_table = st.session_state.get("cost_table")
    results = []
    prog = st.progress(0.0)
    for j, pkg in enumerate(to_run):
        oob_mod = apply_package(apply_package(base_oob, threat), pkg)
        df, _ = run_batch(
            blue_bot_factory=lambda: make_bot(blue_kind),
            red_bot_factory=lambda: make_bot(red_kind),
            n_runs=int(n_runs), oob=copy.deepcopy(oob_mod),
            stochastic=stochastic, chi=chi, base_seed=int(seed),
            blue_cyber=pkg.cyber, red_cyber=threat.cyber, fog_of_war=fog,
            progress=lambda d, t: prog.progress(
                (j + d / t) / len(to_run),
                text=f"{pkg.name} — replicação {d}/{t}"))
        results.append({
            "package": pkg.name, "description": pkg.description,
            "cost": package_cost(base_oob, pkg, cost_table),
            "summary": summarize(df), "df": df,
            "profile": capability_profile(oob_mod, "blue", pkg.cyber),
            "group_losses": summarize_groups(df),
        })
    prog.empty()
    st.session_state["cbp_results"] = results
    st.session_state["cbp_threat"] = threat_sel

results = st.session_state.get("cbp_results")
if not results:
    st.info("Selecione os pacotes e execute a análise na barra lateral.")
    st.stop()


def composite(s: dict) -> float:
    total_w = (w_fpso + w_port + w_win + w_loss) or 1.0
    return (w_fpso * s["mean_fpsos_surviving"] / 4.0
            + w_port * s["mean_port_integrity"] / 100.0
            + w_win * s["p_blue_win"]
            + w_loss * (1.0 - s["mean_blue_losses"] / 100.0)) / total_w


rows = []
for r in results:
    s = r["summary"]
    rows.append({
        "Pacote": r["package"], "Custo (UC)": r["cost"],
        "Eficácia composta": composite(s),
        "P(vitória)": s["p_blue_win"],
        "FPSOs sobrev.": s["mean_fpsos_surviving"],
        "Integr. portos (%)": s["mean_port_integrity"],
        "Perdas Azul (%)": s["mean_blue_losses"],
        "Razão de troca": s["mean_exchange_ratio"],
    })
tbl = pd.DataFrame(rows).sort_values("Eficácia composta", ascending=False)

st.subheader("Ranking das alternativas")
if st.session_state.get("cbp_threat"):
    st.caption(f"Avaliado contra: **{st.session_state['cbp_threat']}**")
st.dataframe(
    tbl.style.format({
        "Custo (UC)": "{:.1f}", "Eficácia composta": "{:.3f}",
        "P(vitória)": "{:.0%}", "FPSOs sobrev.": "{:.2f}",
        "Integr. portos (%)": "{:.0f}", "Perdas Azul (%)": "{:.0f}",
        "Razão de troca": "{:.2f}"})
    .highlight_max(subset=["Eficácia composta"], color="#c8ddf5"),
    use_container_width=True, hide_index=True)

c1, c2 = st.columns(2)
with c1:
    st.subheader("Custo × eficácia")
    fig = go.Figure()
    for r in results:
        fig.add_trace(go.Scatter(
            x=[r["cost"]], y=[composite(r["summary"])],
            mode="markers+text", text=[r["package"]],
            textposition="top center", name=r["package"],
            marker=dict(size=14)))
    fig.update_layout(
        xaxis_title="Custo do pacote (UC ilustrativas)",
        yaxis_title="Eficácia composta (0–1)",
        showlegend=False, height=460)
    st.plotly_chart(fig, use_container_width=True)
    st.caption("A fronteira eficiente é o conjunto de pacotes não dominados "
               "(mais acima e mais à esquerda).")

with c2:
    st.subheader("Perfil de capacidades")
    areas = list(results[0]["profile"].keys())
    base_prof = results[0]["profile"]
    fig = go.Figure()
    for r in results:
        vals = [r["profile"][a] / (base_prof[a] or 1.0) for a in areas]
        fig.add_trace(go.Scatterpolar(
            r=vals + vals[:1], theta=areas + areas[:1],
            name=r["package"], fill="toself", opacity=0.55))
    fig.update_layout(height=460,
                      polar=dict(radialaxis=dict(showticklabels=False)),
                      legend=dict(orientation="h", y=-0.15))
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Valores relativos ao primeiro pacote da análise.")

# ── Fronteira DEA ────────────────────────────────────────────────────────────
st.subheader("Fronteira de eficiência (DEA)")
st.markdown(
    "A **Análise Envoltória de Dados** dispensa os pesos fixos da eficácia "
    "composta: cada pacote é avaliado sob os pesos que lhe são **mais "
    "favoráveis**, obtidos por programação linear. Produz a *fronteira* de "
    "pacotes não dominados, o escore θ ∈ (0, 1] de cada um e — o resultado "
    "prescritivo — o **reference set**: quais pacotes eficientes um pacote "
    "ineficiente deveria imitar, e em que proporção.")

dc1, dc2, dc3 = st.columns([2, 2, 1])
dea_inputs = dc1.multiselect(
    "Insumos (menos é melhor)", list(DEA_INPUTS),
    default=["Custo (UC)", "Perdas Azul (%SP)"], key="dea_in")
dea_outputs = dc2.multiselect(
    "Produtos / MOEs (mais é melhor)", list(DEA_OUTPUTS),
    default=["FPSOs sobreviventes", "Integridade portuária (%)",
             "P(vitória Azul)"], key="dea_out")
dea_model = dc3.radio(
    "Modelo", ["BCC", "CCR"], key="dea_model",
    help="CCR: retornos constantes de escala. BCC: retornos variáveis — "
         "em geral mais defensável para pacotes de força, pois dobrar o "
         "orçamento raramente dobra a capacidade operativa.")

if not dea_inputs or not dea_outputs:
    st.warning("Selecione ao menos um insumo e um produto.")
elif len(results) < 2:
    st.info("A DEA exige ao menos dois pacotes na análise.")
else:
    nota = discrimination_note(len(results), len(dea_inputs), len(dea_outputs))
    if nota:
        st.warning(f"⚠️ {nota}")
    names_d, Xd, Yd = build_matrices(results, dea_inputs, dea_outputs)
    dea = run_dea(names_d, Xd, Yd, dea_inputs, dea_outputs, model=dea_model)

    def _peers_str(i):
        p = {k: v for k, v in dea.peers[i].items() if k != names_d[i]}
        if dea.is_efficient[i]:
            return "— (é referência)"
        return " · ".join(f"{k} (λ={v:.2f})" for k, v in
                          sorted(p.items(), key=lambda kv: -kv[1])) or "—"

    dea_rows = []
    for i, nome in enumerate(names_d):
        alvo = dea.targets(i)
        dea_rows.append({
            "Pacote": nome,
            "θ (eficiência)": dea.efficiency[i],
            "Situação": "✅ eficiente" if dea.is_efficient[i] else "ineficiente",
            "Folga radial": 1.0 - dea.efficiency[i],
            "Referências a imitar (peers)": _peers_str(i),
            **{f"Alvo: {k}": v for k, v in alvo.items()},
        })
    dea_tbl = pd.DataFrame(dea_rows).sort_values("θ (eficiência)",
                                                 ascending=False)
    fmt = {"θ (eficiência)": "{:.3f}", "Folga radial": "{:.0%}"}
    fmt.update({c: "{:.1f}" for c in dea_tbl.columns if c.startswith("Alvo:")})
    st.dataframe(dea_tbl.style.format(fmt), use_container_width=True,
                 hide_index=True)
    st.caption(
        "**θ** = 1 → pacote na fronteira. **Folga radial** = redução "
        "proporcional de insumos que o pacote precisaria alcançar para "
        "ficar eficiente, mantendo os mesmos produtos. **Alvo** = nível de "
        "insumo correspondente (θ·x).")

    d1, d2 = st.columns(2)
    with d1:
        ordem = dea_tbl.sort_values("θ (eficiência)")
        fig = go.Figure(go.Bar(
            x=ordem["θ (eficiência)"], y=ordem["Pacote"], orientation="h",
            marker_color=["#2e7d4f" if s.startswith("✅") else "#1f4e79"
                          for s in ordem["Situação"]],
            text=[f"{v:.3f}" for v in ordem["θ (eficiência)"]],
            textposition="auto"))
        fig.add_vline(x=1.0, line_dash="dash", line_color="#2e7d4f")
        fig.update_layout(title=f"Escore de eficiência θ — modelo {dea_model}",
                          xaxis_title="θ", height=420,
                          xaxis=dict(range=[0, 1.08]),
                          margin=dict(l=10, r=10, t=50, b=10))
        st.plotly_chart(fig, use_container_width=True)
    with d2:
        eixo_x = dea_inputs[0]
        eixo_y = dea_outputs[0]
        fig = go.Figure()
        for i, nome in enumerate(names_d):
            efic = dea.is_efficient[i]
            fig.add_trace(go.Scatter(
                x=[Xd[i, 0]], y=[Yd[i, 0]], mode="markers+text",
                text=[nome], textposition="top center",
                marker=dict(size=17 if efic else 12,
                            color="#2e7d4f" if efic else "#1f4e79",
                            symbol="star" if efic else "circle",
                            line=dict(width=1.5, color="white")),
                name=nome, showlegend=False,
                hovertemplate=f"<b>{nome}</b><br>θ={dea.efficiency[i]:.3f}"
                              "<extra></extra>"))
        fig.update_layout(title="Pacotes no plano insumo × produto",
                          xaxis_title=eixo_x, yaxis_title=eixo_y, height=420,
                          margin=dict(l=10, r=10, t=50, b=10))
        st.plotly_chart(fig, use_container_width=True)
        st.caption("★ = pacote na fronteira. Projeção 2-D do primeiro insumo "
                   "e do primeiro produto selecionados; θ considera todas as "
                   "dimensões.")

    with st.expander("🔎 Pesos ótimos e grupos por reference set"):
        st.markdown("**Pesos ótimos por pacote** — sob que critério cada um "
                    "obtém sua melhor avaliação. Peso nulo indica dimensão "
                    "que o pacote *não* consegue usar a seu favor.")
        w_rows = []
        for i, nome in enumerate(names_d):
            row = {"Pacote": nome}
            row.update({f"v · {k}": dea.input_weights[i, j]
                        for j, k in enumerate(dea_inputs)})
            row.update({f"u · {k}": dea.output_weights[i, j]
                        for j, k in enumerate(dea_outputs)})
            w_rows.append(row)
        st.dataframe(pd.DataFrame(w_rows), use_container_width=True,
                     hide_index=True)

        st.markdown("**Grupos por reference set compartilhado** — pacotes que "
                    "referenciam os mesmos peers são avaliados sob critério "
                    "semelhante (Sakata et al., 2021).")
        for sig, membros in dea.reference_groups().items():
            ref = " + ".join(sig) if sig else "—"
            st.markdown(f"- **Referência {ref}** → {', '.join(membros)}")

    st.session_state["cbp_dea"] = {
        "model": dea_model, "inputs": dea_inputs, "outputs": dea_outputs,
        "names": names_d, "efficiency": dea.efficiency.tolist(),
        "peers": dea.peers, "note": nota,
    }

# ── Perdas por grupo de capacidade (Camada 2) ────────────────────────────────
if any(r.get("group_losses") for r in results):
    st.subheader("Perdas por grupo de capacidade")
    st.caption("Perdas médias de SP por componente de força (Camada 2 — "
               "Coutau-Bégarie). À esquerda, o desgaste da força projetada; "
               "à direita, o atrito imposto aos componentes da ameaça. "
               "Células vazias = grupo ausente do pacote.")
    pkg_names_r = [r["package"] for r in results]
    hm1, hm2 = st.columns(2)
    for col, side, title, scale in (
            (hm1, "blue", "🔵 Força Azul — perdas próprias (%SP)", "Reds"),
            (hm2, "red", "🔴 Força Vermelha — atrito imposto (%SP)", "Teal")):
        labels = group_labels(side)
        present = [(sig, lab) for sig, lab in labels
                   if any(f"grp_{side}_{sig}" in (r.get("group_losses") or {})
                          for r in results)]
        if not present:
            continue
        z = [[(r.get("group_losses") or {}).get(f"grp_{side}_{sig}")
              for r in results] for sig, _ in present]
        hover = [[f"{lab}<br>{r['package']}" for r in results]
                 for _, lab in present]
        with col:
            fig = go.Figure(go.Heatmap(
                z=z, x=pkg_names_r, y=[sig for sig, _ in present],
                colorscale=scale, zmin=0, zmax=100,
                text=hover, hovertemplate="%{text}<br>perda média: "
                                          "%{z:.0f}%<extra></extra>",
                texttemplate="%{z:.0f}", textfont=dict(size=10),
                colorbar=dict(title="%SP")))
            fig.update_layout(title=title, height=420,
                              yaxis=dict(autorange="reversed"),
                              margin=dict(l=10, r=10, t=50, b=10))
            st.plotly_chart(fig, use_container_width=True)
    st.caption("Siglas: DISS dissuasão · INTERV intervenção · VIG vigilância "
               "· COST costeira · ANF anfíbia · LOG logística · DAE defesa "
               "aérea · PATMAR patrulha/ISR · ATQ ataque · DCOST defesa "
               "costeira · GBAD antiaérea · OPESP op. especiais · INFRA "
               "ativos protegidos.")

report = comparison_report_md(
    [{k: r[k] for k in ("package", "description", "cost", "summary")}
     | {"group_losses": r.get("group_losses")}
     for r in results],
    threat=st.session_state.get("cbp_threat"),
    dea=st.session_state.get("cbp_dea"))
detail = pd.concat([r["df"].assign(pacote=r["package"]) for r in results])
c1, c2 = st.columns(2)
c1.download_button("⬇️ Relatório comparativo (Markdown)",
                   report.encode("utf-8"), "analise_cbp.md",
                   "text/markdown", use_container_width=True)
c2.download_button("⬇️ Replicações detalhadas (CSV)",
                   detail.to_csv(index=False).encode("utf-8"),
                   "analise_cbp_replicacoes.csv", "text/csv",
                   use_container_width=True)
