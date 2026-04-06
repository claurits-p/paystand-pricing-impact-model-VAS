"""
Win rate model — asymmetric impacts with convex SaaS curve and 3-component ACH.

Win rate is driven by the *effective Y1 SaaS price* the customer sees,
plus CC, ACH (3-component), and impl fee levers.  Both SaaS strategies
(discount-remove and flat-monthly) map onto the same win-rate curve
because the customer only sees the Year 1 price at signing.

Retention is anchored to real renewal data:
  - 0% price increase → 5% annual churn (95% retention)
  - 25% price increase → 10% annual churn (90% retention)
  - Scales linearly with Y2 price increase

Each optimizer runs dual_annealing in BOTH modes and picks the winner.
Strategy A now has an 8th lever: removal_pct (how much of Y1 discount to
remove at Y2 renewal, 0-50%).
"""
from __future__ import annotations
from scipy.optimize import dual_annealing

import config as cfg
from models.revenue_model import PricingScenario


# ── Precompute standard reference values ─────────────────────

def _blended_cc(base_rate: float, amex_rate: float) -> float:
    return (
        cfg.CC_FIXED_COMPONENT
        + base_rate * cfg.CC_BASE_VOLUME_SHARE
        + amex_rate * cfg.CC_AMEX_VOLUME_SHARE
    )

_STD = cfg.STANDARD_PRICING
_STD_CC = _blended_cc(_STD["cc_base_rate"], _STD["cc_amex_rate"])
_BEST_CC = _blended_cc(
    cfg.LEVER_BOUNDS["cc_base_rate"]["min"],
    cfg.LEVER_BOUNDS["cc_amex_rate"]["min"],
)
_WORST_CC = _blended_cc(
    cfg.LEVER_BOUNDS["cc_base_rate"]["max"],
    cfg.LEVER_BOUNDS["cc_amex_rate"]["max"],
)

_lb = cfg.LEVER_BOUNDS
_IMPACTS = cfg.LEVER_IMPACT

_STD_Y1_SAAS = cfg.STD_EFFECTIVE_Y1_SAAS
_BEST_Y1_SAAS = cfg.SAAS_FLAT_MONTHLY_BOUNDS["min"] * 12
_WORST_Y1_SAAS = cfg.SAAS_ARR_DEFAULT

_STD_ACCEL = _STD["ach_accel_pct"]
_STD_BPS = _STD["ach_accel_bps"]
_MAX_BPS = _lb["ach_accel_bps"]["max"]
_MIN_ACCEL = _lb["ach_accel_pct"]["min"]
_MAX_FEE = _lb["ach_fixed_fee"]["max"]


# ── Core: asymmetric impact with optional convex curve ───────

def _asymmetric_impact(
    value: float, standard: float, best: float, worst: float,
    up_impact: float, down_impact: float,
    lower_is_better: bool = True,
    power: float = 1.0,
) -> float:
    if lower_is_better:
        if value <= standard:
            denom = standard - best
            if denom == 0:
                return 0.0
            frac = min(1.0, (standard - value) / denom)
            return up_impact * (frac ** power)
        else:
            denom = worst - standard
            if denom == 0:
                return 0.0
            frac = min(1.0, (value - standard) / denom)
            return -down_impact * (frac ** power)
    else:
        if value >= standard:
            denom = best - standard
            if denom == 0:
                return 0.0
            frac = min(1.0, (value - standard) / denom)
            return up_impact * (frac ** power)
        else:
            denom = standard - worst
            if denom == 0:
                return 0.0
            frac = min(1.0, (standard - value) / denom)
            return -down_impact * (frac ** power)


# ── 3-Component ACH win rate model ───────────────────────────

def _ach_3component_impact(pricing: PricingScenario) -> float:
    bps_range = _MAX_BPS - _STD_BPS
    bps_over = max(0.0, pricing.ach_accel_bps - _STD_BPS)
    bps_severity = pricing.ach_accel_pct * (bps_over / bps_range if bps_range > 0 else 0.0)
    bps_penalty = -cfg.ACH_BPS_PENALTY_MAX * bps_severity

    accel_range = _STD_ACCEL - _MIN_ACCEL
    accel_reduction = max(0.0, _STD_ACCEL - pricing.ach_accel_pct)
    accel_benefit = cfg.ACH_ACCEL_REDUCTION_MAX * (accel_reduction / accel_range if accel_range > 0 else 0.0)

    fee_threshold = cfg.ACH_FEE_NEUTRAL_THRESHOLD
    fee_range = _MAX_FEE - fee_threshold
    fee_over = max(0.0, pricing.ach_fixed_fee - fee_threshold)
    non_accel_pct = 1 - pricing.ach_accel_pct
    fee_penalty = -cfg.ACH_FEE_PENALTY_MAX * (fee_over / fee_range if fee_range > 0 else 0.0) * non_accel_pct

    std_non_accel = 1 - _STD_ACCEL
    non_accel_gain = max(0.0, non_accel_pct - std_non_accel)
    non_accel_max = 1 - _MIN_ACCEL - std_non_accel
    fee_bonus = cfg.ACH_FEE_PREFERENCE_MAX * (non_accel_gain / non_accel_max if non_accel_max > 0 else 0.0)

    return bps_penalty + accel_benefit + fee_penalty + fee_bonus


# ── Win rate function ────────────────────────────────────────

def win_rate(pricing: PricingScenario) -> float:
    y1_saas = pricing.effective_y1_saas
    saas_impact = _asymmetric_impact(
        y1_saas, _STD_Y1_SAAS, _BEST_Y1_SAAS, _WORST_Y1_SAAS,
        _IMPACTS["saas_y1_price"]["up"],
        _IMPACTS["saas_y1_price"]["down"],
        lower_is_better=True,
        power=cfg.SAAS_WR_POWER,
    )

    cc_blended = _blended_cc(pricing.cc_base_rate, pricing.cc_amex_rate)
    cc_impact = _asymmetric_impact(
        cc_blended, _STD_CC, _BEST_CC, _WORST_CC,
        _IMPACTS["cc_rate"]["up"],
        _IMPACTS["cc_rate"]["down"],
        lower_is_better=True,
    )

    ach_impact = _ach_3component_impact(pricing)

    impl_impact = _asymmetric_impact(
        pricing.impl_fee_discount_pct,
        _STD["impl_fee_discount_pct"],
        _lb["impl_fee_discount_pct"]["max"],
        _lb["impl_fee_discount_pct"]["min"],
        _IMPACTS["impl_discount"]["up"],
        _IMPACTS["impl_discount"]["down"],
        lower_is_better=False,
    )

    total = cfg.WIN_RATE_BASELINE + saas_impact + cc_impact + ach_impact + impl_impact
    return max(0.0, min(1.0, total))


# ── Retention model (anchored to real renewal data) ──────────

def compute_retention_factors(
    pricing: PricingScenario,
    growth: float,
) -> dict[int, float]:
    """Compute per-year average retention factors.

    Churn is driven by the Y2 price increase:
      0% increase → 5% annual churn (95% retention)
      25% increase → 10% annual churn (90% retention)
      Scales linearly, capped at 35%.

    Flat monthly: no price increase → base 5% annual churn.
    Growth offsets churn each quarter.
    """
    price_increase = pricing.y2_price_increase_pct

    if pricing.saas_strategy == "flat_monthly":
        annual_churn = cfg.FLAT_MONTHLY_ANNUAL_CHURN
    else:
        annual_churn = min(
            cfg.CHURN_ANNUAL_CAP,
            cfg.CHURN_BASE_ANNUAL + cfg.CHURN_PER_PCT_INCREASE * price_increase * 100,
        )

    quarterly_churn = 1 - (1 - annual_churn) ** 0.25

    survival = [1.0]
    for q in range(12):
        q_churn = max(quarterly_churn - growth, -0.10)
        next_surv = survival[-1] * (1 - q_churn)
        survival.append(max(0.0, next_surv))

    ret = {}
    for y in [1, 2, 3]:
        start = (y - 1) * 4
        ret[y] = sum(survival[start + i] for i in range(4)) / 4
    return ret


# ── Helper: build PricingScenario from optimizer vector ──────

def _vec_to_pricing_a(x, saas_arr_list: float, impl_fee_list: float) -> PricingScenario:
    """Strategy A: [saas_disc, cc_base, cc_amex, ach_pct, ach_bps, ach_fee, impl_disc, removal_pct]."""
    return PricingScenario(
        saas_arr_discount_pct=x[0],
        cc_base_rate=x[1],
        cc_amex_rate=x[2],
        ach_accel_pct=x[3],
        ach_accel_bps=x[4],
        ach_fixed_fee=x[5],
        impl_fee_discount_pct=x[6],
        hold_days_cc=2,
        saas_arr_list=saas_arr_list,
        impl_fee_list=impl_fee_list,
        saas_strategy="discount_remove",
        removal_pct=x[7],
    )


def _vec_to_pricing_b(x, saas_arr_list: float, impl_fee_list: float) -> PricingScenario:
    """Strategy B: [flat_monthly, cc_base, cc_amex, ach_pct, ach_bps, ach_fee, impl_disc]."""
    return PricingScenario(
        saas_arr_discount_pct=0.0,
        cc_base_rate=x[1],
        cc_amex_rate=x[2],
        ach_accel_pct=x[3],
        ach_accel_bps=x[4],
        ach_fixed_fee=x[5],
        impl_fee_discount_pct=x[6],
        hold_days_cc=2,
        saas_arr_list=saas_arr_list,
        impl_fee_list=impl_fee_list,
        saas_strategy="flat_monthly",
        saas_flat_monthly=x[0],
    )


def _get_bounds_a():
    lb = cfg.LEVER_BOUNDS
    return [
        (lb["saas_arr_discount_pct"]["min"], lb["saas_arr_discount_pct"]["max"]),
        (lb["cc_base_rate"]["min"], lb["cc_base_rate"]["max"]),
        (lb["cc_amex_rate"]["min"], lb["cc_amex_rate"]["max"]),
        (lb["ach_accel_pct"]["min"], lb["ach_accel_pct"]["max"]),
        (lb["ach_accel_bps"]["min"], lb["ach_accel_bps"]["max"]),
        (lb["ach_fixed_fee"]["min"], lb["ach_fixed_fee"]["max"]),
        (lb["impl_fee_discount_pct"]["min"], lb["impl_fee_discount_pct"]["max"]),
        (lb["removal_pct"]["min"], lb["removal_pct"]["max"]),
    ]


def _get_bounds_b():
    fb = cfg.SAAS_FLAT_MONTHLY_BOUNDS
    lb = cfg.LEVER_BOUNDS
    return [
        (fb["min"], fb["max"]),
        (lb["cc_base_rate"]["min"], lb["cc_base_rate"]["max"]),
        (lb["cc_amex_rate"]["min"], lb["cc_amex_rate"]["max"]),
        (lb["ach_accel_pct"]["min"], lb["ach_accel_pct"]["max"]),
        (lb["ach_accel_bps"]["min"], lb["ach_accel_bps"]["max"]),
        (lb["ach_fixed_fee"]["min"], lb["ach_fixed_fee"]["max"]),
        (lb["impl_fee_discount_pct"]["min"], lb["impl_fee_discount_pct"]["max"]),
    ]


def _record_changes(pricing_orig, pricing_new):
    changes = {}
    fields = [
        ("saas_arr_discount_pct", 1e-4, "rate"),
        ("cc_base_rate", 1e-5, "rate"),
        ("cc_amex_rate", 1e-5, "rate"),
        ("ach_accel_pct", 0.01, "rate"),
        ("ach_accel_bps", 1e-5, "rate"),
        ("ach_fixed_fee", 0.01, "fee"),
        ("impl_fee_discount_pct", 1e-4, "rate"),
        ("removal_pct", 0.01, "rate"),
    ]
    for field, tol, _ in fields:
        old = getattr(pricing_orig, field)
        new = getattr(pricing_new, field)
        if abs(new - old) > tol:
            changes[field] = (old, new)
    if pricing_new.saas_strategy == "flat_monthly":
        changes["saas_strategy"] = ("discount_remove", "flat_monthly")
        changes["saas_flat_monthly"] = (0, pricing_new.saas_flat_monthly)
    return changes


# ── Dual-mode optimizer runner ───────────────────────────────

def _run_dual_mode(objective_fn, saas_list, impl_list, growth, seed=42):
    def _obj_a(x):
        p = _vec_to_pricing_a(x, saas_list, impl_list)
        return objective_fn(p, growth)

    def _obj_b(x):
        p = _vec_to_pricing_b(x, saas_list, impl_list)
        return objective_fn(p, growth)

    bounds_a = _get_bounds_a()
    bounds_b = _get_bounds_b()

    res_a = dual_annealing(_obj_a, bounds_a, seed=seed, maxiter=1000)
    res_b = dual_annealing(_obj_b, bounds_b, seed=seed, maxiter=1000)

    if res_a.fun <= res_b.fun:
        best = _vec_to_pricing_a(res_a.x, saas_list, impl_list)
        nfev = res_a.nfev + res_b.nfev
    else:
        best = _vec_to_pricing_b(res_b.x, saas_list, impl_list)
        nfev = res_a.nfev + res_b.nfev

    return best, nfev


# ── Revenue Optimizer ────────────────────────────────────────

def optimize_revenue(
    pricing: PricingScenario,
    deals_to_pricing: int,
    volumes: dict,
    quarterly_growth: float = 0.02,
    include_float: bool = True,
) -> tuple[PricingScenario, dict, float]:
    from models.revenue_model import compute_three_year_financials

    saas_list = pricing.saas_arr_list
    impl_list = pricing.impl_fee_list

    def _objective(p, g):
        wp = win_rate(p)
        if wp <= 0:
            return 0.0
        deals = deals_to_pricing * wp
        ret = compute_retention_factors(p, g)
        yearly = compute_three_year_financials(volumes, p, include_float=include_float)
        total_rev = sum(yearly[y].total_revenue * deals * ret[y] for y in [1, 2, 3])
        return -total_rev

    adjusted, _ = _run_dual_mode(_objective, saas_list, impl_list, quarterly_growth)
    changes = _record_changes(pricing, adjusted)
    achieved = win_rate(adjusted)
    return adjusted, changes, achieved


# ── Margin Optimizer ─────────────────────────────────────────

def optimize_margin_pct(
    pricing: PricingScenario,
    deals_to_pricing: int,
    volumes: dict,
    quarterly_growth: float = 0.02,
    include_float: bool = True,
) -> tuple[PricingScenario, dict, float]:
    from models.revenue_model import compute_three_year_financials

    saas_list = pricing.saas_arr_list
    impl_list = pricing.impl_fee_list

    def _objective(p, g):
        wp = win_rate(p)
        if wp <= 0:
            return 0.0
        deals = deals_to_pricing * wp
        ret = compute_retention_factors(p, g)
        yearly = compute_three_year_financials(volumes, p, include_float=include_float)
        total_margin = sum(
            (yearly[y].total_revenue - yearly[y].total_cost) * deals * ret[y]
            for y in [1, 2, 3]
        )
        return -total_margin

    adjusted, _ = _run_dual_mode(_objective, saas_list, impl_list, quarterly_growth)
    changes = _record_changes(pricing, adjusted)
    achieved = win_rate(adjusted)
    return adjusted, changes, achieved
