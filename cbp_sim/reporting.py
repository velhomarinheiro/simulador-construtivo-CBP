"""Geração de relatórios (Markdown) para download no app."""

from __future__ import annotations

from datetime import datetime

import pandas as pd


def _fmt_pct(x: float) -> str:
    return f"{100 * x:.1f}%"


def batch_report_md(summary: dict, df: pd.DataFrame, *,
                    title: str = "Relatório de Simulação Construtiva",
                    config: dict | None = None) -> str:
    """Relatório de um lote Monte Carlo."""
    ci = summary["p_blue_win_ci95"]
    lines = [
        f"# {title}",
        "",
        f"*Gerado em {datetime.now():%d/%m/%Y %H:%M} — Simulador Construtivo "
        "CBP · Cenário Operação Atlântico Sul*",
        "",
        "## Configuração",
        "",
    ]
    if config:
        for k, v in config.items():
            lines.append(f"- **{k}**: {v}")
    lines += [
        "",
        "## Medidas de Eficácia (MOEs)",
        "",
        f"| MOE | Valor |",
        f"|---|---|",
        f"| Replicações | {summary['n_runs']} |",
        f"| P(vitória Força Azul) | {_fmt_pct(summary['p_blue_win'])} "
        f"(IC95%: {_fmt_pct(ci[0])}–{_fmt_pct(ci[1])}) |",
        f"| Duração média da campanha | {summary['mean_turns']:.1f} dias |",
        f"| FPSOs sobreviventes (média) | "
        f"{summary['mean_fpsos_surviving']:.2f} / 4 |",
        f"| Integridade portuária média | "
        f"{summary['mean_port_integrity']:.1f}% |",
        f"| Perdas Força Azul (média, % SP) | "
        f"{summary['mean_blue_losses']:.1f}% |",
        f"| Perdas Força Vermelha (média, % SP) | "
        f"{summary['mean_red_losses']:.1f}% |",
        f"| Razão de troca média (verm./azul) | "
        f"{summary['mean_exchange_ratio']:.2f} |",
        f"| Decisão por limite operacional | {_fmt_pct(summary['p_timeout'])} |",
        "",
        "## Replicações",
        "",
        df.to_markdown(index=False),
        "",
        "---",
        "",
        "*Metodologia: simulação construtiva bot × bot com mecânica do "
        "wargame Operação Atlântico Sul; engajamentos adjudicados pela "
        "equação de salva multidomínio (naval_salvo) com matriz de "
        "admissibilidade canônica 5×5.*",
    ]
    return "\n".join(lines)


def comparison_report_md(results: list[dict], *,
                         title: str = "Análise de Alternativas — "
                                      "Planejamento Baseado em Capacidades") -> str:
    """
    Relatório comparativo de pacotes de força.

    ``results``: lista de dicts com chaves ``package`` (nome), ``cost``,
    ``summary`` (de montecarlo.summarize) e opcionalmente ``description``.
    """
    lines = [
        f"# {title}",
        "",
        f"*Gerado em {datetime.now():%d/%m/%Y %H:%M} — Simulador Construtivo "
        "CBP · Cenário Operação Atlântico Sul*",
        "",
        "## Alternativas avaliadas",
        "",
    ]
    for r in results:
        if r.get("description"):
            lines.append(f"- **{r['package']}** — {r['description']}")
    lines += [
        "",
        "## Comparação de eficácia e custo",
        "",
        "| Pacote de Força | Custo (UC) | P(vitória Azul) | FPSOs sobrev. | "
        "Integr. portos | Perdas Azul | Razão de troca |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        s = r["summary"]
        lines.append(
            f"| {r['package']} | {r['cost']:.1f} | "
            f"{_fmt_pct(s['p_blue_win'])} | "
            f"{s['mean_fpsos_surviving']:.2f}/4 | "
            f"{s['mean_port_integrity']:.0f}% | "
            f"{s['mean_blue_losses']:.0f}% | "
            f"{s['mean_exchange_ratio']:.2f} |")
    best_eff = max(results, key=lambda r: r["summary"]["p_blue_win"])
    cheapest = min(results, key=lambda r: r["cost"])
    ratio = [(r, r["summary"]["p_blue_win"] / r["cost"] if r["cost"] else 0)
             for r in results]
    best_ce = max(ratio, key=lambda t: t[1])[0]
    lines += [
        "",
        "## Destaques",
        "",
        f"- **Maior eficácia**: {best_eff['package']} "
        f"(P(vitória) = {_fmt_pct(best_eff['summary']['p_blue_win'])}).",
        f"- **Melhor custo-efetividade**: {best_ce['package']}.",
        f"- **Menor custo**: {cheapest['package']} "
        f"({cheapest['cost']:.1f} UC).",
        "",
        "---",
        "",
        "*Custos em unidades de custo (UC) ilustrativas. As MOEs derivam de "
        "replicações Monte Carlo da simulação construtiva (mecânica OAS + "
        "equação de salva multidomínio). Resultados destinam-se a comparação "
        "relativa entre alternativas, não a predição absoluta.*",
    ]
    return "\n".join(lines)
