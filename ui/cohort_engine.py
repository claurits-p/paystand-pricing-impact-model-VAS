"""
Cohort-level calculation engine.

Takes per-deal financials from the revenue model, scales them by deal
count, and produces side-by-side Standard vs two optimized scenarios.

Two optimizers (all fully unconstrained, dual-mode Strategy A+B):
  - Revenue Optimized: max total 3yr cohort revenue
  - $ Margin Optimized: max total 3yr cohort margin dollars
"""
from __future__ import annotations
from dataclasses import dataclass, field

from models.revenue_model import (
    PricingScenario,
    YearlyRevenue,
    compute_three_year_financials,
)
from models.volume_forecast import VolumeForecastYear, forecast_volume_y1_y3
from models.win_probability import (
    win_rate as compute_win_rate,
    optimize_revenue,
    optimize_margin_pct,
    compute_retention_factors,
)
from models.funnel_model import FunnelResult, compute_funnel, compute_standard_funnel
from models.upside_model import UpsideYear, compute_upside_per_deal
import config as cfg


@dataclass
class CohortYearMetrics:
    year: int
    deals: int
    saas_revenue: float
    impl_fee_revenue: float
    cc_revenue: float
    ach_revenue: float
    bank_revenue: float
    float_income: float
    teampay_saas_revenue: float
    teampay_processing_revenue: float
    teampay_cost: float
    total_revenue: float
    total_cost: float
    margin: float
    margin_pct: float
    take_rate: float
    upside_revenue: float = 0.0


@dataclass
class CohortScenario:
    name: str
    deals_won: int
    win_rate: float
    per_deal_pricing: PricingScenario
    per_deal_yearly: dict[int, YearlyRevenue]
    per_deal_volumes: dict[int, VolumeForecastYear]
    cohort_yearly: dict[int, CohortYearMetrics]
    three_year_revenue: float
    three_year_margin: float
    three_year_margin_pct: float
    three_year_take_rate: float
    lever_changes: dict | None = None
    funnel: FunnelResult | None = None
    upside_detail: dict | None = None


def _simple_retention_factor(year: int, quarterly_churn: float = 0.02) -> float:
    """Fallback retention factor (flat quarterly churn)."""
    r = 1 - quarterly_churn
    quarters_start = (year - 1) * 4
    quarters_end = year * 4
    return sum(r ** q for q in range(quarters_start, quarters_end)) / 4




def _compute_teampay_year(
    deals_won: int,
    year: int,
    retention: float,
    tp_optin: float,
    tp_usage: float,
    proc_growth: float = 1.0,
    monthly_volume: float = 50_000,
    free_y1_saas: bool = True,
) -> tuple[float, float, float]:
    active_tp = deals_won * tp_optin * tp_usage * retention

    annual_proc_vol = monthly_volume * 12
    vol_factor = 0.50 if (year == 1 and free_y1_saas) else 1.0
    tp_proc_rev = active_tp * annual_proc_vol * cfg.TEAMPAY_PROCESSING_RATE * vol_factor * proc_growth
    tp_proc_cost = tp_proc_rev * (1 - cfg.TEAMPAY_PROCESSING_MARGIN)

    if year == 1 and free_y1_saas:
        tp_saas_rev = 0.0
        tp_saas_cost = 0.0
    else:
        tp_saas_rev = active_tp * cfg.TEAMPAY_SAAS_ANNUAL
        tp_saas_cost = tp_saas_rev * (1 - cfg.TEAMPAY_SAAS_MARGIN)

    return tp_saas_rev, tp_proc_rev, tp_proc_cost + tp_saas_cost


def _scale_yearly(
    yearly: dict[int, YearlyRevenue], deals: int,
    ret_factors: dict[int, float] | None = None,
    quarterly_churn: float = 0.02,
    tp_optin: float = 0.0,
    tp_usage: float = 0.0,
    tp_monthly_vol: float = 50_000,
    tp_free_y1_saas: bool = True,
    include_upside: bool = False,
    upside_total_customers: int = cfg.UPSIDE_TOTAL_CUSTOMERS,
    vas_recommended_only: bool = False,
    vas_tam_scenario: str = "base",
    per_deal_volumes: dict | None = None,
) -> tuple[dict[int, CohortYearMetrics], dict | None]:
    if ret_factors is None:
        ret_factors = {y: _simple_retention_factor(y, quarterly_churn) for y in [1, 2, 3]}

    tp_ret = {1: ret_factors[1], 2: ret_factors[2], 3: ret_factors[3]}

    result = {}
    upside_detail: dict | None = {} if include_upside else None
    for y, yr in yearly.items():
        retention = ret_factors[y]
        active = deals * retention
        base_rev = yr.total_revenue * active
        base_cost = yr.total_cost * active

        tp_saas, tp_proc, tp_cost = _compute_teampay_year(
            deals, y, tp_ret[y], tp_optin, tp_usage, 1.0,
            monthly_volume=tp_monthly_vol, free_y1_saas=tp_free_y1_saas,
        )
        tp_rev = tp_saas + tp_proc

        cc_rev = yr.cc_revenue * active
        ach_rev = yr.ach_revenue * active
        bank_rev = yr.bank_network_revenue * active
        float_inc = yr.float_income * active

        up_rev = 0.0
        up_cost = 0.0
        if include_upside and per_deal_volumes is not None:
            up = compute_upside_per_deal(
                per_deal_volumes[y], upside_total_customers,
                recommended_only=vas_recommended_only,
                tam_scenario=vas_tam_scenario,
            )
            up_rev = up.total * active
            upside_detail[y] = {name: val * active for name, val in up.items.items()}
            if y == 1:
                up_cost = up.build_cost

        rev = base_rev + tp_rev + up_rev
        cost = base_cost + tp_cost + up_cost
        margin = rev - cost
        mpct = margin / rev if rev > 0 else 0
        vol = (yr.total_revenue / yr.take_rate * active) if yr.take_rate > 0 else 0
        tr = rev / vol if vol > 0 else 0
        result[y] = CohortYearMetrics(
            year=y,
            deals=int(round(active)),
            saas_revenue=yr.saas_revenue * active,
            impl_fee_revenue=yr.impl_fee_revenue * active,
            cc_revenue=cc_rev,
            ach_revenue=ach_rev,
            bank_revenue=bank_rev,
            float_income=float_inc,
            teampay_saas_revenue=tp_saas,
            teampay_processing_revenue=tp_proc,
            teampay_cost=tp_cost,
            total_revenue=rev,
            total_cost=cost,
            margin=margin,
            margin_pct=mpct,
            take_rate=tr,
            upside_revenue=up_rev,
        )
    return result, upside_detail


def _build_cohort_scenario(
    name: str,
    deals_won: int,
    wr: float,
    pricing: PricingScenario,
    per_deal_yearly: dict[int, YearlyRevenue],
    per_deal_volumes: dict[int, VolumeForecastYear],
    lever_changes: dict | None = None,
    ret_factors: dict[int, float] | None = None,
    quarterly_churn: float = 0.02,
    tp_optin: float = 0.0,
    tp_usage: float = 0.0,
    tp_monthly_vol: float = 50_000,
    tp_free_y1_saas: bool = True,
    include_upside: bool = False,
    upside_total_customers: int = cfg.UPSIDE_TOTAL_CUSTOMERS,
    vas_recommended_only: bool = False,
    vas_tam_scenario: str = "base",
) -> CohortScenario:
    cohort_yearly, upside_detail = _scale_yearly(
        per_deal_yearly, deals_won,
        ret_factors=ret_factors, quarterly_churn=quarterly_churn,
        tp_optin=tp_optin, tp_usage=tp_usage, tp_monthly_vol=tp_monthly_vol,
        tp_free_y1_saas=tp_free_y1_saas,
        include_upside=include_upside, upside_total_customers=upside_total_customers,
        vas_recommended_only=vas_recommended_only,
        vas_tam_scenario=vas_tam_scenario,
        per_deal_volumes=per_deal_volumes,
    )
    total_rev = sum(cy.total_revenue for cy in cohort_yearly.values())
    total_margin = sum(cy.margin for cy in cohort_yearly.values())
    total_vol = sum(
        cy.total_revenue / cy.take_rate
        for cy in cohort_yearly.values() if cy.take_rate > 0
    )
    scenario = CohortScenario(
        name=name,
        deals_won=deals_won,
        win_rate=wr,
        per_deal_pricing=pricing,
        per_deal_yearly=per_deal_yearly,
        per_deal_volumes=per_deal_volumes,
        cohort_yearly=cohort_yearly,
        three_year_revenue=total_rev,
        three_year_margin=total_margin,
        three_year_margin_pct=total_margin / total_rev if total_rev > 0 else 0,
        three_year_take_rate=total_rev / total_vol if total_vol > 0 else 0,
        lever_changes=lever_changes,
    )
    scenario.upside_detail = upside_detail
    return scenario


def run_cohort_comparison(
    sqls_per_quarter: int,
    current_win_rate: float,
    avg_saas_arr: float,
    avg_impl_fee: float,
    total_arr_won: float,
    standard_pricing_inputs: dict,
    quarterly_growth: float = 0.02,
    tp_contract_optin: float = 0.50,
    tp_actual_usage: float = 0.20,
    tp_monthly_volume: float = 50_000,
    include_float: bool = True,
    include_float_std: bool = True,
    include_teampay: bool = True,
    include_upside: bool = False,
    include_upside_std: bool = False,
    upside_total_customers: int = cfg.UPSIDE_TOTAL_CUSTOMERS,
    vas_recommended_only: bool = False,
    vas_tam_scenario: str = "base",
) -> tuple[CohortScenario, CohortScenario, CohortScenario, str]:
    """
    Run Standard + two optimizer scenarios with full funnel model.

    Starts from SQLs per quarter, applies historical conversion rates
    (SQL → SAL → ROI), then applies the win rate model at ROI → Win.
    The 59% baseline win rate = ROI → Win (not Neg → Win).

    Returns (standard, revenue_opt, margin_opt, solver_message).
    """
    # Standard funnel: hardcoded Q4 2025 rates (no model)
    std_funnel = compute_standard_funnel(sqls_per_quarter, current_win_rate)
    std_deals = std_funnel.deals_won
    deals_to_roi = std_funnel.deals_to_roi

    per_deal_arr = total_arr_won / std_deals if std_deals > 0 else 0.0
    volumes = forecast_volume_y1_y3(per_deal_arr)

    # --- Standard scenario (always Strategy A) ---
    std_pricing = PricingScenario(
        saas_arr_discount_pct=standard_pricing_inputs["saas_arr_discount_pct"],
        impl_fee_discount_pct=standard_pricing_inputs["impl_fee_discount_pct"],
        cc_base_rate=standard_pricing_inputs["cc_base_rate"],
        cc_amex_rate=standard_pricing_inputs["cc_amex_rate"],
        ach_accel_pct=standard_pricing_inputs["ach_accel_pct"],
        ach_accel_bps=standard_pricing_inputs["ach_accel_bps"],
        ach_fixed_fee=standard_pricing_inputs["ach_fixed_fee"],
        hold_days_cc=standard_pricing_inputs["hold_days_cc"],
        saas_arr_list=avg_saas_arr,
        impl_fee_list=avg_impl_fee,
        saas_strategy="discount_remove",
    )
    std_pricing.removal_pct = standard_pricing_inputs.get("removal_pct", 0.25)
    std_yearly = compute_three_year_financials(volumes, std_pricing, include_float=include_float_std)
    std_ret = compute_retention_factors(std_pricing, quarterly_growth)

    opt_tp_optin = tp_contract_optin if include_teampay else 0.0
    opt_tp_usage = tp_actual_usage if include_teampay else 0.0

    standard = _build_cohort_scenario(
        "Standard Pricing", std_deals, current_win_rate,
        std_pricing, std_yearly, volumes,
        ret_factors=std_ret,
        tp_optin=opt_tp_optin, tp_usage=opt_tp_usage,
        tp_monthly_vol=tp_monthly_volume,
        include_upside=include_upside_std, upside_total_customers=upside_total_customers,
        vas_recommended_only=vas_recommended_only, vas_tam_scenario=vas_tam_scenario,
    )
    standard.funnel = std_funnel

    # --- Revenue Optimized (dual mode) ---
    rev_pricing, rev_changes, rev_wp = optimize_revenue(
        std_pricing, deals_to_roi, volumes,
        quarterly_growth=quarterly_growth,
        include_float=include_float,
    )
    rev_yearly = compute_three_year_financials(volumes, rev_pricing, include_float=include_float)
    rev_funnel = compute_funnel(sqls_per_quarter, rev_wp, current_win_rate)
    rev_deals = rev_funnel.deals_won
    rev_ret = compute_retention_factors(rev_pricing, quarterly_growth)

    revenue_opt = _build_cohort_scenario(
        "Revenue Optimized", rev_deals, rev_wp,
        rev_pricing, rev_yearly, volumes, rev_changes,
        ret_factors=rev_ret,
        tp_optin=opt_tp_optin, tp_usage=opt_tp_usage,
        tp_monthly_vol=tp_monthly_volume,
        include_upside=include_upside, upside_total_customers=upside_total_customers,
        vas_recommended_only=vas_recommended_only, vas_tam_scenario=vas_tam_scenario,
    )
    revenue_opt.funnel = rev_funnel

    # --- Margin Optimized (dual mode) ---
    mar_pricing, mar_changes, mar_wp = optimize_margin_pct(
        std_pricing, deals_to_roi, volumes,
        quarterly_growth=quarterly_growth,
        include_float=include_float,
    )
    mar_yearly = compute_three_year_financials(volumes, mar_pricing, include_float=include_float)
    mar_funnel = compute_funnel(sqls_per_quarter, mar_wp, current_win_rate)
    mar_deals = mar_funnel.deals_won
    mar_ret = compute_retention_factors(mar_pricing, quarterly_growth)

    margin_opt = _build_cohort_scenario(
        "$ Margin Optimized", mar_deals, mar_wp,
        mar_pricing, mar_yearly, volumes, mar_changes,
        ret_factors=mar_ret,
        tp_optin=opt_tp_optin, tp_usage=opt_tp_usage,
        tp_monthly_vol=tp_monthly_volume,
        include_upside=include_upside, upside_total_customers=upside_total_customers,
        vas_recommended_only=vas_recommended_only, vas_tam_scenario=vas_tam_scenario,
    )
    margin_opt.funnel = mar_funnel

    strategy_notes = []
    for label, p in [("Revenue", rev_pricing), ("$ Margin", mar_pricing)]:
        if p.saas_strategy == "flat_monthly":
            strategy_notes.append(f"{label} chose Flat Monthly ${p.saas_flat_monthly:,.0f}/mo")
        else:
            strategy_notes.append(
                f"{label} chose Discount & Remove "
                f"({p.saas_arr_discount_pct:.0%} disc, "
                f"{p.removal_pct:.0%} removal @ {cfg.REMOVAL_ATTAINMENT:.0%} attain)"
            )

    solver_msg = "Dual-mode optimizers (Strategy A + B). " + " | ".join(strategy_notes)

    return standard, revenue_opt, margin_opt, solver_msg


def build_balanced_scenario(
    revenue_opt: CohortScenario,
    margin_opt: CohortScenario,
    standard: CohortScenario,
    volumes: dict,
    sqls_per_quarter: int,
    quarterly_growth: float = 0.02,
    tp_contract_optin: float = 0.50,
    tp_actual_usage: float = 0.20,
    tp_monthly_volume: float = 50_000,
    include_float: bool = True,
    include_teampay: bool = True,
    include_upside: bool = False,
    upside_total_customers: int = cfg.UPSIDE_TOTAL_CUSTOMERS,
    vas_recommended_only: bool = False,
    vas_tam_scenario: str = "base",
    min_margin_pct_increase: float = 0.02,
) -> CohortScenario:
    """Build a Balanced scenario via Pareto scan between Revenue Opt and $ Margin Opt.

    Scans 1,000 interpolated pricing points between the two optimizers,
    evaluates each through the full model pipeline, and selects the point
    that maximises 3-year margin dollars subject to:
      - 3-yr revenue  >= $ Margin Opt's 3-yr revenue
      - 3-yr margin % >= Revenue Opt's margin % + min_margin_pct_increase
    Falls back to the unconstrained max-margin-dollars point if no
    feasible solution exists.
    """
    rev_p = revenue_opt.per_deal_pricing
    mar_p = margin_opt.per_deal_pricing
    std_p = standard.per_deal_pricing
    opt_tp_optin = tp_contract_optin if include_teampay else 0.0
    opt_tp_usage = tp_actual_usage if include_teampay else 0.0

    # Determine SaaS strategy for interpolation
    if rev_p.saas_strategy == mar_p.saas_strategy:
        strategy = rev_p.saas_strategy
    else:
        strategy = "discount_remove"

    def _lerp(a, b, t):
        return a + t * (b - a)

    def _rev_lever(attr):
        """Get lever value from Rev Opt, converting flat_monthly to equivalent discount if needed."""
        if attr == "saas_arr_discount_pct" and rev_p.saas_strategy == "flat_monthly":
            return 0.76
        if attr == "removal_pct" and rev_p.saas_strategy == "flat_monthly":
            return 0.0
        return getattr(rev_p, attr)

    def _mar_lever(attr):
        if attr == "saas_arr_discount_pct" and mar_p.saas_strategy == "flat_monthly":
            return 0.76
        if attr == "removal_pct" and mar_p.saas_strategy == "flat_monthly":
            return 0.0
        return getattr(mar_p, attr)

    LEVER_FIELDS = [
        "saas_arr_discount_pct", "cc_base_rate", "cc_amex_rate",
        "ach_accel_pct", "ach_accel_bps", "ach_fixed_fee",
        "impl_fee_discount_pct", "removal_pct",
    ]
    rev_vals = {f: _rev_lever(f) for f in LEVER_FIELDS}
    mar_vals = {f: _mar_lever(f) for f in LEVER_FIELDS}

    if strategy == "flat_monthly":
        rev_flat = rev_p.saas_flat_monthly if rev_p.saas_strategy == "flat_monthly" else 800
        mar_flat = mar_p.saas_flat_monthly if mar_p.saas_strategy == "flat_monthly" else 800

    # Constraint floors
    rev_floor = margin_opt.three_year_revenue
    margin_pct_floor = max(0.55, revenue_opt.three_year_margin_pct + min_margin_pct_increase)

    # Pre-compute per-deal VAS for each year (independent of pricing)
    upside_per_year: dict[int, float] = {}
    upside_build_cost = 0.0
    if include_upside:
        for y in [1, 2, 3]:
            up = compute_upside_per_deal(
                volumes[y], upside_total_customers,
                recommended_only=vas_recommended_only, tam_scenario=vas_tam_scenario,
            )
            upside_per_year[y] = up.total
            if y == 1:
                upside_build_cost = up.build_cost

    N_STEPS = 1_000
    best_margin = -float("inf")
    best_t = 0.5
    best_constrained_margin = -float("inf")
    best_constrained_t = None

    for i in range(N_STEPS + 1):
        t = i / N_STEPS

        levers = {f: _lerp(rev_vals[f], mar_vals[f], t) for f in LEVER_FIELDS}

        if strategy == "flat_monthly":
            pricing = PricingScenario(
                saas_arr_discount_pct=0.0,
                cc_base_rate=levers["cc_base_rate"],
                cc_amex_rate=levers["cc_amex_rate"],
                ach_accel_pct=levers["ach_accel_pct"],
                ach_accel_bps=levers["ach_accel_bps"],
                ach_fixed_fee=levers["ach_fixed_fee"],
                impl_fee_discount_pct=levers["impl_fee_discount_pct"],
                hold_days_cc=2,
                saas_arr_list=std_p.saas_arr_list,
                impl_fee_list=std_p.impl_fee_list,
                saas_strategy="flat_monthly",
                saas_flat_monthly=_lerp(rev_flat, mar_flat, t),
                removal_pct=0.0,
            )
        else:
            pricing = PricingScenario(
                saas_arr_discount_pct=levers["saas_arr_discount_pct"],
                cc_base_rate=levers["cc_base_rate"],
                cc_amex_rate=levers["cc_amex_rate"],
                ach_accel_pct=levers["ach_accel_pct"],
                ach_accel_bps=levers["ach_accel_bps"],
                ach_fixed_fee=levers["ach_fixed_fee"],
                impl_fee_discount_pct=levers["impl_fee_discount_pct"],
                hold_days_cc=2,
                saas_arr_list=std_p.saas_arr_list,
                impl_fee_list=std_p.impl_fee_list,
                saas_strategy="discount_remove",
                removal_pct=levers["removal_pct"],
            )

        wp = compute_win_rate(pricing)
        ret = compute_retention_factors(pricing, quarterly_growth)
        yearly = compute_three_year_financials(volumes, pricing, include_float=include_float)
        funnel = compute_funnel(sqls_per_quarter, wp, standard.win_rate)
        deals = funnel.deals_won

        total_rev = 0.0
        total_cost = 0.0
        for y in [1, 2, 3]:
            active = deals * ret[y]
            total_rev += yearly[y].total_revenue * active
            total_cost += yearly[y].total_cost * active
            tp_saas, tp_proc, tp_cost = _compute_teampay_year(
                deals, y, ret[y], opt_tp_optin, opt_tp_usage, 1.0,
                monthly_volume=tp_monthly_volume,
            )
            total_rev += tp_saas + tp_proc
            total_cost += tp_cost
            if include_upside:
                total_rev += upside_per_year[y] * active
                if y == 1:
                    total_cost += upside_build_cost

        margin = total_rev - total_cost
        margin_pct = margin / total_rev if total_rev > 0 else 0

        if margin > best_margin:
            best_margin = margin
            best_t = t

        if total_rev >= rev_floor and margin_pct >= margin_pct_floor:
            if margin > best_constrained_margin:
                best_constrained_margin = margin
                best_constrained_t = t

    chosen_t = best_constrained_t if best_constrained_t is not None else best_t

    # Build the winning scenario with full detail
    levers = {f: _lerp(rev_vals[f], mar_vals[f], chosen_t) for f in LEVER_FIELDS}

    if strategy == "flat_monthly":
        bal_pricing = PricingScenario(
            saas_arr_discount_pct=0.0,
            cc_base_rate=levers["cc_base_rate"],
            cc_amex_rate=levers["cc_amex_rate"],
            ach_accel_pct=levers["ach_accel_pct"],
            ach_accel_bps=levers["ach_accel_bps"],
            ach_fixed_fee=levers["ach_fixed_fee"],
            impl_fee_discount_pct=levers["impl_fee_discount_pct"],
            hold_days_cc=2,
            saas_arr_list=std_p.saas_arr_list,
            impl_fee_list=std_p.impl_fee_list,
            saas_strategy="flat_monthly",
            saas_flat_monthly=_lerp(rev_flat, mar_flat, chosen_t),
            removal_pct=0.0,
        )
    else:
        bal_pricing = PricingScenario(
            saas_arr_discount_pct=levers["saas_arr_discount_pct"],
            cc_base_rate=levers["cc_base_rate"],
            cc_amex_rate=levers["cc_amex_rate"],
            ach_accel_pct=levers["ach_accel_pct"],
            ach_accel_bps=levers["ach_accel_bps"],
            ach_fixed_fee=levers["ach_fixed_fee"],
            impl_fee_discount_pct=levers["impl_fee_discount_pct"],
            hold_days_cc=2,
            saas_arr_list=std_p.saas_arr_list,
            impl_fee_list=std_p.impl_fee_list,
            saas_strategy="discount_remove",
            removal_pct=levers["removal_pct"],
        )

    bal_wp = compute_win_rate(bal_pricing)
    bal_ret = compute_retention_factors(bal_pricing, quarterly_growth)
    bal_yearly = compute_three_year_financials(volumes, bal_pricing, include_float=include_float)
    bal_funnel = compute_funnel(sqls_per_quarter, bal_wp, standard.win_rate)
    bal_deals = bal_funnel.deals_won

    bal_changes = {}
    for fld in LEVER_FIELDS:
        old = getattr(std_p, fld)
        new = getattr(bal_pricing, fld)
        if abs(new - old) > 1e-4:
            bal_changes[fld] = (old, new)
    if bal_pricing.saas_strategy != std_p.saas_strategy:
        bal_changes["saas_strategy"] = (std_p.saas_strategy, bal_pricing.saas_strategy)
        bal_changes["saas_flat_monthly"] = (0, bal_pricing.saas_flat_monthly)

    scenario = _build_cohort_scenario(
        "Balanced", bal_deals, bal_wp,
        bal_pricing, bal_yearly, volumes, bal_changes,
        ret_factors=bal_ret,
        tp_optin=opt_tp_optin, tp_usage=opt_tp_usage,
        tp_monthly_vol=tp_monthly_volume,
        include_upside=include_upside, upside_total_customers=upside_total_customers,
        vas_recommended_only=vas_recommended_only, vas_tam_scenario=vas_tam_scenario,
    )
    scenario.funnel = bal_funnel
    return scenario
