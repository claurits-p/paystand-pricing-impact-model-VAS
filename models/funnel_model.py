"""
Sales funnel model — three computation modes:

1. Historical: hardcoded grand-total rates (Jan 2023–Jan 2026).
2. Standard (Q4 2025): hardcoded Q4 actual rates, no model.
3. Model-driven (optimized): cube-root per-stage factor applied
   with graduated weights across 5 stages:
     SQL→SQL-H:  per_stage^0.25  (quarter weight — subtle early signal)
     SQL-H→SAL:  per_stage^0.50  (half weight)
     SAL→ROI, ROI→Neg, Neg→Won: per_stage^1.0  (full weight)
   Deals compound naturally; more competitive pricing lifts every stage.
"""
from __future__ import annotations
from dataclasses import dataclass
import math

import config as cfg


@dataclass
class FunnelResult:
    """Funnel output for a single scenario."""
    sqls: int
    stages: list[dict]
    deals_to_roi: int
    deals_to_negotiation: int
    deals_won: int
    win_rate: float           # ROI → Win rate


def compute_historical_funnel(sqls: int) -> list[dict]:
    """Hardcoded grand-total rates (Jan 2023–Jan 2026). No model."""
    count = float(sqls)
    stages = [{"name": "SQL", "count": int(round(count)), "rate": None}]

    for stage in cfg.FUNNEL_HISTORICAL_RATES:
        rate = stage["rate"]
        count = count * rate
        stages.append({
            "name": stage["to"],
            "count": int(round(count)),
            "rate": rate,
        })

    return stages


def compute_standard_funnel(sqls: int, roi_to_win: float) -> FunnelResult:
    """Q4 2025 hardcoded rates for upstream, user-stated ROI→Win for Won."""
    count = float(sqls)
    stages = [{"name": "SQL", "count": int(round(count)), "rate": None, "adjusted_rate": None}]

    deals_at_roi = 0
    deals_at_neg = 0

    for stage in cfg.FUNNEL_Q4_RATES:
        rate = stage["rate"]
        count = count * rate
        stages.append({
            "name": stage["to"],
            "count": int(round(count)),
            "rate": rate,
            "adjusted_rate": rate,
        })
        if stage["to"] == "ROI":
            deals_at_roi = int(round(count))
        if stage["to"] == "Negotiation":
            deals_at_neg = int(round(count))

    deals_won = min(int(round(deals_at_roi * roi_to_win)), deals_at_neg)
    neg_to_won = deals_won / deals_at_neg if deals_at_neg > 0 else 0.0

    stages.append({
        "name": "Won",
        "count": deals_won,
        "rate": neg_to_won,
        "adjusted_rate": neg_to_won,
    })

    return FunnelResult(
        sqls=sqls,
        stages=stages,
        deals_to_roi=deals_at_roi,
        deals_to_negotiation=deals_at_neg,
        deals_won=deals_won,
        win_rate=roi_to_win,
    )


def compute_funnel(
    sqls: int,
    scenario_win_rate: float,
    baseline_win_rate: float,
) -> FunnelResult:
    """Model-driven funnel for optimized scenarios.

    Graduated uplift weights (derived from ROI→Win improvement ratio):
      SQL→SQL-H:   per_stage^0.25  (quarter — subtle early signal)
      SQL-H→SAL:   per_stage^0.50  (half)
      SAL→ROI+:    per_stage^1.0   (full)
    Deals compound naturally through adjusted rates.
    """
    hist = {s["to"]: s["rate"] for s in cfg.FUNNEL_HISTORICAL_RATES}

    count = float(sqls)
    stages = [{"name": "SQL", "count": int(round(count)), "rate": None, "adjusted_rate": None}]

    sql_to_sqlh_base = hist["SQL-H"]
    sqlh_to_sal_base = hist["SAL"]
    sal_to_roi_base  = hist["ROI"]
    roi_to_neg_base  = hist["Negotiation"]
    neg_to_won_base  = hist["Won"]

    improvement = scenario_win_rate / baseline_win_rate if baseline_win_rate > 0 else 1.0
    per_stage = improvement ** (1.0 / 3.0) if improvement > 0 else 1.0
    per_stage_quarter = per_stage ** 0.25
    per_stage_half    = per_stage ** 0.5

    new_sql_to_sqlh = min(1.0, sql_to_sqlh_base * per_stage_quarter)
    new_sqlh_to_sal = min(1.0, sqlh_to_sal_base * per_stage_half)
    new_sal_to_roi  = min(1.0, sal_to_roi_base  * per_stage)
    new_roi_to_neg  = min(1.0, roi_to_neg_base  * per_stage)
    new_neg_to_won  = min(1.0, neg_to_won_base  * per_stage)

    count = count * new_sql_to_sqlh
    deals_at_sqlh = count

    stages.append({
        "name": "SQL-H",
        "count": int(round(deals_at_sqlh)),
        "rate": sql_to_sqlh_base,
        "adjusted_rate": new_sql_to_sqlh,
    })

    sal_count = round(deals_at_sqlh * new_sqlh_to_sal)
    stages.append({
        "name": "SAL",
        "count": sal_count,
        "rate": sqlh_to_sal_base,
        "adjusted_rate": new_sqlh_to_sal,
    })

    roi_count = round(sal_count * new_sal_to_roi)
    stages.append({
        "name": "ROI",
        "count": roi_count,
        "rate": sal_to_roi_base,
        "adjusted_rate": new_sal_to_roi,
    })

    neg_count = round(roi_count * new_roi_to_neg)
    stages.append({
        "name": "Negotiation",
        "count": neg_count,
        "rate": roi_to_neg_base,
        "adjusted_rate": new_roi_to_neg,
    })

    won_count = round(neg_count * new_neg_to_won)
    stages.append({
        "name": "Won",
        "count": won_count,
        "rate": neg_to_won_base,
        "adjusted_rate": new_neg_to_won,
    })

    return FunnelResult(
        sqls=sqls,
        stages=stages,
        deals_to_roi=roi_count,
        deals_to_negotiation=neg_count,
        deals_won=won_count,
        win_rate=scenario_win_rate,
    )
