"""
Cohort-level input form for the pricing impact model.
"""
from __future__ import annotations
import streamlit as st
import config as cfg


def render_cohort_inputs() -> dict:
    """Render cohort inputs and return collected values."""

    st.header("Cohort Data")

    c1, c2, c3 = st.columns(3)
    with c1:
        cohort_name = st.text_input("Cohort Name", value="Q4 2025")
        sqls_per_quarter = st.number_input(
            "SQLs per Quarter", min_value=1, value=cfg.FUNNEL_SQLS_PER_QUARTER, step=25,
            help="Sales Qualified Leads per quarter. Model applies historical funnel "
                 "conversion rates to derive deals at each stage.",
        )
        current_win_rate = cfg.FUNNEL_Q4_ROI_TO_WIN

    with c2:
        avg_saas_arr = st.number_input(
            "Avg ARR / Deal (Pre-Discount)", min_value=0.0,
            value=30_476.0, step=1000.0, format="%.0f",
        )
        avg_impl_fee = st.number_input(
            "Avg Implementation Fee ($/deal)", min_value=0.0,
            value=5_599.0, step=500.0, format="%.0f",
        )

    with c3:
        total_arr_won = st.number_input(
            "Total ARR Won ($)", min_value=0.0,
            value=1_654_046.0, step=10_000.0, format="%.0f",
            help="Recurring ARR only (excludes implementation fees). "
                 "Used for volume forecast via historical Vol/MRR ratios.",
        )

    st.subheader("Churn & Growth")
    cg1, cg2, cg3 = st.columns([2, 1, 2])
    with cg1:
        st.markdown(
            f'<span style="font-size:0.875rem;">'
            f"Churn driven by Y2 price increase — {cfg.CHURN_BASE_ANNUAL:.0%} base "
            f"(+{cfg.CHURN_PER_PCT_INCREASE*100:.2f}pp per 1% increase, "
            f"cap {cfg.CHURN_ANNUAL_CAP:.0%}). Growth offsets churn."
            f'</span>',
            unsafe_allow_html=True,
        )
        quarterly_growth = st.number_input(
            "Quarterly Growth %",
            min_value=0.0, max_value=20.0, value=2.0, step=0.5,
            format="%.1f",
            help="Revenue growth per surviving customer each quarter. Offsets churn.",
        ) / 100

    st.subheader("Model Settings")
    ms1, ms2 = st.columns(2)
    with ms1:
        include_float = st.toggle("Include Float Revenue", value=False,
            help="Toggle float income on/off for optimized scenarios.")
        include_float_std = st.toggle("Float in Standard", value=False,
            help="Include float income in the Standard scenario.",
            disabled=not include_float)
    with ms2:
        include_upside = st.toggle("Include VAS Fees", value=True,
            help="Add value-added service fees across all scenarios.")
        include_upside_std = st.toggle("VAS Fees in Standard", value=True,
            help="Include VAS fees in the Standard scenario.",
            disabled=not include_upside)
        if include_upside:
            vas_recommended_only = st.toggle("Recommended Only", value=False,
                help="Show only the 10 recommended VAS fee items instead of all 25.")
            vas_tam_scenario = st.radio(
                "TAM Assumption",
                options=["min", "base", "max"],
                format_func=lambda x: {"min": "Conservative (Min)", "base": "Base", "max": "Aggressive (Max)"}[x],
                index=1,
                horizontal=True,
                help="Min/Max ranges from the AR Competitor Fee Matrix.",
            )
            upside_total_customers = st.number_input(
                "Total Active Customers",
                min_value=100, value=750, step=50,
                help="Used to convert portfolio-level TAM to per-deal rates.",
            )
        else:
            vas_recommended_only = False
            vas_tam_scenario = "base"
            upside_total_customers = 750
    if not include_float:
        include_float_std = False
    if not include_upside:
        include_upside_std = False

    st.subheader("Teampay Assumptions")
    include_teampay = st.toggle("Include Teampay", value=True,
        help="Toggle Teampay revenue on/off for all scenarios.")

    if include_teampay:
        tp1, tp2, tp3 = st.columns(3)
        with tp1:
            tp_contract_optin = st.slider(
                "Teampay Contract Opt-in %",
                min_value=0, max_value=100, value=80, step=5,
                format="%d%%",
                help="Percentage of deals that allow Teampay in their contract.",
            ) / 100
        with tp2:
            tp_actual_usage = st.slider(
                "Teampay Actual Usage %",
                min_value=0, max_value=100, value=45, step=5,
                format="%d%%",
                help="Of those who opt in, the percentage that actually use Teampay.",
            ) / 100
        with tp3:
            tp_monthly_volume = st.slider(
                "Teampay Card Volume ($/mo)",
                min_value=10_000, max_value=1_000_000, value=100_000, step=10_000,
                format="$%d",
                help="Average monthly card processing volume per Teampay deal.",
            )
    else:
        tp_contract_optin = 0.0
        tp_actual_usage = 0.0
        tp_monthly_volume = 0
        st.caption("Teampay excluded from all scenarios. Float revenue does not include Teampay.")

    return {
        "cohort_name": cohort_name,
        "sqls_per_quarter": sqls_per_quarter,
        "current_win_rate": current_win_rate,
        "avg_saas_arr": avg_saas_arr,
        "avg_impl_fee": avg_impl_fee,
        "total_arr_won": total_arr_won,
        "quarterly_growth": quarterly_growth,
        "tp_contract_optin": tp_contract_optin,
        "tp_actual_usage": tp_actual_usage,
        "tp_monthly_volume": tp_monthly_volume,
        "include_float": include_float,
        "include_float_std": include_float_std,
        "include_teampay": include_teampay,
        "include_upside": include_upside,
        "include_upside_std": include_upside_std,
        "upside_total_customers": upside_total_customers,
        "vas_recommended_only": vas_recommended_only,
        "vas_tam_scenario": vas_tam_scenario,
    }


def render_standard_pricing() -> dict:
    """Render inputs for standard (current) pricing baseline."""

    with st.expander("Standard Pricing (Current Baseline)", expanded=False):
        c1, c2, c3 = st.columns(3)
        with c1:
            saas_disc = st.slider(
                "SaaS ARR Discount %", 0, 100, 30, key="std_saas_disc",
            ) / 100
            impl_disc = st.slider(
                "Impl Fee Discount %", 0, 100, 0, key="std_impl_disc",
            ) / 100
        with c2:
            cc_rate = st.number_input(
                "CC Base Rate %", min_value=1.50, max_value=3.50,
                value=2.20, step=0.05, key="std_cc",
                help="Q4 avg non-AMEX base rate. Model adds 0.53% fixed component.",
            ) / 100
            amex_rate = st.number_input(
                "AMEX Rate %", min_value=2.50, max_value=4.0,
                value=3.21, step=0.05, key="std_amex",
                help="Q4 avg AMEX fee: 3.21%",
            ) / 100
        with c3:
            st.markdown("**ACH:** 0.10% (10 bps)")
            st.markdown("**Hold Days (CC/Bank/ACH):** 2/2/2")

    return {
        "saas_arr_discount_pct": saas_disc,
        "impl_fee_discount_pct": impl_disc,
        "cc_base_rate": cc_rate,
        "cc_amex_rate": amex_rate,
        "ach_accel_pct": 1.0,
        "ach_accel_bps": 0.0010,
        "ach_fixed_fee": 2.50,
        "hold_days_cc": 2,
        "removal_pct": 0.25,
    }
