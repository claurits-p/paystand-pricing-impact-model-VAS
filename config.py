"""
Default assumptions, pricing lever bounds, and win-rate model config.
All values are configurable via the Streamlit UI.
"""

# ── SaaS Defaults ──────────────────────────────────────────────
SAAS_ARR_DEFAULT = 30_476          # $/year (avg ARR/deal pre-discount from Q4 2025 data)
SAAS_IMPL_FEE_DEFAULT = 3_000      # $ one-time implementation fee
SAAS_ARR_MARGIN = 0.85             # 85% margin on ARR

# ── CC Defaults ────────────────────────────────────────────────
CC_STANDARD_BASE_RATE = 0.022      # 2.20% standard base CC rate
CC_STANDARD_AMEX_RATE = 0.035      # 3.50% AMEX standard
CC_FIXED_COMPONENT = 0.0053        # 0.53% fixed component (mid-tier cards, assessments, etc.)
CC_BASE_VOLUME_SHARE = 0.75        # 75% of CC volume at base rate
CC_AMEX_VOLUME_SHARE = 0.25        # 25% of CC volume at AMEX rate
CC_COST_RATE = 0.024               # 2.40% blended cost (interchange + assessments + markup)

# ── ACH / Bank Network Defaults ───────────────────────────────
ACH_COST_PER_TXN = 0.13           # $0.13 per transaction cost
ACH_AVG_TXN_SIZE = 1_700          # $1,700 average transaction size

# ACH blend model: two profiles
# Accelerated: high bps, fast hold (2/2/3), no float
# Non-accelerated: fixed fee, slow hold (2/5/7), earns float
ACH_ACCEL_HOLD = {"cc": 2, "bank": 2, "ach": 3}
ACH_SLOW_HOLD = {"cc": 2, "bank": 5, "ach": 7}
ACH_STD_ACCEL_PCT = 1.0            # standard today: 100% accelerated (given away free)
ACH_STD_ACCEL_BPS = 0.0010        # 0.10% standard accelerated rate
ACH_STD_FIXED_FEE = 2.50          # $2.50 standard fixed fee for non-accelerated

# ── Hold Time (per payment type) ──────────────────────────────
HOLD_DAYS_CC_DEFAULT = 2
HOLD_DAYS_ACH_DEFAULT = 6
HOLD_DAYS_BANK_DEFAULT = 4
FLOAT_ANNUAL_RATE = 0.065          # 6.5% return on float balances
FLOAT_CALENDAR_FACTOR = 7 / 5     # convert business hold days to calendar days
SAAS_ANNUAL_ESCALATOR = 0.07       # 7% annual increase on standard ARR

# ── Pricing Lever Bounds ──────────────────────────────────────
# Strategy A: discount on list price (removed at Y2 renewal)
LEVER_BOUNDS = {
    "saas_arr_discount_pct": {"min": 0.0, "max": 1.0,  "default": 0.30, "step": 0.05},
    "impl_fee_discount_pct":  {"min": 0.0, "max": 1.0,  "default": 0.0, "step": 0.10},
    "cc_base_rate":           {"min": 0.019, "max": 0.025, "default": 0.022, "step": 0.001},
    "cc_amex_rate":           {"min": 0.030, "max": 0.036, "default": 0.035, "step": 0.005},
    "ach_accel_pct":          {"min": 0.25, "max": 0.75, "default": 0.50, "step": 0.05},
    "ach_accel_bps":          {"min": 0.0010, "max": 0.0049, "default": 0.0035, "step": 0.0005},
    "ach_fixed_fee":          {"min": 2.00, "max": 5.00, "default": 2.50, "step": 0.25},
    "hold_days_cc":           {"min": 1, "max": 2, "default": 2, "step": 1},
    "removal_pct":            {"min": 0.0, "max": 0.50, "default": 0.25, "step": 0.05},
}

# Strategy B: flat monthly SaaS, persists all 3 years (no removal)
SAAS_FLAT_MONTHLY_BOUNDS = {"min": 600, "max": 1000, "default": 800, "step": 50}

# ── Win Rate Model (simple linear, asymmetric) ──────────────
# Win rate is driven by the *effective Y1 monthly SaaS* the customer
# sees at signing. Both strategies map to the same curve.
# Other levers (CC, ACH, impl) remain the same.
# Target range: ~10% (all worst) to ~90% (all best).
WIN_RATE_BASELINE = 0.59           # 59% at standard pricing

STANDARD_PRICING = {
    "saas_arr_discount_pct": 0.30,
    "cc_base_rate": 0.022,
    "cc_amex_rate": 0.035,
    "ach_accel_pct": 1.0,         # 100% accelerated (given away free today)
    "ach_accel_bps": 0.0010,      # 0.10% on accelerated
    "ach_fixed_fee": 2.50,        # $2.50 for non-accelerated
    "hold_days_cc": 2,
    "impl_fee_discount_pct": 0.0,
}

# Standard effective Y1 SaaS: $30,476 * (1 - 0.30) = $21,333
STD_EFFECTIVE_Y1_SAAS = SAAS_ARR_DEFAULT * (1 - STANDARD_PRICING["saas_arr_discount_pct"])

# Asymmetric max win-rate impact per lever (in percentage points).
# "up" = full move toward most competitive pricing.
# "down" = full move toward least competitive pricing.
LEVER_IMPACT = {
    "saas_y1_price": {"up": 0.25, "down": 0.28},   # dominant: steep in the practical range ($7.2k-$17.5k)
    "cc_rate":       {"up": 0.05, "down": 0.08},
    "impl_discount": {"up": 0.03, "down": 0.06},
}

# SaaS convex curve: power > 1 gives diminishing returns on deeper discounts
SAAS_WR_POWER = 1.3

# ── 3-Component ACH Win Rate Model ──────────────────────────
# Component 1: BPS penalty — high uncapped bps × accel share hurts win rate
ACH_BPS_PENALTY_MAX = 0.08        # -8pp max
# Component 2: Accel reduction benefit — moving off 100% accelerated is good
ACH_ACCEL_REDUCTION_MAX = 0.04    # +4pp max
# Component 3: Fee penalty — fixed fees above $3 add mild friction
ACH_FEE_PENALTY_MAX = 0.02        # -2pp max
ACH_FEE_NEUTRAL_THRESHOLD = 3.00  # fees at or below this are neutral
# Component 4: Fee preference bonus — customers prefer predictable fixed fee
ACH_FEE_PREFERENCE_MAX = 0.01     # +1pp max
# Total range: +5pp (all best) to ~-7.5pp (worst practical combo)

# ── Discount Removal (New Framework) ─────────────────────────
# The optimizer chooses removal_pct as a lever (how much of Y1 discount to remove at Y2).
# Cap: Y2 price can never exceed 2× Y1 price (doubling limit).
# Attainment: only 75% of planned removals actually succeed across the portfolio.
REMOVAL_PCT_BOUNDS = {"min": 0.0, "max": 0.50, "default": 0.25, "step": 0.05}
REMOVAL_ATTAINMENT = 0.75             # 75% of planned removals succeed (midpoint of 70-80%)
REMOVAL_MAX_PRICE_RATIO = 2.0         # Y2 price can't exceed 2× Y1 price

# ── Churn Model (Anchored to Real Renewal Data) ─────────────
# Two anchor points from actual business data:
#   0% price increase → 5% annual churn (95% retention)
#   25% price increase → 10% annual churn (90% retention) — current avg
# Linear: each 1% price increase adds 0.20pp annual churn above the 5% base.
CHURN_BASE_ANNUAL = 0.05              # 5% annual churn with NO price increase
CHURN_PER_PCT_INCREASE = 0.0020       # +0.20pp annual churn per 1% Y2 price increase
CHURN_ANNUAL_CAP = 0.35               # max 35% annual churn even at extreme removal

# Flat monthly: no price increase → base churn only
FLAT_MONTHLY_ANNUAL_CHURN = 0.05      # 5% (same as no-increase anchor)

# ── Growth ───────────────────────────────────────────────────
GROWTH_BASELINE_QUARTERLY = 0.02        # 2% quarterly growth offsets churn (UI adjustable)

# ── Sales Funnel ─────────────────────────────────────────────
FUNNEL_SQLS_PER_QUARTER = 921

# Q4 2025 actual rates (for Standard scenario — hardcoded from data)
# Derived from cumulative: SQL→SQL-H = SQL→Win/SQL-H→Win, SQL-H→SAL = SQL-H→Win/SAL→Win
# 900 × 73.8% × 47.8% × 39.81% = 126 at ROI; ROI→Neg 69.77%; ROI→Win ≈ 59%
FUNNEL_Q4_RATES = [
    {"from": "SQL",    "to": "SQL-H",        "rate": 0.738},
    {"from": "SQL-H",  "to": "SAL",          "rate": 0.478},
    {"from": "SAL",    "to": "ROI",          "rate": 0.3981},
    {"from": "ROI",    "to": "Negotiation",  "rate": 0.6977},
]
FUNNEL_Q4_ROI_TO_WIN = 0.58   # Q4 2025 ROI→Win rate (baseline for model)

# Grand total historical rates (Jan 2023 – Mar 2026, for Historical column)
# Derived from cumulative: SQL→Win=7.37%, SQL-H→Win=9.78%, SAL→Win=21.09%,
# ROI→Win=51%, Neg→Win=77.83%
FUNNEL_HISTORICAL_RATES = [
    {"from": "SQL",          "to": "SQL-H",        "rate": 0.7536},
    {"from": "SQL-H",        "to": "SAL",          "rate": 0.4637},
    {"from": "SAL",          "to": "ROI",          "rate": 0.4134},
    {"from": "ROI",          "to": "Negotiation",  "rate": 0.6553},
    {"from": "Negotiation",  "to": "Won",          "rate": 0.7783},
]

# ── Teampay Defaults ─────────────────────────────────────────
TEAMPAY_SAAS_ANNUAL = 7_500        # $7,500/year SaaS (free Year 1)
TEAMPAY_SAAS_MARGIN = 0.80         # 80% margin on Teampay SaaS
TEAMPAY_PROCESSING_RATE = 0.023    # 2.3% per transaction
TEAMPAY_PROCESSING_MARGIN = 0.27   # 27% margin on processing
TEAMPAY_MONTHLY_VOLUME = 100_000   # $100k/month per Teampay deal (Y1 at 50% ramp)
TEAMPAY_PROCESSING_GROWTH = 0.03   # 3% annual growth on processing volume

# ── Value-Added Services (VAS) Fee Revenue ───────────────────
# Data-driven list of all fee items with TAM > $0.
# Each item carries tam_mrr (base), min/max ARR ranges from the sheet,
# recommended flag, build_cost, and model type.
UPSIDE_TOTAL_CUSTOMERS = 750

# Volume-model constants (used by items with model != "flat")
UPSIDE_PAYOUT_BPS = 0.001
UPSIDE_AVG_CARD_TXN_SIZE = 1_150
UPSIDE_PAYMENT_FAILURE_RATE = 0.108
UPSIDE_PAYMENT_FAILURE_FEE = 0.50
UPSIDE_ACCOUNT_UPDATER_OPTIN = 0.50
UPSIDE_ACCOUNT_UPDATER_FEE = 0.20

VAS_ITEMS = [
    {"name": "Transfer / Recon Fee",      "tam_mrr": 440_000, "min_tam_arr": 2_640_000, "max_tam_arr": 5_280_000, "recommended": False, "build_cost": 0,      "model": "volume_payout"},
    {"name": "Invoicing Fee",             "tam_mrr": 250_000, "min_tam_arr": 1_500_000, "max_tam_arr": 3_000_000, "recommended": False, "build_cost": 0,      "model": "flat"},
    {"name": "Instant Payout Fee",        "tam_mrr": 200_000, "min_tam_arr": 1_200_000, "max_tam_arr": 2_400_000, "recommended": True,  "build_cost": 10_000, "model": "flat"},
    {"name": "Account Maintenance",       "tam_mrr": 200_000, "min_tam_arr": 1_200_000, "max_tam_arr": 2_400_000, "recommended": False, "build_cost": 0,      "model": "flat"},
    {"name": "Per-User / Seat Fee",       "tam_mrr": 100_000, "min_tam_arr":   600_000, "max_tam_arr": 1_200_000, "recommended": True,  "build_cost": 0,      "model": "flat"},
    {"name": "Tax Automation Fee",        "tam_mrr":  63_000, "min_tam_arr":   378_000, "max_tam_arr":   756_000, "recommended": False, "build_cost": 10_000, "model": "flat"},
    {"name": "Buy Now Pay Later",         "tam_mrr":  60_000, "min_tam_arr":   360_000, "max_tam_arr":   720_000, "recommended": True,  "build_cost": 10_000, "model": "flat"},
    {"name": "Premium Support",           "tam_mrr":  50_000, "min_tam_arr":   300_000, "max_tam_arr":   600_000, "recommended": False, "build_cost": 0,      "model": "flat"},
    {"name": "Dispute Threshold Fee",     "tam_mrr":  35_000, "min_tam_arr":   210_000, "max_tam_arr":   420_000, "recommended": True,  "build_cost": 0,      "model": "flat"},
    {"name": "PCI Compliance Fee",        "tam_mrr":  21_000, "min_tam_arr":   126_000, "max_tam_arr":   252_000, "recommended": False, "build_cost": 0,      "model": "flat"},
    {"name": "Smart Retry",              "tam_mrr":  20_000, "min_tam_arr":   120_000, "max_tam_arr":   240_000, "recommended": True,  "build_cost": 0,      "model": "flat"},
    {"name": "Min Volume Penalties",      "tam_mrr":  18_000, "min_tam_arr":   108_000, "max_tam_arr":   216_000, "recommended": False, "build_cost": 0,      "model": "flat"},
    {"name": "Recurring Billing Fee",     "tam_mrr":  17_000, "min_tam_arr":   102_000, "max_tam_arr":   204_000, "recommended": False, "build_cost": 0,      "model": "flat"},
    {"name": "Payment Failures",          "tam_mrr":  15_000, "min_tam_arr":    90_000, "max_tam_arr":   180_000, "recommended": True,  "build_cost": 0,      "model": "volume_failures"},
    {"name": "Account Updater Fee",       "tam_mrr":  13_500, "min_tam_arr":    81_000, "max_tam_arr":   162_000, "recommended": True,  "build_cost": 0,      "model": "volume_updater"},
    {"name": "Reporting / Query Cost",    "tam_mrr":  12_500, "min_tam_arr":    75_000, "max_tam_arr":   150_000, "recommended": True,  "build_cost": 10_000, "model": "flat"},
    {"name": "Network Token Fee",         "tam_mrr":   5_000, "min_tam_arr":    30_000, "max_tam_arr":    60_000, "recommended": False, "build_cost": 10_000, "model": "flat"},
    {"name": "Batch Processing Fee",      "tam_mrr":   3_850, "min_tam_arr":    23_100, "max_tam_arr":    46_200, "recommended": False, "build_cost": 0,      "model": "flat"},
    {"name": "AI Dispute Resolution",     "tam_mrr":   3_600, "min_tam_arr":    21_600, "max_tam_arr":    43_200, "recommended": True,  "build_cost": 10_000, "model": "flat"},
    {"name": "Wire Transfer Fee",         "tam_mrr":   3_000, "min_tam_arr":    18_000, "max_tam_arr":    36_000, "recommended": False, "build_cost": 10_000, "model": "flat"},
    {"name": "Fraud Screening Fee",       "tam_mrr":   2_600, "min_tam_arr":    15_600, "max_tam_arr":    31_200, "recommended": False, "build_cost": 10_000, "model": "flat"},
    {"name": "Fee on Refunds",            "tam_mrr":   1_000, "min_tam_arr":     6_000, "max_tam_arr":    12_000, "recommended": True,  "build_cost": 0,      "model": "flat"},
    {"name": "Exit Fee",                  "tam_mrr":     250, "min_tam_arr":     1_500, "max_tam_arr":     3_000, "recommended": False, "build_cost": 0,      "model": "flat"},
    {"name": "KYC/KYB Verification",      "tam_mrr":     100, "min_tam_arr":       600, "max_tam_arr":     1_200, "recommended": False, "build_cost": 0,      "model": "flat"},
    {"name": "Dispute Retrieval Fee",     "tam_mrr":     100, "min_tam_arr":       600, "max_tam_arr":     1_200, "recommended": False, "build_cost": 0,      "model": "flat"},
]
