"""Utilitários compartilhados da interface Streamlit."""

from __future__ import annotations

import math

import plotly.graph_objects as go
import streamlit as st

from cbp_sim import hexmap as hx

# ── Identidade visual ─────────────────────────────────────────────────────────

TERRAIN_COLORS = {
    hx.T_LAND: "#8a9a5b",
    hx.T_SHALLOW: "#9fd8e8",
    hx.T_SHELF: "#5fb4d4",
    hx.T_DEEP: "#1d5f8a",
    hx.T_OIL: "#3e7ca6",
}
BLUE_COLOR = "#1f77e0"
RED_COLOR = "#e04a3a"

CATEGORY_SYMBOLS = {
    "surface": "■", "submarine": "▼", "air": "▲", "land": "⬢", "specops": "✚",
}

PAGE_ICON = "⚓"


def page_setup(title: str, *, wide: bool = True):
    st.set_page_config(
        page_title=f"{title} · Simulador Construtivo CBP",
        page_icon=PAGE_ICON,
        layout="wide" if wide else "centered",
        initial_sidebar_state="expanded",
    )
    inject_css()


def inject_css():
    st.markdown("""
    <style>
      .stApp { font-family: "Source Sans Pro", "Segoe UI", sans-serif; }
      h1, h2, h3 { letter-spacing: -0.02em; }
      div[data-testid="stMetric"] {
        background: linear-gradient(160deg, rgba(31,119,224,.08), rgba(31,119,224,.02));
        border: 1px solid rgba(31,119,224,.25);
        border-radius: 12px;
        padding: 12px 16px;
      }
      div[data-testid="stMetric"] label { opacity: .8; }
      .cbp-card {
        border: 1px solid rgba(128,128,128,.25);
        border-radius: 14px;
        padding: 1rem 1.2rem;
        margin-bottom: .8rem;
        background: rgba(128,128,128,.05);
      }
      .cbp-card h4 { margin: 0 0 .35rem 0; }
      .cbp-card p { margin: 0; opacity: .85; font-size: .92rem; }
      .cbp-hero {
        background: linear-gradient(135deg, #0b2d52 0%, #14518f 55%, #1f77e0 100%);
        color: #fff;
        border-radius: 18px;
        padding: 2rem 2.2rem;
        margin-bottom: 1.2rem;
      }
      .cbp-hero h1 { color: #fff; margin: 0 0 .4rem 0; }
      .cbp-hero p { color: #dbe9fb; max-width: 62rem; margin: .2rem 0; }
      .cbp-badge {
        display: inline-block;
        background: rgba(255,255,255,.16);
        border: 1px solid rgba(255,255,255,.35);
        color: #fff;
        border-radius: 999px;
        padding: .15rem .8rem;
        font-size: .8rem;
        margin: .5rem .35rem 0 0;
      }
    </style>
    """, unsafe_allow_html=True)


# ── Mapa hexagonal (plotly) ───────────────────────────────────────────────────

def hex_center(col: int, row: int, size: float = 1.0) -> tuple[float, float]:
    """Centro do hex (odd-q, flat-top); y invertido p/ linha 1 no topo."""
    x = size * 1.5 * col
    y = size * math.sqrt(3) * (row + 0.5 * (col & 1))
    return x, -y


def _hex_vertices(cx: float, cy: float, size: float = 1.0):
    xs, ys = [], []
    for k in range(7):
        ang = math.radians(60 * k)
        xs.append(cx + size * math.cos(ang))
        ys.append(cy + size * math.sin(ang))
    return xs, ys


def map_figure(units: list[dict] | None = None, *,
               height: int = 560,
               show_labels: bool = True,
               title: str | None = None) -> go.Figure:
    """
    Desenha o teatro de operações. ``units`` são snapshots
    (dicts com id, name, team, category, col, row, hp, maxHp).
    """
    fig = go.Figure()

    # Terreno como polígonos
    for terr in (hx.T_LAND, hx.T_SHALLOW, hx.T_SHELF, hx.T_DEEP, hx.T_OIL):
        xs_all, ys_all = [], []
        for row in range(hx.GRID_H):
            for col in range(hx.GRID_W):
                if hx.TERRAIN_MAP[row][col] != terr:
                    continue
                cx, cy = hex_center(col, row)
                xs, ys = _hex_vertices(cx, cy, 0.98)
                xs_all += xs + [None]
                ys_all += ys + [None]
        if xs_all:
            fig.add_trace(go.Scatter(
                x=xs_all, y=ys_all, mode="lines", fill="toself",
                fillcolor=TERRAIN_COLORS[terr],
                line=dict(color="rgba(255,255,255,.45)", width=1),
                name=hx.TERRAIN_NAMES[terr], hoverinfo="name",
                showlegend=True))

    # Rótulos de coordenadas
    fig.add_trace(go.Scatter(
        x=[hex_center(c, 0)[0] for c in range(hx.GRID_W)],
        y=[2.0] * hx.GRID_W,
        text=[chr(65 + c) for c in range(hx.GRID_W)],
        mode="text", textfont=dict(size=11, color="#888"),
        hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(
        x=[-2.2] * hx.GRID_H,
        y=[hex_center(0, r)[1] for r in range(hx.GRID_H)],
        text=[str(r + 1) for r in range(hx.GRID_H)],
        mode="text", textfont=dict(size=11, color="#888"),
        hoverinfo="skip", showlegend=False))

    # Unidades
    if units:
        # Deslocamento leve para pilhas no mesmo hex
        seen: dict[tuple, int] = {}
        for team, color in (("blue", BLUE_COLOR), ("red", RED_COLOR)):
            xs, ys, texts, hovers, sizes = [], [], [], [], []
            for u in units:
                if u["team"] != team or u["hp"] <= 0:
                    continue
                k = (u["col"], u["row"])
                n = seen.get(k, 0)
                seen[k] = n + 1
                cx, cy = hex_center(u["col"], u["row"])
                cx += (n % 3) * 0.34 - 0.34
                cy += (n // 3) * 0.34 - 0.17
                xs.append(cx)
                ys.append(cy)
                texts.append(CATEGORY_SYMBOLS.get(u["category"], "●"))
                hp_frac = u["hp"] / u["maxHp"] if u["maxHp"] else 0
                hovers.append(
                    f"<b>{u['name']}</b> ({'Azul' if team == 'blue' else 'Vermelha'})"
                    f"<br>{hx.hex_label(u['col'], u['row'])} · "
                    f"SP {u['hp']:.0f}/{u['maxHp']:.0f} ({hp_frac:.0%})")
                sizes.append(15 if u["category"] == "surface" else 13)
            fig.add_trace(go.Scatter(
                x=xs, y=ys, mode="text",
                text=texts,
                textfont=dict(size=15, color=color,
                              family="Arial Black, sans-serif"),
                hovertext=hovers, hoverinfo="text",
                name="Força Azul" if team == "blue" else "Força Vermelha",
                showlegend=True))

    fig.update_layout(
        title=title,
        height=height,
        margin=dict(l=10, r=10, t=40 if title else 10, b=10),
        xaxis=dict(visible=False, scaleanchor="y", scaleratio=1),
        yaxis=dict(visible=False),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig


# ── Estado de sessão compartilhado ────────────────────────────────────────────

def get_oob():
    """Ordem de batalha ativa da sessão (pode ter sido editada/carregada)."""
    from cbp_sim.engine import load_order_of_battle
    if "oob" not in st.session_state:
        st.session_state["oob"] = load_order_of_battle()
    return st.session_state["oob"]


def make_bot(kind: str, tuning=None):
    """Fábrica de bots a partir da seleção da UI."""
    from cbp_sim.bots import HeuristicBot, MLBot
    if kind.startswith("ML"):
        pol = st.session_state.get("ml_policies", {})
        return MLBot(pol.get("move"), pol.get("attack"))
    return HeuristicBot(tuning) if tuning else HeuristicBot()


BOT_OPTIONS = ["Heurístico", "ML (clonagem comportamental)"]
