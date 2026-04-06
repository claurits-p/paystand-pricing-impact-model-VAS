"""
Exhaustive grid-search optimizer with multi-objective balanced scoring.

Two-pass approach:
  1. Coarse sweep (~8k combos) to identify the best region
  2. Fine sweep around that region (~20k combos) to pinpoint the optimum

The "balanced" score normalizes revenue, margin %, and take rate
to [0, 1] across the feasible set, then averages them — finding
the combo that performs best across all three metrics simultaneously.
"""
from __future__ import annotations
import numpy as np
from itertools import product

import config as cfg
from models.revenue_model import PricingScenario, compute_three_year_financials
from models.win_probability import win_rate


def _retention_factor(year: int, q_churn: float) -> float:
    r = 1 - q_churn
    qs = (year - 1) * 4
    qe = year * 4
    return sum(r ** q for q in range(qs, qe)) / 4




def _eval_combo(combo, saas_list, impl_list, deals_to_pricing, volumes,
                quarterly_churn, include_float):
    """Evaluate a single pricing combo. Returns (total_rev, margin_pct, take_rate, win_rate) or None."""
    saas_d, cc_b, cc_a, ach_pct, ach_bps, ach_fee, impl_d = combo
    p = PricingScenario(
        saas_arr_discount_pct=float(saas_d),
        cc_base_rate=float(cc_b),
        cc_amex_rate=float(cc_a),
        ach_accel_pct=float(ach_pct),
        ach_accel_bps=float(ach_bps),
        ach_fixed_fee=float(ach_fee),
        impl_fee_discount_pct=float(impl_d),
        hold_days_cc=2,
        saas_arr_list=saas_list,
        impl_fee_list=impl_list,
    )
    wp = win_rate(p)
    if wp <= 0.05:
        return None

    deals = deals_to_pricing * wp
    yearly = compute_three_year_financials(volumes, p, include_float=include_float)

    total_rev = 0.0
    total_cost = 0.0
    total_vol = 0.0
    for y in [1, 2, 3]:
        ret = _retention_factor(y, quarterly_churn)
        total_rev += yearly[y].total_revenue * deals * ret
        total_cost += yearly[y].total_cost * deals * ret
        vol_y = volumes[y]
        total_vol += (vol_y.cc + vol_y.ach + vol_y.bank_network) * deals * ret

    margin_pct = (total_rev - total_cost) / total_rev if total_rev > 0 else 0
    take_rate_val = total_rev / total_vol if total_vol > 0 else 0

    return total_rev, margin_pct, take_rate_val, wp


def _sweep_grid(grid, saas_list, impl_list, deals_to_pricing, volumes,
                quarterly_churn, include_float):
    """Evaluate all combos in grid, return (combos, results) arrays for valid ones."""
    valid_combos = []
    results = []
    for combo in grid:
        r = _eval_combo(combo, saas_list, impl_list, deals_to_pricing,
                        volumes, quarterly_churn, include_float)
        if r is not None:
            valid_combos.append(combo)
            results.append(r)
    return valid_combos, np.array(results) if results else np.empty((0, 4))


def _balanced_scores(results: np.ndarray, std_metrics: tuple[float, float, float] | None = None) -> np.ndarray:
    """Compute balanced scores as improvement over standard.

    For each combo, measure the % improvement over standard on each metric,
    then compute a weighted average (revenue 50%, margin% 25%, take rate 25%).
    Revenue gets more weight because it captures absolute impact (deals matter).
    Combos that underperform standard on revenue get a heavy penalty.
    """
    rev = results[:, 0]
    mar = results[:, 1]
    tr = results[:, 2]

    if std_metrics is not None:
        std_rev, std_mar, std_tr = std_metrics
    else:
        std_rev = np.median(rev)
        std_mar = np.median(mar)
        std_tr = np.median(tr)

    rev_imp = (rev - std_rev) / std_rev if std_rev > 0 else np.zeros_like(rev)
    mar_imp = (mar - std_mar) / std_mar if std_mar > 0 else np.zeros_like(mar)
    tr_imp = (tr - std_tr) / std_tr if std_tr > 0 else np.zeros_like(tr)

    def _norm(vals):
        mn, mx = vals.min(), vals.max()
        return (vals - mn) / (mx - mn) if mx > mn else np.zeros_like(vals)

    score = 0.50 * _norm(rev_imp) + 0.25 * _norm(mar_imp) + 0.25 * _norm(tr_imp)

    below_std_rev = rev < std_rev
    score[below_std_rev] *= 0.3

    return score


def _refine_grid(best_combo, lb):
    """Build a fine grid around the best combo from the coarse pass."""
    saas_d, cc_b, cc_a, ach_pct, ach_bps, ach_fee, impl_d = best_combo

    def _local(center, lo, hi, step):
        vals = np.arange(max(lo, center - step * 3), min(hi, center + step * 3) + step / 2, step)
        return vals

    saas_vals = _local(saas_d, lb["saas_arr_discount_pct"]["min"],
                       lb["saas_arr_discount_pct"]["max"], 0.025)
    cc_b_vals = _local(cc_b, lb["cc_base_rate"]["min"],
                       lb["cc_base_rate"]["max"], 0.0005)
    cc_a_vals = _local(cc_a, lb["cc_amex_rate"]["min"],
                       lb["cc_amex_rate"]["max"], 0.001)
    ach_p_vals = _local(ach_pct, lb["ach_accel_pct"]["min"],
                        lb["ach_accel_pct"]["max"], 0.05)
    ach_bps_vals = _local(ach_bps, lb["ach_accel_bps"]["min"],
                          lb["ach_accel_bps"]["max"], 0.0005)
    ach_fee_vals = _local(ach_fee, lb["ach_fixed_fee"]["min"],
                          lb["ach_fixed_fee"]["max"], 0.50)
    impl_vals = _local(impl_d, lb["impl_fee_discount_pct"]["min"],
                       lb["impl_fee_discount_pct"]["max"], 0.10)

    return list(product(saas_vals, cc_b_vals, cc_a_vals, ach_p_vals,
                        ach_bps_vals, ach_fee_vals, impl_vals))


def optimize_balanced(
    pricing: PricingScenario,
    deals_to_pricing: int,
    volumes: dict,
    quarterly_churn: float = 0.02,
    include_float: bool = True,
    std_metrics: tuple[float, float, float] | None = None,
) -> tuple[PricingScenario, dict, float, dict]:
    """Two-pass grid search: coarse sweep then fine refinement.

    std_metrics = (3yr_revenue, margin_pct, take_rate) for the Standard scenario.
    Used to score combos relative to the benchmark.

    Returns (best_pricing, changes_dict, achieved_win_rate, search_stats).
    """
    lb = cfg.LEVER_BOUNDS
    saas_list = pricing.saas_arr_list
    impl_list = pricing.impl_fee_list

    # Pass 1: coarse grid
    coarse_grid = list(product(
        np.arange(lb["saas_arr_discount_pct"]["min"], lb["saas_arr_discount_pct"]["max"] + 0.01, 0.10),
        np.array([lb["cc_base_rate"]["min"], 0.021, 0.023, lb["cc_base_rate"]["max"]]),
        np.array([lb["cc_amex_rate"]["min"], 0.033, lb["cc_amex_rate"]["max"]]),
        np.array([0.25, 0.50, 0.75]),
        np.array([lb["ach_accel_bps"]["min"], 0.003, lb["ach_accel_bps"]["max"]]),
        np.array([2.0, 3.50, 5.0]),
        np.array([0.0, 0.50, 1.0]),
    ))

    combos1, results1 = _sweep_grid(coarse_grid, saas_list, impl_list,
                                     deals_to_pricing, volumes,
                                     quarterly_churn, include_float)

    if len(combos1) == 0:
        return pricing, {}, cfg.WIN_RATE_BASELINE, {"combos_evaluated": len(coarse_grid), "pass": "coarse_only"}

    scores1 = _balanced_scores(results1, std_metrics)
    top_idx = np.argmax(scores1)
    best_coarse = combos1[top_idx]

    # Pass 2: fine grid around best coarse combo
    fine_grid = _refine_grid(best_coarse, lb)

    combos2, results2 = _sweep_grid(fine_grid, saas_list, impl_list,
                                     deals_to_pricing, volumes,
                                     quarterly_churn, include_float)

    # Merge both passes
    all_combos = combos1 + combos2
    all_results = np.vstack([results1, results2]) if len(combos2) > 0 else results1
    all_scores = _balanced_scores(all_results, std_metrics)

    best_idx = np.argmax(all_scores)
    best_combo = all_combos[best_idx]
    total_evaluated = len(coarse_grid) + len(fine_grid)

    saas_d, cc_b, cc_a, ach_pct, ach_bps, ach_fee, impl_d = best_combo
    best_pricing = PricingScenario(
        saas_arr_discount_pct=float(saas_d),
        cc_base_rate=float(cc_b),
        cc_amex_rate=float(cc_a),
        ach_accel_pct=float(ach_pct),
        ach_accel_bps=float(ach_bps),
        ach_fixed_fee=float(ach_fee),
        impl_fee_discount_pct=float(impl_d),
        hold_days_cc=2,
        saas_arr_list=saas_list,
        impl_fee_list=impl_list,
    )
    best_wp = win_rate(best_pricing)

    changes = {}
    fields = [
        ("saas_arr_discount_pct", 1e-4),
        ("cc_base_rate", 1e-5),
        ("cc_amex_rate", 1e-5),
        ("ach_accel_pct", 0.01),
        ("ach_accel_bps", 1e-5),
        ("ach_fixed_fee", 0.01),
        ("impl_fee_discount_pct", 1e-4),
    ]
    for field, tol in fields:
        old = getattr(pricing, field)
        new = getattr(best_pricing, field)
        if abs(new - old) > tol:
            changes[field] = (old, new)

    stats = {
        "combos_evaluated": total_evaluated,
        "coarse_combos": len(coarse_grid),
        "fine_combos": len(fine_grid),
        "valid_combos": len(all_combos),
        "best_score": float(all_scores[best_idx]),
        "best_revenue": float(all_results[best_idx, 0]),
        "best_margin_pct": float(all_results[best_idx, 1]),
        "best_take_rate": float(all_results[best_idx, 2]),
    }

    return best_pricing, changes, best_wp, stats
