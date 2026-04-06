"""
Display components for cohort comparison: summary metrics, year-by-year
side-by-side table, delta row, and pricing details.
"""
from __future__ import annotations
import pandas as pd
import streamlit as st

from ui.cohort_engine import CohortScenario

_STD_CLR = "#1B6AC9"
_REV_CLR = "#18924E"
_MAR_CLR = "#E67E22"
_BAL_CLR = "#17A2B8"


def render_funnel_comparison(
    std: CohortScenario, ltv: CohortScenario, top: CohortScenario,
    ai: CohortScenario | None = None,
) -> None:
    """Side-by-side funnel showing stage-to-stage conversion rates.

    Each cell: deal count | → Next stage %
    Rates color-coded green/red vs historical benchmark.
    SQL → Win shown as summary row at bottom.
    """
    from models.funnel_model import compute_historical_funnel
    import config as _cfg

    st.subheader("Sales Funnel", help=(
        "Shows how deals flow through the pipeline from SQL to Won. "
        "Each cell shows the deal count and the conversion rate to the next stage. "
        "Historical rates are the grand-total average (Jan 2023–Mar 2026). "
        "Standard uses Q4 2025 actual rates. "
        "Optimized scenarios apply a graduated improvement factor based on how much "
        "the pricing-driven win rate exceeds the baseline — heavier weighting on later stages "
        "(SAL→ROI, ROI→Negotiation, Negotiation→Won). "
        "SQL→Win at the bottom is the overall pipeline conversion rate. "
        "Green = above historical benchmark. Red = below."
    ))

    _HIST_CLR = "#808495"
    hist_stages = compute_historical_funnel(_cfg.FUNNEL_SQLS_PER_QUARTER)

    stage_names = ["SQL", "SQL-H", "SAL", "ROI", "Negotiation", "Won"]
    _NEXT_STAGE = {
        "SQL": "SQL-H", "SQL-H": "SAL", "SAL": "ROI",
        "ROI": "Negotiation", "Negotiation": "Won",
    }

    def _build_lookup(stages_list: list[dict]) -> dict[str, dict]:
        return {s["name"]: s for s in stages_list}

    hist_lookup = _build_lookup(hist_stages)
    std_lookup = _build_lookup(std.funnel.stages) if std.funnel else {}
    ltv_lookup = _build_lookup(ltv.funnel.stages) if ltv.funnel else {}
    top_lookup = _build_lookup(top.funnel.stages) if top.funnel else {}
    ai_lookup = _build_lookup(ai.funnel.stages) if ai and ai.funnel else {}

    def _deals_won(lookup):
        w = lookup.get("Won")
        return w["count"] if w else 0

    hist_won = _deals_won(hist_lookup)
    std_won = _deals_won(std_lookup)
    ltv_won = _deals_won(ltv_lookup)
    top_won = _deals_won(top_lookup)
    ai_won = _deals_won(ai_lookup) if ai else 0

    def _stage_to_next_rate(lookup, stage_name):
        """Get the conversion rate FROM stage_name TO the next stage."""
        nxt = _NEXT_STAGE.get(stage_name)
        if not nxt:
            return 0.0
        nxt_s = lookup.get(nxt)
        if not nxt_s:
            return 0.0
        return nxt_s.get("adjusted_rate") or nxt_s.get("rate") or 0.0

    hist_s2s = {name: _stage_to_next_rate(hist_lookup, name) for name in stage_names}

    # (label, lookup, color, won_count, is_benchmark)
    columns = [
        ("Historical",    hist_lookup, _HIST_CLR, hist_won, True),
        ("Standard (Q4)", std_lookup,  _STD_CLR,  std_won,  False),
        ("Revenue Opt",   ltv_lookup,  _REV_CLR,  ltv_won,  False),
        ("$ Margin Opt",  top_lookup,  _MAR_CLR,  top_won,  False),
    ]
    if ai is not None:
        columns.append(("Balanced", ai_lookup, _BAL_CLR, ai_won, False))

    header = '<tr><th style="padding:4px 10px;text-align:left;color:#808495;">Stage</th>'
    for name, _, color, _, _ in columns:
        header += (
            f'<th style="padding:4px 10px;text-align:right;color:{color};font-weight:600;">'
            f'{name}</th>'
        )
    header += '</tr>'

    rows = ""
    for stage_name in stage_names:
        row = f'<tr><td style="padding:4px 10px;font-weight:500;">{stage_name}</td>'

        for _, lookup, color, won_count, is_bench in columns:
            s = lookup.get(stage_name)
            if not s:
                row += f'<td style="padding:4px 10px;text-align:right;color:{color};">—</td>'
                continue

            count = s["count"]
            nxt = _NEXT_STAGE.get(stage_name)

            if stage_name == "Won":
                row += (
                    f'<td style="padding:4px 10px;text-align:right;color:{color};font-weight:600;">'
                    f'{count:,}</td>'
                )
            else:
                s2s = _stage_to_next_rate(lookup, stage_name)
                hist_rate = hist_s2s.get(stage_name, 0)

                if is_bench:
                    rate_clr = _HIST_CLR
                elif s2s >= hist_rate:
                    rate_clr = "#09ab3b"
                else:
                    rate_clr = "#ff2b2b"

                arrow_label = f"→ {nxt}" if nxt else ""
                row += (
                    f'<td style="padding:4px 10px;text-align:right;">'
                    f'<span style="color:{color};">{count:,}</span>'
                    f' <span style="font-size:0.8rem;color:{rate_clr};'
                    f'font-weight:600;margin-left:6px;">{arrow_label} {s2s:.1%}</span>'
                    f'</td>'
                )

        row += '</tr>'
        rows += row

    sql_row = (
        '<tr style="border-top:2px solid #ddd;">'
        '<td style="padding:6px 10px;font-weight:600;">SQL → Win</td>'
    )
    hist_sql_to_win = hist_won / sqls if (sqls := hist_lookup.get("SQL", {}).get("count", 0)) else 0
    for label, lookup, color, won_count, is_bench in columns:
        sql_count = lookup.get("SQL", {}).get("count", 0)
        s2w = won_count / sql_count if sql_count > 0 else 0
        if is_bench:
            rate_clr = _HIST_CLR
        elif s2w >= hist_sql_to_win:
            rate_clr = "#09ab3b"
        else:
            rate_clr = "#ff2b2b"
        sql_row += (
            f'<td style="padding:6px 10px;text-align:right;font-weight:600;'
            f'color:{rate_clr};font-size:1.05rem;">{s2w:.1%}</td>'
        )
    sql_row += '</tr>'

    table = (
        '<table style="width:100%;border-collapse:collapse;font-size:1.05rem;">'
        f'<thead style="border-bottom:2px solid #ddd;">{header}</thead>'
        f'<tbody>{rows}{sql_row}</tbody></table>'
    )
    st.markdown(table, unsafe_allow_html=True)


def _scenario_label(scenario: CohortScenario) -> str:
    clr = {
        "Standard Pricing": _STD_CLR,
        "Revenue Optimized": _REV_CLR,
        "$ Margin Optimized": _MAR_CLR,
        "Balanced": _BAL_CLR,
    }.get(scenario.name, "#333")
    return (
        f'<span style="color:{clr};font-weight:600;font-size:1.05rem;">'
        f'{scenario.name}</span> ({scenario.deals_won} deals)'
    )


def render_volume_forecast(
    std: CohortScenario, ltv: CohortScenario, top: CohortScenario,
) -> None:
    """Volume forecast tables showing 3-year volumes by payment type for all scenarios."""
    st.subheader("Volume Forecast", help=(
        "Projected payment volumes per deal × deals won, broken out by payment type "
        "(Card, ACH, Bank). Volumes are derived from real Vol/MRR and Card Vol/MRR ratios "
        "and grow quarterly at the user-defined growth rate. "
        "Card Volume % shows the credit card mix, which drives CC processing revenue. "
        "All scenarios share the same per-deal volume profile — differences come from deal count."
    ))

    def _vol_df(scenario: CohortScenario) -> pd.DataFrame:
        vols = scenario.per_deal_volumes
        deals = scenario.deals_won
        rows = []
        for y in (1, 2, 3):
            v = vols[y]
            rows.append({
                "Year": f"Year {y}",
                "Total Volume": f"${v.total * deals:,.0f}",
                "Card Volume": f"${v.cc * deals:,.0f}",
                "ACH Volume": f"${v.ach * deals:,.0f}",
                "Bank Volume": f"${v.bank_network * deals:,.0f}",
                "Card %": f"{v.cc / v.total:.1%}" if v.total > 0 else "0%",
            })
        t = sum(vols[y].total for y in (1, 2, 3)) * deals
        cc = sum(vols[y].cc for y in (1, 2, 3)) * deals
        ach = sum(vols[y].ach for y in (1, 2, 3)) * deals
        bank = sum(vols[y].bank_network for y in (1, 2, 3)) * deals
        rows.append({
            "Year": "3-Year Total",
            "Total Volume": f"${t:,.0f}",
            "Card Volume": f"${cc:,.0f}",
            "ACH Volume": f"${ach:,.0f}",
            "Bank Volume": f"${bank:,.0f}",
            "Card %": f"{cc / t:.1%}" if t > 0 else "0%",
        })
        return pd.DataFrame(rows)

    col1, col2, col3 = st.columns(3)
    for col, scenario in [(col1, std), (col2, ltv), (col3, top)]:
        with col:
            st.markdown(_scenario_label(scenario), unsafe_allow_html=True)
            st.dataframe(_vol_df(scenario), use_container_width=True, hide_index=True)


def render_summary_metrics(
    std: CohortScenario, ltv: CohortScenario, top: CohortScenario,
    ai: CohortScenario | None = None,
) -> None:
    """Top-level summary: Standard on top, then each optimized scenario with deltas."""

    st.subheader("Cohort Impact Summary", help=(
        "Headline metrics for each pricing scenario applied to the full deal cohort. "
        "Deals Won = total deals through the sales funnel. "
        "3-Year Revenue = total cohort revenue across all active deals, accounting for churn and quarterly growth. "
        "SaaS (ACV) = SaaS subscription revenue only. "
        "3-Year Margin = Revenue minus all costs (CC interchange, ACH costs, SaaS COGS, Teampay costs). "
        "Margin % = Margin / Revenue. "
        "Take Rate = total revenue as a % of total processing volume. "
        "Delta badges (▲/▼) and % changes show the difference vs Standard."
    ))

    def _delta_badge(label: str, is_pos: bool) -> str:
        bg = "rgba(9,171,59,0.15)" if is_pos else "rgba(255,43,43,0.15)"
        clr = "#09ab3b" if is_pos else "#ff2b2b"
        arrow = "▲" if is_pos else "▼"
        return (
            f'<span style="font-size:0.8rem;color:{clr};background:{bg};'
            f'padding:2px 6px;border-radius:4px;margin-left:6px;">'
            f'{arrow} {label}</span>'
        )

    def _pct_change(new_val: float, old_val: float) -> str:
        if old_val == 0:
            return ""
        pct = (new_val - old_val) / abs(old_val)
        is_pos = pct >= 0
        bg = "rgba(9,171,59,0.08)" if is_pos else "rgba(255,43,43,0.08)"
        clr = "#09ab3b" if is_pos else "#ff2b2b"
        border = "rgba(9,171,59,0.4)" if is_pos else "rgba(255,43,43,0.4)"
        return (
            f'<span style="font-size:0.75rem;color:{clr};border:1px solid {border};'
            f'background:{bg};padding:1px 5px;border-radius:3px;margin-left:4px;">'
            f'{pct:+.1%}</span>'
        )

    def _neg_to_won(s):
        """Get Neg→Won rate from funnel (matches the 'Won' row in funnel chart)."""
        if s.funnel and s.funnel.deals_to_negotiation > 0:
            return s.funnel.deals_won / s.funnel.deals_to_negotiation
        return s.win_rate

    def _saas_3yr(s):
        return sum(s.cohort_yearly[y].saas_revenue for y in [1, 2, 3])

    metric_defs = [
        ("Deals Won", lambda s: str(s.deals_won), lambda s: s.deals_won,
         lambda d: f"{d:+.0f}", True),
        ("3-Year Revenue", lambda s: f"${s.three_year_revenue:,.0f}", lambda s: s.three_year_revenue,
         lambda d: f"${d:+,.0f}", True),
        ("SaaS (ACV)", lambda s: f"${_saas_3yr(s):,.0f}", lambda s: _saas_3yr(s),
         lambda d: f"${d:+,.0f}", True),
        ("3-Year Margin", lambda s: f"${s.three_year_margin:,.0f}", lambda s: s.three_year_margin,
         lambda d: f"${d:+,.0f}", True),
        ("Margin %", lambda s: f"{s.three_year_margin_pct:.1%}", lambda s: s.three_year_margin_pct,
         lambda d: f"{d*100:+.1f}pp", True),
        ("Take Rate", lambda s: f"{s.three_year_take_rate:.2%}", lambda s: s.three_year_take_rate,
         lambda d: f"{d*100:+.2f}pp", True),
    ]

    # ── Standard row (benchmark) ──
    st.markdown(
        f'<div style="background:rgba(27,106,201,0.06);border-left:4px solid {_STD_CLR};'
        f'padding:10px 16px;border-radius:4px;margin-bottom:12px;">'
        f'<span style="color:{_STD_CLR};font-weight:700;font-size:1.1rem;">'
        f'Standard Pricing</span>'
        f'<span style="color:#808495;font-size:0.9rem;margin-left:12px;">'
        f'(Benchmark — {std.deals_won} deals)</span></div>',
        unsafe_allow_html=True,
    )
    n_metric_cols = 7 if ai is not None else 6
    std_cols = st.columns(n_metric_cols)
    for i, (label, fmt_fn, _, _, _) in enumerate(metric_defs):
        content = (
            f'<div style="font-size:0.8rem;color:#808495;">{label}</div>'
            f'<div style="font-size:1.5rem;font-weight:500;color:{_STD_CLR};">'
            f'{fmt_fn(std)}</div>'
        )
        if label == "3-Year Revenue":
            content += _yearly_revenue_html(std, _STD_CLR)
        elif label == "SaaS (ACV)":
            content += _yearly_saas_html(std, _STD_CLR)
        std_cols[i].markdown(content, unsafe_allow_html=True)

    st.markdown('<div style="height:8px;"></div>', unsafe_allow_html=True)

    # ── Optimized scenario rows ──
    scenarios = [
        ("Revenue Optimized", ltv, _REV_CLR),
        ("$ Margin Optimized", top, _MAR_CLR),
    ]
    if ai is not None:
        scenarios.append(("Balanced", ai, _BAL_CLR))

    for name, scenario, color in scenarios:
        st.markdown(
            f'<div style="background:rgba(0,0,0,0.02);border-left:4px solid {color};'
            f'padding:8px 16px;border-radius:4px;margin-bottom:4px;">'
            f'<span style="color:{color};font-weight:700;font-size:1.0rem;">'
            f'{name}</span>'
            f'<span style="color:#808495;font-size:0.85rem;margin-left:10px;">'
            f'({scenario.deals_won} deals)</span></div>',
            unsafe_allow_html=True,
        )
        row_cols = st.columns(n_metric_cols)
        for i, (label, fmt_fn, val_fn, delta_fmt, _) in enumerate(metric_defs):
            val = val_fn(scenario)
            std_val = val_fn(std)
            delta = val - std_val
            is_pos = delta >= 0
            pct_badge = _pct_change(val, std_val)
            content = (
                f'<div style="font-size:0.8rem;color:#808495;">{label}</div>'
                f'<div style="font-size:1.4rem;font-weight:500;color:{color};">'
                f'{fmt_fn(scenario)}'
                f'{_delta_badge(delta_fmt(delta), is_pos)}'
                f'{pct_badge}'
                f'</div>'
            )
            if label == "3-Year Revenue":
                content += _yearly_revenue_html(scenario, color)
            elif label == "SaaS (ACV)":
                content += _yearly_saas_html(scenario, color)
            row_cols[i].markdown(content, unsafe_allow_html=True)
        st.markdown('<div style="height:4px;"></div>', unsafe_allow_html=True)


def _yearly_revenue_html(scenario: CohortScenario, color: str) -> str:
    """Return HTML string for Y1/Y2/Y3 revenue below 3-Year Revenue metric."""
    y1 = scenario.cohort_yearly[1].total_revenue
    y2 = scenario.cohort_yearly[2].total_revenue
    y3 = scenario.cohort_yearly[3].total_revenue
    return (
        f'<div style="font-size:0.95rem;color:{color};opacity:0.75;margin-top:2px;">'
        f'Y1: ${y1:,.0f}<br>Y2: ${y2:,.0f}<br>Y3: ${y3:,.0f}</div>'
    )


def _yearly_saas_html(scenario: CohortScenario, color: str) -> str:
    """Return HTML string for Y1/Y2/Y3 SaaS revenue below SaaS (ACV) metric."""
    y1 = scenario.cohort_yearly[1].saas_revenue
    y2 = scenario.cohort_yearly[2].saas_revenue
    y3 = scenario.cohort_yearly[3].saas_revenue
    return (
        f'<div style="font-size:0.95rem;color:{color};opacity:0.75;margin-top:2px;">'
        f'Y1: ${y1:,.0f}<br>Y2: ${y2:,.0f}<br>Y3: ${y3:,.0f}</div>'
    )


def render_scenario_header(scenario: CohortScenario) -> None:
    """Render a scenario header with key stats."""
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Deals Won", scenario.deals_won)
    c2.metric("Win Rate", f"{scenario.win_rate:.0%}")
    c3.metric("3-Year Revenue", f"${scenario.three_year_revenue:,.0f}")
    c4.metric("3-Year Margin", f"${scenario.three_year_margin:,.0f}")


def _yearly_df(scenario: CohortScenario) -> pd.DataFrame:
    """Build a year-by-year DataFrame for a cohort scenario."""
    rows = []
    for y in [1, 2, 3]:
        cy = scenario.cohort_yearly[y]
        rows.append({
            "Year": str(y),
            "SaaS Rev": f"${cy.saas_revenue:,.0f}",
            "Impl Fee": f"${cy.impl_fee_revenue:,.0f}",
            "CC Rev": f"${cy.cc_revenue:,.0f}",
            "ACH Rev": f"${cy.ach_revenue:,.0f}",
            "Float": f"${cy.float_income:,.0f}",
            "TP SaaS": f"${cy.teampay_saas_revenue:,.0f}",
            "TP Proc": f"${cy.teampay_processing_revenue:,.0f}",
            "Total Rev": f"${cy.total_revenue:,.0f}",
            "Total Cost": f"${cy.total_cost:,.0f}",
            "Margin": f"${cy.margin:,.0f}",
            "Margin %": f"{cy.margin_pct:.1%}",
        })

    total_rev = sum(scenario.cohort_yearly[y].total_revenue for y in [1, 2, 3])
    total_cost = sum(scenario.cohort_yearly[y].total_cost for y in [1, 2, 3])
    total_margin = total_rev - total_cost
    rows.append({
        "Year": "Total",
        "SaaS Rev": f"${sum(scenario.cohort_yearly[y].saas_revenue for y in [1,2,3]):,.0f}",
        "Impl Fee": f"${sum(scenario.cohort_yearly[y].impl_fee_revenue for y in [1,2,3]):,.0f}",
        "CC Rev": f"${sum(scenario.cohort_yearly[y].cc_revenue for y in [1,2,3]):,.0f}",
        "ACH Rev": f"${sum(scenario.cohort_yearly[y].ach_revenue for y in [1,2,3]):,.0f}",
        "Float": f"${sum(scenario.cohort_yearly[y].float_income for y in [1,2,3]):,.0f}",
        "TP SaaS": f"${sum(scenario.cohort_yearly[y].teampay_saas_revenue for y in [1,2,3]):,.0f}",
        "TP Proc": f"${sum(scenario.cohort_yearly[y].teampay_processing_revenue for y in [1,2,3]):,.0f}",
        "Total Rev": f"${total_rev:,.0f}",
        "Total Cost": f"${total_cost:,.0f}",
        "Margin": f"${total_margin:,.0f}",
        "Margin %": f"{total_margin / total_rev:.1%}" if total_rev > 0 else "0.0%",
    })
    return pd.DataFrame(rows)


def render_side_by_side_tables(
    std: CohortScenario, ltv: CohortScenario, top: CohortScenario,
) -> None:
    """Year-by-year tables for each scenario, side by side."""

    col1, col2, col3 = st.columns(3)
    for col, scenario in [(col1, std), (col2, ltv), (col3, top)]:
        with col:
            st.markdown(_scenario_label(scenario), unsafe_allow_html=True)
            st.dataframe(_yearly_df(scenario), use_container_width=True, hide_index=True)


def render_delta_table(
    std: CohortScenario, ltv: CohortScenario, top: CohortScenario,
) -> None:
    """Delta tables showing differences vs Standard for both optimized scenarios."""

    def _build_delta_rows(base: CohortScenario, comp: CohortScenario) -> list[dict]:
        rows = []
        for y in [1, 2, 3]:
            s = base.cohort_yearly[y]
            c = comp.cohort_yearly[y]
            tp_s = s.teampay_saas_revenue + s.teampay_processing_revenue
            tp_c = c.teampay_saas_revenue + c.teampay_processing_revenue
            rows.append({
                "Year": str(y),
                "Δ SaaS": f"${c.saas_revenue - s.saas_revenue:+,.0f}",
                "Δ CC": f"${c.cc_revenue - s.cc_revenue:+,.0f}",
                "Δ ACH": f"${c.ach_revenue - s.ach_revenue:+,.0f}",
                "Δ Float": f"${c.float_income - s.float_income:+,.0f}",
                "Δ Teampay": f"${tp_c - tp_s:+,.0f}",
                "Δ Revenue": f"${c.total_revenue - s.total_revenue:+,.0f}",
                "Δ Cost": f"${c.total_cost - s.total_cost:+,.0f}",
                "Δ Margin": f"${c.margin - s.margin:+,.0f}",
                "Δ Margin %": f"{(c.margin_pct - s.margin_pct) * 100:+.1f}pp",
            })

        t_s_rev = sum(base.cohort_yearly[y].total_revenue for y in [1, 2, 3])
        t_c_rev = sum(comp.cohort_yearly[y].total_revenue for y in [1, 2, 3])
        t_s_cost = sum(base.cohort_yearly[y].total_cost for y in [1, 2, 3])
        t_c_cost = sum(comp.cohort_yearly[y].total_cost for y in [1, 2, 3])
        t_s_m = t_s_rev - t_s_cost
        t_c_m = t_c_rev - t_c_cost
        tp_delta = sum(
            (comp.cohort_yearly[y].teampay_saas_revenue + comp.cohort_yearly[y].teampay_processing_revenue)
            - (base.cohort_yearly[y].teampay_saas_revenue + base.cohort_yearly[y].teampay_processing_revenue)
            for y in [1, 2, 3]
        )

        rows.append({
            "Year": "Total",
            "Δ SaaS": f"${sum(comp.cohort_yearly[y].saas_revenue - base.cohort_yearly[y].saas_revenue for y in [1,2,3]):+,.0f}",
            "Δ CC": f"${sum(comp.cohort_yearly[y].cc_revenue - base.cohort_yearly[y].cc_revenue for y in [1,2,3]):+,.0f}",
            "Δ ACH": f"${sum(comp.cohort_yearly[y].ach_revenue - base.cohort_yearly[y].ach_revenue for y in [1,2,3]):+,.0f}",
            "Δ Float": f"${sum(comp.cohort_yearly[y].float_income - base.cohort_yearly[y].float_income for y in [1,2,3]):+,.0f}",
            "Δ Teampay": f"${tp_delta:+,.0f}",
            "Δ Revenue": f"${t_c_rev - t_s_rev:+,.0f}",
            "Δ Cost": f"${t_c_cost - t_s_cost:+,.0f}",
            "Δ Margin": f"${t_c_m - t_s_m:+,.0f}",
            "Δ Margin %": f"{((t_c_m / t_c_rev if t_c_rev else 0) - (t_s_m / t_s_rev if t_s_rev else 0)) * 100:+.1f}pp",
        })
        return rows

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(
            f'<span style="color:{_REV_CLR};font-weight:600;font-size:1.05rem;">'
            f'Revenue Optimized</span> − Standard Delta',
            unsafe_allow_html=True,
        )
        st.dataframe(pd.DataFrame(_build_delta_rows(std, ltv)), use_container_width=True, hide_index=True)
    with col2:
        st.markdown(
            f'<span style="color:{_MAR_CLR};font-weight:600;font-size:1.05rem;">'
            f'$ Margin Optimized</span> − Standard Delta',
            unsafe_allow_html=True,
        )
        st.dataframe(pd.DataFrame(_build_delta_rows(std, top)), use_container_width=True, hide_index=True)


def render_cost_to_collect_ar(
    std: CohortScenario, ltv: CohortScenario, top: CohortScenario,
    ai: CohortScenario | None = None,
) -> None:
    """Cost to Collect AR — what it costs the customer per dollar of revenue collected.

    Assumes 50% of CC volume has convenience fees applied (offset).
    Expressed as a percentage of total processing volume.
    """
    st.subheader("Cost to Collect AR (Per Deal)", help=(
        "All-in cost to the customer to collect their accounts receivable through Paystand, "
        "expressed as a % of total processing volume. "
        "Includes SaaS fees, implementation fees, net CC processing (after 50% convenience fee offset), "
        "and ACH fees. Lower % = more favorable for the customer. "
        "Y1 is typically highest due to implementation fees. "
        "Green = lower cost than Standard. Red = higher cost than Standard."
    ))

    CONV_FEE_OFFSET = 0.50

    def _yearly_cost_pct(scenario, y):
        yr = scenario.per_deal_yearly[y]
        vol = scenario.per_deal_volumes[y]
        saas = yr.saas_revenue
        impl = yr.impl_fee_revenue
        net_cc = yr.cc_revenue * (1 - CONV_FEE_OFFSET)
        ach = yr.ach_revenue
        total_cost = saas + impl + net_cc + ach
        pct = (total_cost / vol.total * 100) if vol.total > 0 else 0
        return saas, impl, net_cc, ach, total_cost, pct

    scenarios = [
        ("Standard", std, _STD_CLR),
        ("Revenue Opt", ltv, _REV_CLR),
        ("$ Margin Opt", top, _MAR_CLR),
    ]
    if ai is not None:
        scenarios.append(("Balanced", ai, _BAL_CLR))

    std_pct = {y: _yearly_cost_pct(std, y)[5] for y in [1, 2, 3]}
    std_3yr_cost = sum(_yearly_cost_pct(std, y)[4] for y in [1, 2, 3])
    std_3yr_vol = sum(std.per_deal_volumes[y].total for y in [1, 2, 3])
    std_pct["3yr"] = (std_3yr_cost / std_3yr_vol * 100) if std_3yr_vol > 0 else 0

    header = '<tr><th style="padding:4px 8px;text-align:left;color:#808495;">Year</th>'
    for label, _, color in scenarios:
        header += (
            f'<th style="padding:4px 8px;text-align:center;" colspan="2">'
            f'<span style="color:{color};font-weight:600;">{label}</span></th>'
        )
    header += '</tr>'
    sub_header = '<tr><td></td>'
    for _ in scenarios:
        sub_header += (
            '<td style="padding:2px 8px;text-align:right;font-size:0.85rem;color:#808495;">$ Cost</td>'
            '<td style="padding:2px 8px;text-align:right;font-size:0.85rem;color:#808495;">%</td>'
        )
    sub_header += '</tr>'

    body = ""
    for y in [1, 2, 3]:
        row = f'<tr><td style="padding:4px 8px;font-weight:500;">Y{y}</td>'
        for label, scenario, color in scenarios:
            _, _, _, _, total_cost, pct = _yearly_cost_pct(scenario, y)
            is_std = (scenario is std)
            if is_std:
                pct_clr = color
            else:
                pct_clr = "#09ab3b" if pct <= std_pct[y] else "#ff2b2b"
            row += (
                f'<td style="padding:4px 8px;text-align:right;">${total_cost:,.0f}</td>'
                f'<td style="padding:4px 8px;text-align:right;color:{pct_clr};font-weight:600;">'
                f'{pct:.2f}%</td>'
            )
        row += '</tr>'
        body += row

    total_row = '<tr style="border-top:2px solid #ddd;"><td style="padding:4px 8px;font-weight:700;">3-Yr Blended</td>'
    for label, scenario, color in scenarios:
        cost_3yr = sum(_yearly_cost_pct(scenario, y)[4] for y in [1, 2, 3])
        vol_3yr = sum(scenario.per_deal_volumes[y].total for y in [1, 2, 3])
        pct_3yr = (cost_3yr / vol_3yr * 100) if vol_3yr > 0 else 0
        is_std = (scenario is std)
        if is_std:
            pct_clr = color
        else:
            pct_clr = "#09ab3b" if pct_3yr <= std_pct["3yr"] else "#ff2b2b"
        total_row += (
            f'<td style="padding:4px 8px;text-align:right;font-weight:700;">${cost_3yr:,.0f}</td>'
            f'<td style="padding:4px 8px;text-align:right;color:{pct_clr};font-weight:700;">'
            f'{pct_3yr:.2f}%</td>'
        )
    total_row += '</tr>'

    table = (
        '<table style="width:100%;border-collapse:collapse;font-size:1.0rem;">'
        f'<thead style="border-bottom:2px solid #ddd;">{header}{sub_header}</thead>'
        f'<tbody>{body}{total_row}</tbody></table>'
    )
    st.markdown(table, unsafe_allow_html=True)


def render_pricing_comparison(
    std: CohortScenario, ltv: CohortScenario, top: CohortScenario,
    ai: CohortScenario | None = None,
) -> None:
    """Side-by-side pricing lever comparison, grouped by category."""
    st.markdown("**Pricing Decisions Comparison (Per Deal)**")

    s = std.per_deal_pricing
    l = ltv.per_deal_pricing
    t = top.per_deal_pricing
    a = ai.per_deal_pricing if ai is not None else None

    import config as cfg
    avg_txn = cfg.ACH_AVG_TXN_SIZE

    def _eff_bps(p):
        fixed_as_bps = p.ach_fixed_fee / avg_txn if avg_txn > 0 else 0
        return p.ach_accel_pct * p.ach_accel_bps + (1 - p.ach_accel_pct) * fixed_as_bps

    def _saas_strategy_label(p):
        if p.saas_strategy == "flat_monthly":
            return f"Flat ${p.saas_flat_monthly:,.0f}/mo"
        return "Discount & Remove"

    def _saas_discount_or_flat(p):
        if p.saas_strategy == "flat_monthly":
            return f"${p.saas_flat_monthly:,.0f}/mo"
        return f"{p.saas_arr_discount_pct:.0%}"

    def _removal_display(p):
        if p.saas_strategy == "flat_monthly":
            return "N/A (flat)"
        return f"{p.removal_pct:.0%} (attain {cfg.REMOVAL_ATTAINMENT:.0%})"

    def _y2_increase_display(p):
        if p.saas_strategy == "flat_monthly":
            return "0% (flat)"
        return f"{p.y2_price_increase_pct:.0%}"

    _HDR = (
        '<div style="font-weight:700;font-size:0.95rem;color:#003B91;'
        'padding:6px 0 2px 0;border-bottom:2px solid #003B91;margin-top:12px;">'
    )
    _cols = (
        f'<span style="color:{_STD_CLR};font-weight:600;">Standard</span>'
        f' &nbsp;|&nbsp; '
        f'<span style="color:{_REV_CLR};font-weight:600;">Revenue Optimized</span>'
        f' &nbsp;|&nbsp; '
        f'<span style="color:{_MAR_CLR};font-weight:600;">$ Margin Optimized</span>'
    )

    _has_ai = a is not None
    _n_cols = 5 if _has_ai else 4

    def _row(label, std_v, rev_v, mar_v, ai_v=None, bold=False):
        w = "font-weight:600;" if bold else ""
        html = (
            f'<tr>'
            f'<td style="padding:4px 8px;{w}color:#333;">{label}</td>'
            f'<td style="padding:4px 8px;color:{_STD_CLR};">{std_v}</td>'
            f'<td style="padding:4px 8px;color:{_REV_CLR};">{rev_v}</td>'
            f'<td style="padding:4px 8px;color:{_MAR_CLR};">{mar_v}</td>'
        )
        if _has_ai:
            html += f'<td style="padding:4px 8px;color:{_BAL_CLR};">{ai_v}</td>'
        html += '</tr>'
        return html

    def _section_hdr(title):
        return (
            f'<tr><td colspan="{_n_cols}" style="padding:10px 8px 4px 0;font-weight:700;'
            f'font-size:0.95rem;color:#003B91;border-bottom:2px solid rgba(0,59,145,0.2);">'
            f'{title}</td></tr>'
        )

    ai_th = (
        f'<th style="text-align:left;padding:6px 8px;color:{_BAL_CLR};font-weight:600;">Balanced</th>'
        if _has_ai else ''
    )
    table = (
        '<table style="width:100%;border-collapse:collapse;font-size:1.05rem;">'
        '<thead><tr style="border-bottom:2px solid #ddd;">'
        '<th style="text-align:left;padding:6px 8px;color:#808495;font-weight:500;">Lever</th>'
        f'<th style="text-align:left;padding:6px 8px;color:{_STD_CLR};font-weight:600;">Standard</th>'
        f'<th style="text-align:left;padding:6px 8px;color:{_REV_CLR};font-weight:600;">Revenue Opt</th>'
        f'<th style="text-align:left;padding:6px 8px;color:{_MAR_CLR};font-weight:600;">$ Margin Opt</th>'
        f'{ai_th}'
        '</tr></thead><tbody>'
    )

    table += _section_hdr("SaaS Pricing")
    table += _row("Strategy", _saas_strategy_label(s), _saas_strategy_label(l), _saas_strategy_label(t),
                   _saas_strategy_label(a) if a else None)
    table += _row("List Price (ARR)", f"${s.saas_arr_list:,.0f}", f"${l.saas_arr_list:,.0f}", f"${t.saas_arr_list:,.0f}",
                   f"${a.saas_arr_list:,.0f}" if a else None)
    table += _row("Discount / Flat Rate", _saas_discount_or_flat(s), _saas_discount_or_flat(l), _saas_discount_or_flat(t),
                   _saas_discount_or_flat(a) if a else None)
    table += _row("Y1 Effective SaaS", f"${s.effective_y1_saas:,.0f}", f"${l.effective_y1_saas:,.0f}", f"${t.effective_y1_saas:,.0f}",
                   f"${a.effective_y1_saas:,.0f}" if a else None, bold=True)
    table += _row("Y2 Discount Removal", _removal_display(s), _removal_display(l), _removal_display(t),
                   _removal_display(a) if a else None)
    table += _row("Y2 Price Increase", _y2_increase_display(s), _y2_increase_display(l), _y2_increase_display(t),
                   _y2_increase_display(a) if a else None, bold=True)

    table += _section_hdr("Implementation")
    table += _row("Impl Fee", f"${s.effective_impl_fee:,.0f}", f"${l.effective_impl_fee:,.0f}", f"${t.effective_impl_fee:,.0f}",
                   f"${a.effective_impl_fee:,.0f}" if a else None)
    table += _row("Impl Discount", f"{s.impl_fee_discount_pct:.0%}", f"{l.impl_fee_discount_pct:.0%}", f"{t.impl_fee_discount_pct:.0%}",
                   f"{a.impl_fee_discount_pct:.0%}" if a else None)

    table += _section_hdr("Credit Card")
    table += _row("CC Base Rate", f"{s.cc_base_rate:.2%}", f"{l.cc_base_rate:.2%}", f"{t.cc_base_rate:.2%}",
                   f"{a.cc_base_rate:.2%}" if a else None)
    table += _row("AMEX Rate", f"{s.cc_amex_rate:.2%}", f"{l.cc_amex_rate:.2%}", f"{t.cc_amex_rate:.2%}",
                   f"{a.cc_amex_rate:.2%}" if a else None)

    table += _section_hdr("ACH")
    table += _row("Effective ACH BPS", f"{_eff_bps(s):.2%}", f"{_eff_bps(l):.2%}", f"{_eff_bps(t):.2%}",
                   f"{_eff_bps(a):.2%}" if a else None, bold=True)
    table += _row("% Accelerated", f"{s.ach_accel_pct:.0%}", f"{l.ach_accel_pct:.0%}", f"{t.ach_accel_pct:.0%}",
                   f"{a.ach_accel_pct:.0%}" if a else None)
    table += _row("Accelerated BPS", f"{s.ach_accel_bps:.2%}", f"{l.ach_accel_bps:.2%}", f"{t.ach_accel_bps:.2%}",
                   f"{a.ach_accel_bps:.2%}" if a else None)
    table += _row("Non-Accel Fixed Fee", f"${s.ach_fixed_fee:.2f}", f"${l.ach_fixed_fee:.2f}", f"${t.ach_fixed_fee:.2f}",
                   f"${a.ach_fixed_fee:.2f}" if a else None)

    table += _section_hdr("Hold Days")
    table += _row(
        "CC / Bank / ACH",
        f"{s.hold_days_cc} / {s.blended_hold_days_bank:.1f} / {s.blended_hold_days_ach:.1f}",
        f"{l.hold_days_cc} / {l.blended_hold_days_bank:.1f} / {l.blended_hold_days_ach:.1f}",
        f"{t.hold_days_cc} / {t.blended_hold_days_bank:.1f} / {t.blended_hold_days_ach:.1f}",
        f"{a.hold_days_cc} / {a.blended_hold_days_bank:.1f} / {a.blended_hold_days_ach:.1f}" if a else None,
    )

    table += '</tbody></table>'
    st.markdown(table, unsafe_allow_html=True)


def render_annualized_impact(
    std: CohortScenario, ltv: CohortScenario, top: CohortScenario,
    ai: CohortScenario | None = None,
) -> None:
    """Staggered multi-cohort impact shown as a cumulative revenue timeline.

    4 quarterly cohorts enter over Q1-Q4. Each cohort generates quarterly
    revenue (Y1/4, Y2/4, Y3/4). The chart shows how total revenue builds
    as cohorts stack up, highlighting the compounding advantage of better pricing.
    """
    import plotly.graph_objects as go

    st.subheader("Annualized Cohort Impact", help=(
        "Models 4 quarterly cohorts entering over a year (Q1–Q4), each running for 3 years. "
        "The stacked area chart shows how quarterly revenue builds as cohorts overlap — "
        "each layer is one cohort's contribution. "
        "The cumulative line chart below shows total revenue across all 4 cohorts over time. "
        "The gap between lines represents the compounding advantage of winning more deals "
        "with optimized pricing across multiple cohorts. "
        "Summary cards at the bottom show the 4-cohort total revenue, margin, and margin %."
    ))

    def _quarterly_revenue(scenario):
        """Break Y1/Y2/Y3 into 12 quarterly values using real monthly volume weights.

        Volume ramps within each year (especially Y1). We use the monthly
        Vol/MRR ratios to compute what fraction of each year's total volume
        falls in each quarter, then distribute that year's revenue accordingly.
        SaaS + impl are spread evenly (subscription), processing revenue
        follows the volume weight curve.
        """
        from models.volume_forecast import MONTHLY_VOL_MRR

        q_rev = []
        for y in [1, 2, 3]:
            m_start = (y - 1) * 12 + 1
            year_monthly = [MONTHLY_VOL_MRR.get(m, 0) for m in range(m_start, m_start + 12)]
            year_total_ratio = sum(year_monthly)

            qtr_weights = []
            for q in range(4):
                qw = sum(year_monthly[q * 3: q * 3 + 3])
                qtr_weights.append(qw / year_total_ratio if year_total_ratio > 0 else 0.25)

            cy = scenario.cohort_yearly[y]
            saas_q = cy.saas_revenue / 4
            impl_q = cy.impl_fee_revenue / 4
            tp_q = (cy.teampay_saas_revenue + cy.teampay_processing_revenue) / 4

            processing_rev = cy.cc_revenue + cy.ach_revenue + cy.bank_revenue + cy.float_income

            for q in range(4):
                q_rev.append(saas_q + impl_q + tp_q + processing_rev * qtr_weights[q])

        return q_rev

    # ── Stacked area: individual cohort layers ──
    scenario_options = {
        "Standard": (std, _STD_CLR),
        "Revenue Optimized": (ltv, _REV_CLR),
        "$ Margin Optimized": (top, _MAR_CLR),
    }
    if ai is not None:
        scenario_options["Balanced"] = (ai, _BAL_CLR)

    selected = st.selectbox(
        "Select scenario to view cohort build-up",
        list(scenario_options.keys()),
        index=1,
        key="annualized_cohort_selector",
    )
    sel_scenario, sel_color = scenario_options[selected]
    cohort_q = _quarterly_revenue(sel_scenario)

    q_labels = [f"Q{((i)%4)+1} Y{((i)//4)+1}" for i in range(12)]
    cohort_names = ["Q1 Cohort", "Q2 Cohort", "Q3 Cohort", "Q4 Cohort"]
    opacity_levels = [1.0, 0.75, 0.55, 0.40]

    fig_stack = go.Figure()
    for c_idx in range(4):
        c_values = []
        for q_idx in range(12):
            age = q_idx - c_idx
            if 0 <= age < len(cohort_q):
                c_values.append(cohort_q[age])
            else:
                c_values.append(0)
        fig_stack.add_trace(go.Scatter(
            x=q_labels, y=c_values,
            name=cohort_names[c_idx],
            mode="lines",
            line=dict(width=0.5, color=sel_color),
            fillcolor=f"rgba({int(sel_color[1:3],16)},{int(sel_color[3:5],16)},{int(sel_color[5:7],16)},{opacity_levels[c_idx]})",
            fill="tonexty" if c_idx > 0 else "tozeroy",
            stackgroup="one",
            hovertemplate="%{fullData.name}: $%{y:,.0f}<extra></extra>",
        ))

    total_by_q = []
    for q_idx in range(12):
        t = sum(
            cohort_q[q_idx - c] if 0 <= (q_idx - c) < len(cohort_q) else 0
            for c in range(4)
        )
        total_by_q.append(t)

    fig_stack.add_annotation(
        x=q_labels[-1], y=total_by_q[-1],
        text=f"${total_by_q[-1]:,.0f}/qtr",
        showarrow=True, arrowhead=2, arrowcolor=sel_color,
        font=dict(color=sel_color, size=12, weight="bold"),
        yshift=20,
    )

    fig_stack.update_layout(
        title=dict(text=f"{selected} — Quarterly Revenue by Cohort", font=dict(size=14)),
        xaxis_title="Quarter",
        yaxis_title="Quarterly Revenue ($)",
        xaxis=dict(tickangle=-45),
        yaxis=dict(tickformat="$,.0f"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(t=60, b=60),
        height=400,
        plot_bgcolor="white",
        hovermode="x unified",
    )
    fig_stack.update_yaxes(gridcolor="rgba(0,0,0,0.06)")
    st.plotly_chart(fig_stack, use_container_width=True)

    # ── Cumulative comparison line chart ──
    st.caption(
        "Cumulative revenue across all cohorts — the gap between lines "
        "is the compounding value of better pricing."
    )

    def _build_cumulative(scenario):
        cq = _quarterly_revenue(scenario)
        quarters = list(range(1, 13))
        cumulative = []
        running = 0.0
        for q_idx in range(12):
            q_total = sum(
                cq[q_idx - c] if 0 <= (q_idx - c) < len(cq) else 0
                for c in range(4)
            )
            running += q_total
            cumulative.append(running)
        return quarters, cumulative

    std_q, std_cum = _build_cumulative(std)
    ltv_q, ltv_cum = _build_cumulative(ltv)
    top_q, top_cum = _build_cumulative(top)

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=std_q, y=std_cum, mode="lines+markers",
        name="Standard", line=dict(color=_STD_CLR, width=3),
        marker=dict(size=5),
    ))
    fig.add_trace(go.Scatter(
        x=ltv_q, y=ltv_cum, mode="lines+markers",
        name="Revenue Optimized", line=dict(color=_REV_CLR, width=3),
        marker=dict(size=5),
    ))
    fig.add_trace(go.Scatter(
        x=top_q, y=top_cum, mode="lines+markers",
        name="$ Margin Optimized", line=dict(color=_MAR_CLR, width=3),
        marker=dict(size=5),
    ))

    if ai is not None:
        ai_q, ai_cum = _build_cumulative(ai)
        fig.add_trace(go.Scatter(
            x=ai_q, y=ai_cum, mode="lines+markers",
            name="Balanced", line=dict(color=_BAL_CLR, width=3),
            marker=dict(size=5),
        ))

    for label, cum, color in [
        ("Standard", std_cum, _STD_CLR),
        ("Revenue Opt", ltv_cum, _REV_CLR),
        ("$ Margin Opt", top_cum, _MAR_CLR),
    ]:
        fig.add_annotation(
            x=12, y=cum[-1],
            text=f"${cum[-1]:,.0f}",
            showarrow=False,
            font=dict(color=color, size=12),
            xanchor="left", xshift=8,
        )

    if ai is not None:
        fig.add_annotation(
            x=12, y=ai_cum[-1],
            text=f"${ai_cum[-1]:,.0f}",
            showarrow=False,
            font=dict(color=_BAL_CLR, size=12),
            xanchor="left", xshift=8,
        )

    fig.update_layout(
        xaxis_title="Quarter",
        yaxis_title="Cumulative Revenue ($)",
        xaxis=dict(
            tickmode="array",
            tickvals=list(range(1, 13)),
            ticktext=[f"Q{((i-1)%4)+1} Y{((i-1)//4)+1}" for i in range(1, 13)],
            tickangle=-45,
        ),
        yaxis=dict(tickformat="$,.0f"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(t=50, b=60, r=100),
        height=400,
        plot_bgcolor="white",
        hovermode="x unified",
    )

    fig.update_yaxes(gridcolor="rgba(0,0,0,0.06)")
    st.plotly_chart(fig, use_container_width=True)

    y3_weights = [1.0, 0.75, 0.50, 0.25]

    def _staggered_totals(scenario):
        y1_r = scenario.cohort_yearly[1].total_revenue
        y2_r = scenario.cohort_yearly[2].total_revenue
        y3_r = scenario.cohort_yearly[3].total_revenue
        y1_c = scenario.cohort_yearly[1].total_cost
        y2_c = scenario.cohort_yearly[2].total_cost
        y3_c = scenario.cohort_yearly[3].total_cost
        tr = sum(y1_r + y2_r + y3_r * w for w in y3_weights)
        tc = sum(y1_c + y2_c + y3_c * w for w in y3_weights)
        return tr, tc

    scenarios = [
        ("Standard", std, _STD_CLR),
        ("Revenue Optimized", ltv, _REV_CLR),
        ("$ Margin Optimized", top, _MAR_CLR),
    ]
    if ai is not None:
        scenarios.append(("Balanced", ai, _BAL_CLR))

    cols = st.columns(len(scenarios))
    for col, (label, scenario, color) in zip(cols, scenarios):
        rev, cost = _staggered_totals(scenario)
        margin = rev - cost
        mpct = margin / rev if rev > 0 else 0
        with col:
            st.markdown(
                f'<div style="border-left:3px solid {color};padding:4px 10px;">'
                f'<div style="color:{color};font-weight:700;font-size:0.95rem;">{label}</div>'
                f'<div style="font-size:0.85rem;color:#808495;">Revenue</div>'
                f'<div style="font-size:1.15rem;font-weight:600;">${rev:,.0f}</div>'
                f'<div style="font-size:0.85rem;color:#808495;">Margin</div>'
                f'<div style="font-size:1.15rem;font-weight:600;">${margin:,.0f}</div>'
                f'<div style="font-size:0.85rem;color:#808495;">Margin %</div>'
                f'<div style="font-size:1.15rem;font-weight:600;">{mpct:.1%}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )


def render_per_deal_comparison(
    std: CohortScenario, ltv: CohortScenario, top: CohortScenario,
) -> None:
    """Per-deal economics comparison so the SaaS trade-off is visible."""
    st.markdown("**Per-Deal Economics (Single Average Deal)**")

    rows = []
    for y in [1, 2, 3]:
        sy = std.per_deal_yearly[y]
        ly = ltv.per_deal_yearly[y]
        ty = top.per_deal_yearly[y]
        rows.append({
            "Year": str(y),
            "Std SaaS": f"${sy.saas_revenue:,.0f}",
            "Rev SaaS": f"${ly.saas_revenue:,.0f}",
            "Mar SaaS": f"${ty.saas_revenue:,.0f}",
            "Std Revenue": f"${sy.total_revenue:,.0f}",
            "Rev Revenue": f"${ly.total_revenue:,.0f}",
            "Mar Revenue": f"${ty.total_revenue:,.0f}",
            "Std Margin": f"${sy.margin:,.0f}",
            "Rev Margin": f"${ly.margin:,.0f}",
            "Mar Margin": f"${ty.margin:,.0f}",
        })

    std_3yr = sum(std.per_deal_yearly[y].total_revenue for y in [1, 2, 3])
    ltv_3yr = sum(ltv.per_deal_yearly[y].total_revenue for y in [1, 2, 3])
    top_3yr = sum(top.per_deal_yearly[y].total_revenue for y in [1, 2, 3])
    std_3yr_m = sum(std.per_deal_yearly[y].margin for y in [1, 2, 3])
    ltv_3yr_m = sum(ltv.per_deal_yearly[y].margin for y in [1, 2, 3])
    top_3yr_m = sum(top.per_deal_yearly[y].margin for y in [1, 2, 3])
    std_3yr_s = sum(std.per_deal_yearly[y].saas_revenue for y in [1, 2, 3])
    ltv_3yr_s = sum(ltv.per_deal_yearly[y].saas_revenue for y in [1, 2, 3])
    top_3yr_s = sum(top.per_deal_yearly[y].saas_revenue for y in [1, 2, 3])
    rows.append({
        "Year": "Total",
        "Std SaaS": f"${std_3yr_s:,.0f}",
        "Rev SaaS": f"${ltv_3yr_s:,.0f}",
        "Mar SaaS": f"${top_3yr_s:,.0f}",
        "Std Revenue": f"${std_3yr:,.0f}",
        "Rev Revenue": f"${ltv_3yr:,.0f}",
        "Mar Revenue": f"${top_3yr:,.0f}",
        "Std Margin": f"${std_3yr_m:,.0f}",
        "Rev Margin": f"${ltv_3yr_m:,.0f}",
        "Mar Margin": f"${top_3yr_m:,.0f}",
    })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


_VAS_PALETTE = [
    "#E67E22", "#F39C12", "#D35400", "#E74C3C", "#C0392B", "#8E44AD",
    "#2980B9", "#1ABC9C", "#27AE60", "#16A085", "#2C3E50", "#7F8C8D",
    "#9B59B6", "#3498DB", "#E91E63", "#FF5722", "#795548", "#607D8B",
    "#00BCD4", "#FFC107", "#4CAF50", "#673AB7", "#009688",
]


def render_upside_breakdown(
    std: CohortScenario, ltv: CohortScenario, top: CohortScenario,
    ai: CohortScenario | None = None,
) -> None:
    """Stacked bar chart showing VAS fee revenue by line item per scenario."""
    import plotly.graph_objects as go

    has_upside = any(
        s.upside_detail is not None and any(s.upside_detail.values())
        for s in [std, ltv, top] + ([ai] if ai else [])
    )
    if not has_upside:
        return

    st.subheader("Value-Added Services Fees", help=(
        "3-year total VAS fee revenue broken down by individual fee item for each scenario. "
        "VAS fees scale directly with deal count — more deals won = proportionally more VAS revenue. "
        "Volume-based fees (Transfer/Recon, Payment Failures, Account Updater) scale with "
        "each deal's payment volume. "
        "Flat fees are derived from the portfolio-level TAM divided by total active customers. "
        "The TAM Assumption toggle (Conservative/Base/Aggressive) adjusts the underlying "
        "market size used for these calculations. "
        "Items with a 'Cost to Build' have that cost amortized as a one-time Y1 expense per deal."
    ))

    scenarios = [
        ("Standard", std, _STD_CLR),
        ("Revenue Optimized", ltv, _REV_CLR),
        ("$ Margin Optimized", top, _MAR_CLR),
    ]
    if ai is not None:
        scenarios.append(("Balanced", ai, _BAL_CLR))

    all_items: list[str] = []
    for _, s, _ in scenarios:
        if s.upside_detail:
            for y in [1, 2, 3]:
                for name in s.upside_detail.get(y, {}):
                    if name not in all_items:
                        all_items.append(name)

    x_labels = [s[0] for s in scenarios]

    fig = go.Figure()
    for idx, item_name in enumerate(all_items):
        color = _VAS_PALETTE[idx % len(_VAS_PALETTE)]
        vals = []
        for _, s, _ in scenarios:
            total = sum(
                (s.upside_detail.get(y, {}) if s.upside_detail else {}).get(item_name, 0)
                for y in [1, 2, 3]
            )
            vals.append(total)
        texts = [f"${v:,.0f}" if v > 20_000 else "" for v in vals]
        fig.add_trace(go.Bar(
            x=x_labels, y=vals,
            name=item_name, marker_color=color,
            text=texts, textposition="inside",
            textfont=dict(color="white", size=11),
        ))

    bar_totals = []
    for _, s, _ in scenarios:
        bar_totals.append(sum(s.cohort_yearly[y].upside_revenue for y in [1, 2, 3]))

    for i, (label, total) in enumerate(zip(x_labels, bar_totals)):
        fig.add_annotation(
            x=label, y=total,
            text=f"<b>${total:,.0f}</b>",
            showarrow=False, yshift=14,
            font=dict(size=13, color=scenarios[i][2]),
        )

    fig.update_layout(
        barmode="stack",
        yaxis=dict(tickformat="$,.0f", title="3-Year VAS Fee Revenue"),
        xaxis=dict(
            tickfont=dict(size=13, weight="bold"),
            tickvals=list(range(len(x_labels))),
            ticktext=[
                f'<span style="color:{scenarios[i][2]}">{lab}</span>'
                for i, lab in enumerate(x_labels)
            ],
        ),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=12)),
        margin=dict(t=50, b=40), height=500,
        plot_bgcolor="white",
    )
    fig.update_yaxes(gridcolor="rgba(0,0,0,0.06)")
    st.plotly_chart(fig, use_container_width=True)
