"""
Visualizations for the cohort pricing impact model.
"""
from __future__ import annotations
import plotly.graph_objects as go
import streamlit as st

from ui.cohort_engine import CohortScenario

STD_COLOR = "#1B6AC9"
REV_COLOR = "#2ECC71"
MAR_COLOR = "#E67E22"
BAL_COLOR = "#17A2B8"
DELTA_POS = "#27AE60"
DELTA_NEG = "#E74C3C"


def render_win_rate_history() -> None:
    """Historical win rate by funnel stage, displayed at the top of the report."""
    from data.win_rate_history import MONTHS, STAGES

    st.markdown("**Historical Win Rates by Funnel Stage**")

    fig = go.Figure()
    for stage_name, info in STAGES.items():
        fig.add_trace(go.Scatter(
            x=MONTHS,
            y=info["values"],
            mode="lines+markers+text",
            name=stage_name,
            line=dict(color=info["color"], width=2),
            marker=dict(size=5),
            text=[f"{v:.1f}%" for v in info["values"]],
            textposition="top center",
            textfont=dict(size=8, color=info["color"]),
        ))

    fig.update_layout(
        height=380,
        margin=dict(l=40, r=20, t=30, b=40),
        yaxis=dict(
            title="Win Rate %",
            range=[0, 100],
            ticksuffix="%",
            gridcolor="rgba(0,0,0,0.06)",
        ),
        xaxis=dict(tickangle=-45),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
            font=dict(size=11),
        ),
        plot_bgcolor="white",
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)


def render_break_even_chart(
    std: CohortScenario,
    ltv: CohortScenario,
    top: CohortScenario,
    ai: CohortScenario | None = None,
) -> None:
    """Cumulative margin over time with crossover points."""
    st.subheader("Cumulative Margin Timeline", help=(
        "Shows how total margin ($) accumulates over 3 years for each scenario. "
        "Margin = Revenue minus all costs (CC interchange, ACH costs, SaaS COGS, Teampay costs, VAS build costs). "
        "Break-even points mark where an optimized scenario's cumulative margin first surpasses Standard — "
        "this tells you how long it takes for the deal count advantage to overcome any per-deal margin trade-off. "
        "'Ahead from start' means the scenario had higher margin than Standard from Year 1."
    ))

    years = [0, 1, 2, 3]

    def _cum_margins(scenario):
        cum = [0.0]
        running = 0.0
        for y in [1, 2, 3]:
            running += scenario.cohort_yearly[y].margin
            cum.append(running)
        return cum

    std_cum = _cum_margins(std)
    ltv_cum = _cum_margins(ltv)
    top_cum = _cum_margins(top)

    def _find_crossover(base, comp):
        """Find where comp's cumulative margin first exceeds base.

        Returns (year_float, was_ever_behind).
        was_ever_behind=False means comp was ahead from Year 1 (no real crossover).
        """
        ever_behind = any(comp[i] < base[i] for i in range(1, len(years)))
        for i in range(1, len(years)):
            diff = comp[i] - base[i]
            if diff >= 0:
                prev_diff = comp[i - 1] - base[i - 1]
                if prev_diff < 0:
                    frac = -prev_diff / (diff - prev_diff)
                    return years[i - 1] + frac, True
                return float(years[i]), ever_behind
        return None, ever_behind

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=years, y=std_cum, mode="lines+markers+text",
        name="Standard", line=dict(color=STD_COLOR, width=3),
        text=[""] + [f"${v:,.0f}" for v in std_cum[1:]],
        textposition="top left", textfont=dict(size=11),
    ))
    fig.add_trace(go.Scatter(
        x=years, y=ltv_cum, mode="lines+markers+text",
        name="Revenue Optimized", line=dict(color=REV_COLOR, width=3),
        text=[""] + [f"${v:,.0f}" for v in ltv_cum[1:]],
        textposition="top center", textfont=dict(size=11),
    ))
    fig.add_trace(go.Scatter(
        x=years, y=top_cum, mode="lines+markers+text",
        name="$ Margin Optimized", line=dict(color=MAR_COLOR, width=3),
        text=[""] + [f"${v:,.0f}" for v in top_cum[1:]],
        textposition="bottom center", textfont=dict(size=11),
    ))

    if ai is not None:
        bal_cum = _cum_margins(ai)
        fig.add_trace(go.Scatter(
            x=years, y=bal_cum, mode="lines+markers+text",
            name="Balanced", line=dict(color=BAL_COLOR, width=3),
            text=[""] + [f"${v:,.0f}" for v in bal_cum[1:]],
            textposition="bottom left", textfont=dict(size=11),
        ))

    def _crossover_label(prefix, cross_year, was_behind):
        if not was_behind:
            return f"{prefix}: Ahead from start"
        if cross_year == int(cross_year):
            return f"{prefix}: Year {int(cross_year)}"
        return f"{prefix}: ~Year {cross_year:.1f}"

    ltv_cross, ltv_behind = _find_crossover(std_cum, ltv_cum)
    if ltv_cross is not None:
        label = _crossover_label("Revenue break-even", ltv_cross, ltv_behind)
        if ltv_behind:
            fig.add_vline(x=ltv_cross, line_dash="dash", line_color=REV_COLOR,
                          annotation_text=label, annotation_position="top right",
                          annotation_font_color=REV_COLOR)
        else:
            fig.add_annotation(
                x=0.5, y=ltv_cum[1], text=label,
                showarrow=False, font=dict(color=REV_COLOR, size=11),
                xanchor="left", yanchor="bottom",
            )

    top_cross, top_behind = _find_crossover(std_cum, top_cum)
    if top_cross is not None:
        label = _crossover_label("$ Margin break-even", top_cross, top_behind)
        if top_behind:
            fig.add_vline(x=top_cross, line_dash="dash", line_color=MAR_COLOR,
                          annotation_text=label, annotation_position="bottom right",
                          annotation_font_color=MAR_COLOR)
        else:
            fig.add_annotation(
                x=0.5, y=top_cum[1], text=label,
                showarrow=False, font=dict(color=MAR_COLOR, size=11),
                xanchor="left", yanchor="top",
            )

    if ai is not None:
        bal_cross, bal_behind = _find_crossover(std_cum, bal_cum)
        if bal_cross is not None:
            label = _crossover_label("Balanced break-even", bal_cross, bal_behind)
            if bal_behind:
                fig.add_vline(x=bal_cross, line_dash="dash", line_color=BAL_COLOR,
                              annotation_text=label, annotation_position="top left",
                              annotation_font_color=BAL_COLOR)
            else:
                fig.add_annotation(
                    x=0.5, y=bal_cum[1], text=label,
                    showarrow=False, font=dict(color=BAL_COLOR, size=11),
                    xanchor="left", yanchor="bottom",
                )

    fig.update_layout(
        xaxis_title="Year", yaxis_title="Cumulative Margin ($)",
        xaxis=dict(tickmode="array", tickvals=[0, 1, 2, 3], ticktext=["Year 0", "Year 1", "Year 2", "Year 3"]),
        yaxis=dict(tickformat="$,.0f"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(t=50, b=40), height=400,
    )
    st.plotly_chart(fig, use_container_width=True)


def render_cumulative_revenue_chart(
    std: CohortScenario,
    ltv: CohortScenario,
    top: CohortScenario,
    ai: CohortScenario | None = None,
) -> None:
    """Cumulative revenue over time — mirrors the margin timeline."""
    st.subheader("Cumulative Revenue Timeline", help=(
        "Shows how total revenue accumulates over 3 years for each scenario. "
        "Revenue includes SaaS, CC processing, ACH processing, float income, "
        "implementation fees, Teampay, and VAS fees. "
        "The gap between lines represents the compounding revenue advantage of winning more deals. "
        "Scenarios with more deals pull further ahead each year as volume grows and VAS fees compound."
    ))

    years = [0, 1, 2, 3]

    def _cum_revenue(scenario):
        cum = [0.0]
        running = 0.0
        for y in [1, 2, 3]:
            running += scenario.cohort_yearly[y].total_revenue
            cum.append(running)
        return cum

    std_cum = _cum_revenue(std)
    ltv_cum = _cum_revenue(ltv)
    top_cum = _cum_revenue(top)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=years, y=std_cum, mode="lines+markers+text",
        name="Standard", line=dict(color=STD_COLOR, width=3),
        text=[""] + [f"${v:,.0f}" for v in std_cum[1:]],
        textposition="top left", textfont=dict(size=11),
    ))
    fig.add_trace(go.Scatter(
        x=years, y=ltv_cum, mode="lines+markers+text",
        name="Revenue Optimized", line=dict(color=REV_COLOR, width=3),
        text=[""] + [f"${v:,.0f}" for v in ltv_cum[1:]],
        textposition="top center", textfont=dict(size=11),
    ))
    fig.add_trace(go.Scatter(
        x=years, y=top_cum, mode="lines+markers+text",
        name="$ Margin Optimized", line=dict(color=MAR_COLOR, width=3),
        text=[""] + [f"${v:,.0f}" for v in top_cum[1:]],
        textposition="bottom center", textfont=dict(size=11),
    ))

    if ai is not None:
        bal_cum = _cum_revenue(ai)
        fig.add_trace(go.Scatter(
            x=years, y=bal_cum, mode="lines+markers+text",
            name="Balanced", line=dict(color=BAL_COLOR, width=3),
            text=[""] + [f"${v:,.0f}" for v in bal_cum[1:]],
            textposition="bottom left", textfont=dict(size=11),
        ))

    fig.update_layout(
        xaxis_title="Year", yaxis_title="Cumulative Revenue ($)",
        xaxis=dict(tickmode="array", tickvals=[0, 1, 2, 3], ticktext=["Year 0", "Year 1", "Year 2", "Year 3"]),
        yaxis=dict(tickformat="$,.0f"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(t=50, b=40), height=400,
    )
    st.plotly_chart(fig, use_container_width=True)


def render_revenue_composition(
    std: CohortScenario,
    ltv: CohortScenario,
    top: CohortScenario,
    ai: CohortScenario | None = None,
) -> None:
    """Stacked bar showing revenue mix by year for all three or four scenarios."""
    st.subheader("Revenue Composition by Year", help=(
        "Stacked bars showing where revenue comes from each year, for each scenario side by side. "
        "SaaS = subscription fees (affected by discount/removal strategy and churn). "
        "CC = credit card processing revenue (Y1 uses scenario rates; Y2/Y3 revert to standard). "
        "ACH = ACH processing revenue (accelerated BPS + non-accelerated fixed fees). "
        "Float = interest earned on funds held during settlement. "
        "Impl Fee = one-time implementation fee (Y1 only). "
        "TP SaaS/Proc = Teampay add-on subscription and processing revenue. "
        "VAS Fees = value-added service fee revenue (scales with deal count). "
        "Totals shown above each bar. Vertical lines separate year groupings."
    ))

    categories = ["SaaS", "CC", "ACH", "Float", "Impl Fee", "TP SaaS", "TP Proc", "VAS Fees"]
    colors = ["#3498DB", "#1B6AC9", "#2980B9", "#1ABC9C", "#95A5A6", "#9B59B6", "#8E44AD", "#E67E22"]

    def _year_vals(s: CohortScenario, y: int) -> list[float]:
        cy = s.cohort_yearly[y]
        return [cy.saas_revenue, cy.cc_revenue, cy.ach_revenue,
                cy.float_income, cy.impl_fee_revenue,
                cy.teampay_saas_revenue, cy.teampay_processing_revenue,
                cy.upside_revenue]

    if ai is not None:
        x_labels = [
            "Std Y1", "Rev Y1", "$Mar Y1", "Bal Y1",
            "Std Y2", "Rev Y2", "$Mar Y2", "Bal Y2",
            "Std Y3", "Rev Y3", "$Mar Y3", "Bal Y3",
        ]
    else:
        x_labels = [
            "Std Y1", "Rev Y1", "$Mar Y1",
            "Std Y2", "Rev Y2", "$Mar Y2",
            "Std Y3", "Rev Y3", "$Mar Y3",
        ]
    _label_color_map = {"Std": STD_COLOR, "Rev": REV_COLOR, "$Mar": MAR_COLOR, "Bal": BAL_COLOR}
    def _tick_color(lab):
        for prefix, color in _label_color_map.items():
            if lab.startswith(prefix):
                return color
        return "#333"
    tick_colors = [_tick_color(lab) for lab in x_labels]

    all_vals: list[list[float]] = []
    for y in (1, 2, 3):
        all_vals.append(_year_vals(std, y))
        all_vals.append(_year_vals(ltv, y))
        all_vals.append(_year_vals(top, y))
        if ai is not None:
            all_vals.append(_year_vals(ai, y))

    fig = go.Figure()
    for i, cat in enumerate(categories):
        y_vals = [bar[i] for bar in all_vals]
        texts = [f"${v:,.0f}" if v > 50_000 else "" for v in y_vals]
        fig.add_trace(go.Bar(
            x=x_labels, y=y_vals,
            name=cat, marker_color=colors[i],
            text=texts, textposition="inside",
            textfont=dict(color="white", size=11),
        ))

    fig.update_layout(
        barmode="stack",
        yaxis=dict(tickformat="$,.0f", tickfont=dict(size=14)),
        xaxis=dict(
            tickfont=dict(size=13, weight="bold"),
            tickvals=list(range(len(x_labels))),
            ticktext=[
                f'<span style="color:{c}">{lab}</span>'
                for lab, c in zip(x_labels, tick_colors)
            ],
        ),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=13)),
        margin=dict(t=50, b=40), height=650,
    )

    bar_totals = [sum(bar) for bar in all_vals]
    for i, (label, total) in enumerate(zip(x_labels, bar_totals)):
        fig.add_annotation(
            x=label, y=total,
            text=f"<b>${total:,.0f}</b>",
            showarrow=False,
            yshift=12,
            font=dict(size=12, color=_tick_color(label)),
        )

    if ai is not None:
        for x_pos in [3.5, 7.5]:
            fig.add_vline(x=x_pos, line_dash="dot", line_color="#ccc", line_width=1)
    else:
        for x_pos in [2.5, 5.5]:
            fig.add_vline(x=x_pos, line_dash="dot", line_color="#ccc", line_width=1)

    st.plotly_chart(fig, use_container_width=True)


def render_insight_callouts(
    std: CohortScenario,
    ltv: CohortScenario,
    top: CohortScenario,
) -> None:
    """Key insight messages."""
    BOX = (
        '<div style="padding:12px 16px;background:#e8f4fd;border-left:4px solid #1B6AC9;'
        'border-radius:4px;margin-bottom:8px;color:#1B6AC9;font-size:0.95rem;">'
    )
    BOX_GREEN = (
        '<div style="padding:12px 16px;background:#e8f8ef;border-left:4px solid #2ECC71;'
        'border-radius:4px;margin-bottom:8px;color:#1a6e3a;font-size:0.95rem;">'
    )
    BOX_ORANGE = (
        '<div style="padding:12px 16px;background:#fef3e8;border-left:4px solid #E67E22;'
        'border-radius:4px;margin-bottom:8px;color:#a85d1a;font-size:0.95rem;">'
    )

    ltv_deal_delta = ltv.deals_won - std.deals_won
    top_deal_delta = top.deals_won - std.deals_won

    if ltv_deal_delta > 0 or top_deal_delta > 0:
        st.markdown(
            f'{BOX_GREEN}Optimized pricing wins <b>{ltv_deal_delta} more deals</b> (Revenue) '
            f'/ <b>{top_deal_delta} more deals</b> ($ Margin) '
            f'from the same pipeline ({std.deals_won} standard).</div>',
            unsafe_allow_html=True,
        )

    ltv_margin = ltv.three_year_margin - std.three_year_margin
    top_margin = top.three_year_margin - std.three_year_margin
    ltv_rev = ltv.three_year_revenue - std.three_year_revenue
    top_rev = top.three_year_revenue - std.three_year_revenue

    st.markdown(
        f'{BOX}3-year margin impact: Revenue <b>${ltv_margin:+,.0f}</b> &nbsp;|&nbsp; '
        f'$ Margin <b>${top_margin:+,.0f}</b></div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        f'{BOX_ORANGE}3-year revenue impact: Revenue <b>${ltv_rev:+,.0f}</b> &nbsp;|&nbsp; '
        f'$ Margin <b>${top_rev:+,.0f}</b></div>',
        unsafe_allow_html=True,
    )


def render_exit_arr(
    std: CohortScenario,
    ltv: CohortScenario,
    top: CohortScenario,
    ai: CohortScenario | None = None,
) -> None:
    """Stacked bar chart showing Exit ARR by revenue component at end of each year."""
    from models.volume_forecast import MONTHLY_VOL_MRR

    st.subheader("Exit ARR by Year (Single Quarterly Cohort)", help=(
        "Exit ARR for ONE quarterly cohort (not accumulated across multiple cohorts). "
        "Annualized recurring run-rate at the END of each year, calculated as "
        "Q4 quarterly revenue × 4, reflecting actual churn, growth, and retention. "
        "Excludes one-time implementation fees. "
        "Stacked bars show the revenue composition: SaaS, CC, ACH, Float, "
        "Teampay, and VAS fees. "
        "SaaS:Fees ratio shown below each bar = SaaS / (CC + ACH). "
        "A 1:1 ratio means equal SaaS and processing fee revenue."
    ))

    def _q4_components(scenario, y):
        """Return annualized (×4) revenue components for Q4 of a given year."""
        m_start = (y - 1) * 12 + 1
        year_monthly = [MONTHLY_VOL_MRR.get(m, 0) for m in range(m_start, m_start + 12)]
        year_total_ratio = sum(year_monthly)
        q4_weight = (
            sum(year_monthly[9:12]) / year_total_ratio
            if year_total_ratio > 0 else 0.25
        )

        cy = scenario.cohort_yearly[y]
        return {
            "SaaS": cy.saas_revenue / 4 * 4,
            "CC": cy.cc_revenue * q4_weight * 4,
            "ACH": cy.ach_revenue * q4_weight * 4,
            "Float": cy.float_income * q4_weight * 4,
            "Teampay": (cy.teampay_saas_revenue + cy.teampay_processing_revenue) / 4 * 4,
            "VAS Fees": cy.upside_revenue / 4 * 4,
        }

    categories = ["SaaS", "CC", "ACH", "Float", "Teampay", "VAS Fees"]
    cat_colors = ["#3498DB", "#1B6AC9", "#2980B9", "#1ABC9C", "#9B59B6", "#E67E22"]

    scenarios = [
        ("Standard", std, STD_COLOR),
        ("Revenue Opt", ltv, REV_COLOR),
        ("$ Margin Opt", top, MAR_COLOR),
    ]
    if ai is not None:
        scenarios.append(("Bal", ai, BAL_COLOR))

    n = len(scenarios)
    if ai is not None:
        x_labels = [
            "Std Y1", "Rev Y1", "$Mar Y1", "Bal Y1",
            "Std Y2", "Rev Y2", "$Mar Y2", "Bal Y2",
            "Std Y3", "Rev Y3", "$Mar Y3", "Bal Y3",
        ]
    else:
        x_labels = [
            "Std Y1", "Rev Y1", "$Mar Y1",
            "Std Y2", "Rev Y2", "$Mar Y2",
            "Std Y3", "Rev Y3", "$Mar Y3",
        ]

    _label_color_map = {"Std": STD_COLOR, "Rev": REV_COLOR, "$Mar": MAR_COLOR, "Bal": BAL_COLOR}
    def _tick_color(lab):
        for prefix, color in _label_color_map.items():
            if lab.startswith(prefix):
                return color
        return "#333"

    all_components = []
    for y in [1, 2, 3]:
        for _, scenario, _ in scenarios:
            all_components.append(_q4_components(scenario, y))

    fig = go.Figure()
    for i, cat in enumerate(categories):
        y_vals = [comp[cat] for comp in all_components]
        texts = [f"${v:,.0f}" if v > 30_000 else "" for v in y_vals]
        fig.add_trace(go.Bar(
            x=x_labels, y=y_vals,
            name=cat, marker_color=cat_colors[i],
            text=texts, textposition="inside",
            textfont=dict(color="white", size=11),
        ))

    bar_totals = [sum(comp.values()) for comp in all_components]
    for i, (label, total) in enumerate(zip(x_labels, bar_totals)):
        saas = all_components[i]["SaaS"]
        fees = all_components[i]["CC"] + all_components[i]["ACH"]
        ratio = fees / saas if saas > 0 else 0
        fig.add_annotation(
            x=label, y=total,
            text=f"<b>${total:,.0f}</b>",
            showarrow=False, yshift=12,
            font=dict(size=11, color=_tick_color(label)),
        )
        fig.add_annotation(
            x=label, y=0,
            text=f"<b>SaaS:Fees 1:{ratio:.1f}</b>",
            showarrow=False, yshift=-18,
            font=dict(size=13, color="#555"),
        )

    if ai is not None:
        for x_pos in [3.5, 7.5]:
            fig.add_vline(x=x_pos, line_dash="dot", line_color="#ccc", line_width=1)
    else:
        for x_pos in [2.5, 5.5]:
            fig.add_vline(x=x_pos, line_dash="dot", line_color="#ccc", line_width=1)

    fig.update_layout(
        barmode="stack",
        yaxis=dict(tickformat="$,.0f", title="Exit ARR ($)"),
        xaxis=dict(
            tickfont=dict(size=13, weight="bold"),
            tickvals=list(range(len(x_labels))),
            ticktext=[
                f'<span style="color:{_tick_color(lab)}">{lab}</span>'
                for lab in x_labels
            ],
        ),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=13)),
        margin=dict(t=50, b=60),
        height=570,
        plot_bgcolor="white",
    )
    fig.update_yaxes(gridcolor="rgba(0,0,0,0.06)")
    st.plotly_chart(fig, use_container_width=True)
