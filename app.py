"""
Paystand Cohort Pricing Impact Model

Compares Standard pricing vs Revenue-Optimized vs Margin%-Optimized
pricing applied to a full deal cohort, showing 3-year financials,
break-even, and revenue impact.
"""
import streamlit as st

st.set_page_config(
    page_title="Paystand Cohort Impact Model",
    page_icon="paystand_logo.png",
    layout="wide",
)

st.markdown(
    """<style>
    /* Bigger text in all dataframe tables */
    .stDataFrame table,
    .stDataFrame th,
    .stDataFrame td,
    div[data-testid="stDataFrame"] table,
    div[data-testid="stDataFrame"] th,
    div[data-testid="stDataFrame"] td,
    .dvn-scroller table,
    .dvn-scroller th,
    .dvn-scroller td,
    [data-testid="glideDataEditor"] * {
        font-size: 1.15rem !important;
    }
    /* Blue subheaders to match title */
    h2, h3, [data-testid="stSubheader"] {
        color: #001F5B !important;
    }
    /* Blue primary button */
    .stButton > button[kind="primary"],
    .stButton > button[data-testid="baseButton-primary"] {
        background-color: #003B91 !important;
        border-color: #003B91 !important;
    }
    .stButton > button[kind="primary"]:hover,
    .stButton > button[data-testid="baseButton-primary"]:hover {
        background-color: #002D6F !important;
        border-color: #002D6F !important;
    }
    </style>""",
    unsafe_allow_html=True,
)

import config as cfg
from ui.cohort_inputs import render_cohort_inputs, render_standard_pricing
from ui.cohort_engine import run_cohort_comparison, build_balanced_scenario
from ui.cohort_display import (
    render_funnel_comparison,
    render_volume_forecast,
    render_summary_metrics,
    render_annualized_impact,
    render_scenario_header,
    render_pricing_comparison,
    render_cost_to_collect_ar,
    render_upside_breakdown,
)
from ui.cohort_charts import (
    render_break_even_chart,
    render_cumulative_revenue_chart,
    render_revenue_composition,
    render_insight_callouts,
    render_exit_arr,
)


def _format_changes(scenario):
    if not scenario.lever_changes:
        return None
    parts = []
    for k, (old, new) in scenario.lever_changes.items():
        label = k.replace("_", " ").title()
        if isinstance(old, str) or isinstance(new, str):
            parts.append(f"{label}: {old} → {new}")
        elif "rate" in k or "pct" in k:
            parts.append(f"{label}: {old:.2%} → {new:.2%}")
        elif "fee" in k or "cap" in k:
            parts.append(f"{label}: ${old:.2f} → ${new:.2f}")
        else:
            parts.append(f"{label}: {old} → {new}")
    return " | ".join(parts)


def main():
    logo_col, title_col = st.columns([0.06, 0.94], gap="small")
    with logo_col:
        st.image("paystand_logo.png", width=55)
    with title_col:
        st.markdown(
            '<h1 style="color: #001F5B; margin-top: -5px;">'
            "Cohort Pricing Impact Model</h1>",
            unsafe_allow_html=True,
        )

    cohort = render_cohort_inputs()
    std_pricing = render_standard_pricing()

    if st.button("Run Cohort Analysis", type="primary", use_container_width=True):
        with st.spinner("Solving for target win rate and scaling to cohort..."):
            standard, revenue_opt, margin_opt, solver_msg = run_cohort_comparison(
                sqls_per_quarter=cohort["sqls_per_quarter"],
                current_win_rate=cohort["current_win_rate"],
                avg_saas_arr=cohort["avg_saas_arr"],
                avg_impl_fee=cohort["avg_impl_fee"],
                total_arr_won=cohort["total_arr_won"],
                standard_pricing_inputs=std_pricing,
                quarterly_growth=cohort["quarterly_growth"],
                tp_contract_optin=cohort["tp_contract_optin"],
                tp_actual_usage=cohort["tp_actual_usage"],
                tp_monthly_volume=cohort["tp_monthly_volume"],
                include_float=cohort["include_float"],
                include_float_std=cohort["include_float_std"],
                include_teampay=cohort["include_teampay"],
                include_upside=cohort["include_upside"],
                include_upside_std=cohort["include_upside_std"],
                upside_total_customers=cohort["upside_total_customers"],
                vas_recommended_only=cohort["vas_recommended_only"],
                vas_tam_scenario=cohort.get("vas_tam_scenario", "base"),
            )

        balanced = build_balanced_scenario(
            revenue_opt, margin_opt, standard, volumes=standard.per_deal_volumes,
            sqls_per_quarter=cohort["sqls_per_quarter"],
            quarterly_growth=cohort["quarterly_growth"],
            tp_contract_optin=cohort["tp_contract_optin"],
            tp_actual_usage=cohort["tp_actual_usage"],
            tp_monthly_volume=cohort["tp_monthly_volume"],
            include_float=cohort["include_float"],
            include_teampay=cohort["include_teampay"],
            include_upside=cohort["include_upside"],
            upside_total_customers=cohort["upside_total_customers"],
            vas_recommended_only=cohort["vas_recommended_only"],
            vas_tam_scenario=cohort.get("vas_tam_scenario", "base"),
            min_margin_pct_increase=0.0,
        )

        st.session_state["standard"] = standard
        st.session_state["revenue_opt"] = revenue_opt
        st.session_state["margin_opt"] = margin_opt
        st.session_state["balanced"] = balanced
        st.session_state["solver_msg"] = solver_msg
        st.session_state["cohort_inputs"] = cohort

    if "standard" not in st.session_state:
        return

    standard = st.session_state["standard"]
    revenue_opt = st.session_state["revenue_opt"]
    margin_opt = st.session_state["margin_opt"]
    balanced = st.session_state.get("balanced")
    solver_msg = st.session_state["solver_msg"]

    _BOX_GREEN = (
        '<div style="padding:12px 16px;background:#e8fde8;border-left:4px solid #1B8A4E;'
        'border-radius:4px;margin-bottom:8px;color:#1B8A4E;font-size:0.95rem;">'
    )
    _BOX_BLUE = (
        '<div style="padding:12px 16px;background:#e8f4fd;border-left:4px solid #1B6AC9;'
        'border-radius:4px;margin-bottom:8px;color:#003B91;font-size:0.95rem;">'
    )

    if solver_msg:
        st.markdown(f'{_BOX_BLUE}{solver_msg}</div>', unsafe_allow_html=True)

    rev_changes = _format_changes(revenue_opt)
    margin_changes = _format_changes(margin_opt)
    bal_changes = _format_changes(balanced) if balanced else None

    if rev_changes:
        st.markdown(
            f'{_BOX_GREEN}<b>Revenue Optimized adjustments:</b> {rev_changes}</div>',
            unsafe_allow_html=True,
        )
    if margin_changes:
        _BOX_ORANGE = (
            '<div style="padding:12px 16px;background:#fef3e8;border-left:4px solid #E67E22;'
            'border-radius:4px;margin-bottom:8px;color:#a85d1a;font-size:0.95rem;">'
        )
        st.markdown(
            f'{_BOX_ORANGE}<b>$ Margin Optimized adjustments:</b> {margin_changes}</div>',
            unsafe_allow_html=True,
        )
    if bal_changes:
        _BOX_TEAL = (
            '<div style="padding:12px 16px;background:#e8f8f5;border-left:4px solid #17A2B8;'
            'border-radius:4px;margin-bottom:8px;color:#117a8b;font-size:0.95rem;">'
        )
        st.markdown(
            f'{_BOX_TEAL}<b>Balanced adjustments:</b> {bal_changes}</div>',
            unsafe_allow_html=True,
        )

    st.divider()
    render_funnel_comparison(standard, revenue_opt, margin_opt, ai=balanced)

    st.divider()
    render_volume_forecast(standard, revenue_opt, margin_opt)

    st.divider()
    render_pricing_comparison(standard, revenue_opt, margin_opt, ai=balanced)

    st.divider()
    render_cost_to_collect_ar(standard, revenue_opt, margin_opt, ai=balanced)

    st.divider()
    render_insight_callouts(standard, revenue_opt, margin_opt)

    st.divider()
    render_summary_metrics(standard, revenue_opt, margin_opt, ai=balanced)

    st.divider()
    render_break_even_chart(standard, revenue_opt, margin_opt, ai=balanced)

    render_cumulative_revenue_chart(standard, revenue_opt, margin_opt, ai=balanced)

    st.divider()
    render_revenue_composition(standard, revenue_opt, margin_opt, ai=balanced)

    st.divider()
    render_annualized_impact(standard, revenue_opt, margin_opt, ai=balanced)

    has_vas = any(
        s.upside_detail for s in [standard, revenue_opt, margin_opt, balanced]
        if s is not None
    )
    if has_vas:
        st.divider()
        render_upside_breakdown(standard, revenue_opt, margin_opt, ai=balanced)

    st.divider()
    render_exit_arr(standard, revenue_opt, margin_opt, ai=balanced)

    # ── SaaS Deficit & VAS Offset Analysis ────────────────────────
    st.divider()
    _render_saas_vas_tradeoff(standard, revenue_opt, margin_opt, balanced)


def _render_saas_vas_tradeoff(standard, revenue_opt, margin_opt, balanced=None):
    """Show SaaS deficit for each scenario vs Standard and how VAS offsets it."""
    import plotly.graph_objects as go
    from models.upside_model import compute_upside_per_deal

    st.subheader("SaaS Deficit & VAS Offset Analysis", help=(
        "Shows how much SaaS revenue each pricing scenario sacrifices compared to "
        "Standard pricing over 3 years, and whether Value-Added Services (VAS) fees "
        "can offset that deficit.\n\n"
        "Red bars = SaaS revenue lost vs Standard (the 'cost' of discounting more aggressively).\n"
        "Green bars = VAS revenue captured at the selected rate, stacking up from the deficit.\n"
        "If the green bar crosses the $0 line, VAS more than covers the SaaS sacrifice.\n\n"
        "The 'Breakeven' percentage tells you the minimum VAS capture needed to fully "
        "offset each scenario's SaaS deficit."
    ))

    ci = st.session_state.get("cohort_inputs", {})
    upside_customers = ci.get("upside_total_customers", cfg.UPSIDE_TOTAL_CUSTOMERS)
    vas_tam = ci.get("vas_tam_scenario", "base")

    ctrl_left, ctrl_right = st.columns([1, 3])
    with ctrl_left:
        vas_scope = st.radio(
            "VAS Items",
            ["All", "Recommended"],
            horizontal=True,
            key="tradeoff_vas_scope",
        )
    with ctrl_right:
        vas_pct = st.slider(
            "VAS Capture Rate",
            min_value=0, max_value=100, value=100, step=5,
            format="%d%%",
            key="tradeoff_vas_capture",
            help="What percentage of the selected VAS items' revenue is captured.",
        )

    tradeoff_rec_only = vas_scope == "Recommended"

    def _compute_vas_3yr(scenario):
        """Compute 3-year VAS potential for a scenario using the selected scope."""
        total = 0.0
        for y in [1, 2, 3]:
            up = compute_upside_per_deal(
                scenario.per_deal_volumes[y], upside_customers,
                recommended_only=tradeoff_rec_only, tam_scenario=vas_tam,
            )
            active = scenario.cohort_yearly[y].deals
            total += up.total * active
        return total

    std_saas = sum(standard.cohort_yearly[y].saas_revenue for y in [1, 2, 3])

    scenario_list = [
        ("Revenue Optimized", revenue_opt, "#2ECC71"),
        ("$ Margin Optimized", margin_opt, "#E67E22"),
    ]
    if balanced is not None:
        scenario_list.append(("Balanced", balanced, "#17A2B8"))

    results = []
    for label, s, color in scenario_list:
        saas = sum(s.cohort_yearly[y].saas_revenue for y in [1, 2, 3])
        deficit = std_saas - saas
        vas_full = _compute_vas_3yr(s)
        vas_adj = vas_full * vas_pct / 100
        net = vas_adj - deficit
        breakeven = (deficit / vas_full * 100) if vas_full > 0 and deficit > 0 else 0
        orig_vas = sum(s.cohort_yearly[y].upside_revenue for y in [1, 2, 3])
        base_rev = s.three_year_revenue - orig_vas
        adj_rev = base_rev + vas_adj
        total_cost = s.three_year_revenue - s.three_year_margin
        adj_margin = adj_rev - total_cost
        adj_margin_pct = adj_margin / adj_rev if adj_rev > 0 else 0
        results.append({
            "label": label, "color": color,
            "deficit": deficit, "vas_full": vas_full, "vas_adj": vas_adj,
            "net": net, "breakeven": breakeven,
            "three_year_rev": adj_rev,
            "margin_pct": adj_margin_pct,
        })

    # ── Scenario cards ────────────────────────────────────────────
    cols = st.columns(len(results))
    for col, r in zip(cols, results):
        with col:
            deficit_str = f"${abs(r['deficit']):,.0f}"
            vas_str = f"${r['vas_adj']:,.0f}"
            if r["deficit"] > 0:
                be_str = f"{r['breakeven']:.0f}%"
                deficit_sign = "−"
                deficit_clr = "#ff2b2b"
            else:
                be_str = "No deficit"
                deficit_sign = "+"
                deficit_clr = "#09ab3b"

            net_clr = "#09ab3b" if r["net"] >= 0 else "#ff2b2b"
            net_sign = "+" if r["net"] >= 0 else "−"
            net_label = "Surplus" if r["net"] >= 0 else "Gap"

            st.markdown(
                f'<div style="text-align:center;padding:14px 12px;background:#f8f9fa;'
                f'border-radius:8px;border:2px solid {r["color"]};">'
                f'<div style="font-size:0.95rem;font-weight:700;color:{r["color"]};">{r["label"]}</div>'
                f'<div style="margin-top:8px;font-size:0.78rem;color:#808495;">SaaS Deficit vs Standard</div>'
                f'<div style="font-size:1.4rem;font-weight:700;color:{deficit_clr};">'
                f'{deficit_sign}{deficit_str}</div>'
                f'<div style="margin-top:6px;font-size:0.78rem;color:#808495;">'
                f'VAS Revenue ({vas_pct}%)</div>'
                f'<div style="font-size:1.4rem;font-weight:700;color:#09ab3b;">+{vas_str}</div>'
                f'<div style="margin-top:8px;border-top:1px solid #e0e0e0;padding-top:8px;">'
                f'<div style="font-size:0.78rem;color:#808495;">Net {net_label}</div>'
                f'<div style="font-size:1.3rem;font-weight:700;color:{net_clr};">'
                f'{net_sign}${abs(r["net"]):,.0f}</div>'
                f'<div style="margin-top:4px;font-size:0.75rem;color:#808495;">'
                f'Breakeven: <b>{be_str}</b></div>'
                f'<div style="margin-top:8px;border-top:1px solid #e0e0e0;padding-top:8px;">'
                f'<div style="font-size:0.78rem;color:#808495;">3-Yr Revenue</div>'
                f'<div style="font-size:1.1rem;font-weight:700;color:#333;">'
                f'${r["three_year_rev"]:,.0f}</div>'
                f'<div style="margin-top:4px;font-size:0.78rem;color:#808495;">Margin %</div>'
                f'<div style="font-size:1.1rem;font-weight:700;color:#333;">'
                f'{r["margin_pct"]:.1%}</div></div></div></div>',
                unsafe_allow_html=True,
            )

    # ── Grouped bar chart ─────────────────────────────────────────
    st.markdown("")
    labels = [r["label"] for r in results]
    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=labels,
        y=[abs(r["deficit"]) if r["deficit"] > 0 else 0 for r in results],
        name="SaaS Deficit vs Standard",
        marker_color="rgba(231, 76, 60, 0.85)",
        text=[f"−${r['deficit']:,.0f}" if r["deficit"] > 0 else "" for r in results],
        textposition="outside",
        textfont=dict(size=12, color="#c0392b"),
    ))

    fig.add_trace(go.Bar(
        x=labels,
        y=[abs(r["deficit"]) if r["deficit"] <= 0 else 0 for r in results],
        name="SaaS Surplus vs Standard",
        marker_color="rgba(46, 204, 113, 0.85)",
        text=[f"+${abs(r['deficit']):,.0f}" if r["deficit"] <= 0 else "" for r in results],
        textposition="outside",
        textfont=dict(size=12, color="#1a8a4a"),
        showlegend=False,
    ))

    fig.add_trace(go.Bar(
        x=labels,
        y=[r["vas_adj"] for r in results],
        name=f"VAS Revenue ({vas_pct}%)",
        marker_color="rgba(27, 106, 201, 0.85)",
        text=[f"+${r['vas_adj']:,.0f}" for r in results],
        textposition="outside",
        textfont=dict(size=12, color="#1B6AC9"),
    ))

    for i, r in enumerate(results):
        net_clr = "#1a8a4a" if r["net"] >= 0 else "#c0392b"
        prefix = "+" if r["net"] >= 0 else ""
        bar_max = max(abs(r["deficit"]), r["vas_adj"])
        fig.add_annotation(
            x=labels[i], y=bar_max,
            text=f"<b>Net: {prefix}${r['net']:,.0f}</b>",
            showarrow=False, yshift=28,
            font=dict(size=13, color=net_clr),
        )

    all_heights = [abs(r["deficit"]) for r in results] + [r["vas_adj"] for r in results]
    top = max(all_heights) if all_heights else 100_000
    padding = top * 0.25

    fig.update_layout(
        barmode="group",
        yaxis=dict(
            tickformat="$,.0f",
            title="3-Year Amount ($)",
            gridcolor="rgba(0,0,0,0.06)",
            range=[0, top + padding],
        ),
        xaxis=dict(
            tickvals=list(range(len(labels))),
            ticktext=[
                f'<span style="color:{r["color"]}">{r["label"]}</span>'
                for r in results
            ],
            tickfont=dict(size=14, weight="bold"),
        ),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
                    font=dict(size=12)),
        margin=dict(t=70, b=40),
        height=480,
        plot_bgcolor="white",
    )
    st.plotly_chart(fig, use_container_width=True)

    # ── VAS Item Breakdown (translate % into concrete items) ──────
    import pandas as pd

    rec_set = {i["name"] for i in cfg.VAS_ITEMS if i["recommended"]}
    scope_label = "Recommended" if tradeoff_rec_only else "All"
    item_count = sum(1 for i in cfg.VAS_ITEMS if not tradeoff_rec_only or i["recommended"])

    items_3yr: dict[str, float] = {}
    for y in [1, 2, 3]:
        up = compute_upside_per_deal(
            standard.per_deal_volumes[y], upside_customers,
            recommended_only=tradeoff_rec_only, tam_scenario=vas_tam,
        )
        avg_active = sum(s.cohort_yearly[y].deals for _, s, _ in scenario_list) / len(scenario_list)
        for name, val in up.items.items():
            items_3yr[name] = items_3yr.get(name, 0) + val * avg_active

    sorted_items = sorted(items_3yr.items(), key=lambda x: x[1], reverse=True)
    total_vas_dollar = sum(v for _, v in sorted_items)

    target_dollar = total_vas_dollar * vas_pct / 100
    cumulative = 0.0
    items_needed = 0
    for name, val in sorted_items:
        cumulative += val
        items_needed += 1
        if cumulative >= target_dollar:
            break

    # Breakeven items per scenario
    be_summaries = []
    for r in results:
        if r["deficit"] <= 0 or r["vas_full"] <= 0:
            be_summaries.append(f'**{r["label"]}**: No SaaS deficit — VAS is purely additive.')
            continue
        be_target = r["deficit"]
        be_cum = 0.0
        be_count = 0
        be_names: list[str] = []
        for name, val in sorted_items:
            ratio = r["vas_full"] / total_vas_dollar if total_vas_dollar > 0 else 1.0
            be_cum += val * ratio
            be_count += 1
            be_names.append(name)
            if be_cum >= be_target:
                break
        names_str = ", ".join(be_names[:5])
        if be_count > 5:
            names_str += f", +{be_count - 5} more"
        be_summaries.append(
            f'**{r["label"]}** ({r["breakeven"]:.0f}%): '
            f'Top {be_count} items — {names_str}'
        )

    st.markdown("---")

    st.markdown("**Breakeven by scenario:**")
    for s in be_summaries:
        st.markdown(f"- {s}")

    with st.expander(f"VAS Item Ranking — {scope_label} ({item_count} items)"):
        per_deal_3yr: dict[str, float] = {}
        for y in [1, 2, 3]:
            up = compute_upside_per_deal(
                standard.per_deal_volumes[y], upside_customers,
                recommended_only=tradeoff_rec_only, tam_scenario=vas_tam,
            )
            for name, val in up.items.items():
                per_deal_3yr[name] = per_deal_3yr.get(name, 0) + val

        sorted_pd = sorted(per_deal_3yr.items(), key=lambda x: x[1], reverse=True)
        total_pd = sum(v for _, v in sorted_pd)

        rows = []
        cumulative = 0.0
        for name, val in sorted_pd:
            cumulative += val
            cum_pct = cumulative / total_pd * 100 if total_pd > 0 else 0
            is_rec = name in rec_set
            rows.append({
                "Rank": len(rows) + 1,
                "VAS Item": name,
                "Rec.": "✓" if is_rec else "",
                "Per-Deal 3-Yr": f"${val:,.0f}",
                "Cumulative %": f"{cum_pct:.0f}%",
            })
        df = pd.DataFrame(rows)
        st.dataframe(df, hide_index=True, use_container_width=True)


if __name__ == "__main__":
    main()
