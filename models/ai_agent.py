"""
AI Agent — two modes:

1. run_ai_analysis(): GPT-4o analyzes model outputs and provides strategic recommendations.
2. run_ai_scenario(): GPT-4o acts as a "deal desk strategist" — proposes specific pricing
   levers that get run through the full financial model as a 4th scenario.
"""
from __future__ import annotations
import json
import re
from openai import OpenAI

import config as cfg

# ── Analysis Agent (existing) ────────────────────────────────

SYSTEM_PROMPT = """You are a senior pricing strategy analyst embedded inside Paystand, a B2B payments company.

ABOUT PAYSTAND:
- Paystand sells a B2B payment processing platform to mid-market and enterprise companies.
- Revenue streams: SaaS subscriptions (annual), credit card processing fees, ACH processing fees, float income from holding funds, implementation fees, Teampay (card processing add-on), and Value-Added Services (VAS) fees.
- Competitive market against legacy processors (Bill.com, Stripe, etc.) — pricing is the primary lever to win deals.
- Average deal: ~$30k ARR pre-discount, ~$5.5k implementation fee.
- Current standard pricing: 30% SaaS discount, 2.20% CC base rate, 0.10% ACH rate on 100% accelerated ACH.
- Sales team prices deals individually — no fixed rate card.

KEY BUSINESS DYNAMICS:
1. LOGOS MATTER: Company is in growth mode. Each customer processes increasing volume over time — a deal won today compounds in value. Each deal also generates ~$25K/yr in Value-Added Services (VAS) fees. Winning 10 more deals at slightly lower margins is usually better than winning 5 at higher margins.
2. SAAS DISCOUNT & REMOVAL: The optimizer now chooses both discount level AND removal rate (0-50%). Only 75% of planned removals succeed (attainment). Y2 price capped at 2× Y1. Churn scales linearly with Y2 price increase: 5% annual at 0% increase, 10% at 25% increase, capped at 35%.
3. ACH IS UNDERPRICED TODAY: Standard gives away ACH at 0.10% (essentially free). There's room to charge more via fixed fees or higher BPS without significantly hurting win rate.
4. FLAT MONTHLY SAAS: Alternative to discount-and-remove. Charge $600-$1000/month flat, no removal, no sticker shock. Lower per-deal SaaS but dramatically better retention.
5. TEAMPAY BUNDLING: Optimized scenarios assume higher Teampay adoption (80% contract opt-in, 45% usage) vs standard (10%). This is a real and achievable revenue upside.
6. VAS FEES: 25 value-added service fee items (transfer fees, payout fees, seat fees, dispute fees, etc.) generate ~$25K per deal per year. These are a pure function of deal count — more deals won = proportionally more VAS revenue. This makes deal count even more valuable than SaaS revenue alone suggests.
7. RETENTION > EXTRACTION: A customer staying 5 years at $15k/yr SaaS is worth more than one paying $25k Y1 who churns at Y2.

OUTPUT FORMAT — you MUST follow this exact structure:

### Key Insight
One sentence: what is the single most important takeaway from these results?

### What the Optimizers Are Telling Us
2-3 bullets explaining WHY the optimizers made the choices they did. Don't describe what they picked — the user can see that. Explain the underlying logic. For example: "The revenue optimizer is willing to sacrifice $X per deal in SaaS because winning Y additional deals generates $Z more in processing revenue over 3 years."

### Recommended Sales Playbook
3-4 specific, actionable bullets the sales team can use TOMORROW. Use exact numbers. For example:
- "Target X-Y% SaaS discount for deals over $Zk ARR"
- "Push flat monthly at $X/mo for price-sensitive prospects"
- "Move ACH to X% accelerated / Y% fixed fee at $Z"

### What Could Change This Answer
2-3 bullets on which assumptions matter most. What would flip the recommendation? For example: "If quarterly churn is actually 3% instead of 2%, the flat monthly strategy becomes significantly more attractive because..."

### Risk to Watch
One specific risk the leadership team should monitor.

RULES:
- Use "Standard", "Revenue Optimized", and "$ Margin Optimized" consistently — never abbreviate or rename them.
- Do NOT just summarize the numbers. The user can already see every number in the dashboard. Your job is to provide INSIGHT they cannot get from the numbers alone.
- Be specific with dollar amounts and percentages.
- Total response under 400 words. Every sentence must add value."""


def _build_context(standard, revenue_opt, margin_opt) -> str:
    """Build a detailed context string from the three scenario results."""

    def _scenario_summary(s) -> str:
        p = s.per_deal_pricing
        strategy = "Flat Monthly" if p.saas_strategy == "flat_monthly" else "Discount & Remove"

        saas_detail = ""
        if p.saas_strategy == "flat_monthly":
            saas_detail = f"Flat ${p.saas_flat_monthly:,.0f}/mo (${p.saas_flat_monthly * 12:,.0f}/yr)"
        else:
            saas_detail = (
                f"List ${p.saas_arr_list:,.0f}, {p.saas_arr_discount_pct:.0%} discount, "
                f"Y1 effective ${p.effective_y1_saas:,.0f}"
            )

        eff_bps = p.ach_accel_pct * p.ach_accel_bps + (1 - p.ach_accel_pct) * (p.ach_fixed_fee / 1700)

        lines = [
            f"  Scenario: {s.name}",
            f"  SaaS Strategy: {strategy}",
            f"  SaaS: {saas_detail}",
            f"  Implementation Fee: ${p.effective_impl_fee:,.0f} ({p.impl_fee_discount_pct:.0%} discount)",
            f"  CC Base Rate: {p.cc_base_rate:.2%}, AMEX Rate: {p.cc_amex_rate:.2%}",
            f"  ACH: {p.ach_accel_pct:.0%} accelerated at {p.ach_accel_bps:.2%} bps, "
            f"{1 - p.ach_accel_pct:.0%} fixed fee at ${p.ach_fixed_fee:.2f}",
            f"  Effective ACH BPS: {eff_bps:.4%}",
            f"  Win Rate: {s.win_rate:.0%} → {s.deals_won} deals won",
            f"  3-Year Revenue: ${s.three_year_revenue:,.0f}",
            f"  3-Year Margin: ${s.three_year_margin:,.0f}",
            f"  3-Year Margin %: {s.three_year_margin_pct:.1%}",
            f"  3-Year Take Rate: {s.three_year_take_rate:.2%}",
        ]

        for y in [1, 2, 3]:
            cy = s.cohort_yearly[y]
            pd_y = s.per_deal_yearly[y]
            lines.append(
                f"  Year {y}: {cy.deals} active deals, "
                f"Rev ${cy.total_revenue:,.0f}, "
                f"Margin ${cy.margin:,.0f} ({cy.margin_pct:.1%}), "
                f"SaaS ${cy.saas_revenue:,.0f}, "
                f"Per-deal SaaS ${pd_y.saas_revenue:,.0f}"
            )

        return "\n".join(lines)

    rev_delta = revenue_opt.three_year_revenue - standard.three_year_revenue
    mar_delta_rev = revenue_opt.three_year_margin - standard.three_year_margin
    mar_delta = margin_opt.three_year_margin - standard.three_year_margin
    rev_delta_mar = margin_opt.three_year_revenue - standard.three_year_revenue
    rev_pct = rev_delta / standard.three_year_revenue if standard.three_year_revenue > 0 else 0
    mar_pct = mar_delta / standard.three_year_margin if standard.three_year_margin > 0 else 0

    vas_section = ""
    if hasattr(standard, 'upside_detail') and any(
        s.upside_detail for s in [standard, revenue_opt, margin_opt] if hasattr(s, 'upside_detail')
    ):
        vas_lines = []
        for label, s in [("Standard", standard), ("Revenue Optimized", revenue_opt), ("$ Margin Optimized", margin_opt)]:
            if hasattr(s, 'upside_detail') and s.upside_detail:
                total_vas = sum(v for v in s.upside_detail.values())
                vas_lines.append(f"  {label}: ${total_vas:,.0f}/yr VAS fees ({s.deals_won} deals)")
        if vas_lines:
            vas_section = "\n- VAS Fees per year:\n" + "\n".join(vas_lines)

    context = f"""Here are the model outputs for this cohort. Analyze them using the exact output format specified.

STANDARD (what we do today):
{_scenario_summary(standard)}

REVENUE OPTIMIZED:
{_scenario_summary(revenue_opt)}
  Revenue vs Standard: ${rev_delta:+,.0f} ({rev_pct:+.1%})
  Margin vs Standard: ${mar_delta_rev:+,.0f}

$ MARGIN OPTIMIZED:
{_scenario_summary(margin_opt)}
  Margin vs Standard: ${mar_delta:+,.0f} ({mar_pct:+.1%})
  Revenue vs Standard: ${rev_delta_mar:+,.0f}

KEY COMPARISONS:
- Deal count: Standard {standard.deals_won} vs Revenue Optimized {revenue_opt.deals_won} vs $ Margin Optimized {margin_opt.deals_won}
- Revenue gap: Revenue Optimized adds ${rev_delta:+,.0f} over 3 years vs Standard
- Margin gap: $ Margin Optimized adds ${mar_delta:+,.0f} over 3 years vs Standard
- Per-deal Y1 SaaS: Standard ${standard.per_deal_yearly[1].saas_revenue:,.0f} vs Revenue Optimized ${revenue_opt.per_deal_yearly[1].saas_revenue:,.0f} vs $ Margin Optimized ${margin_opt.per_deal_yearly[1].saas_revenue:,.0f}
- Per-deal Y2 SaaS: Standard ${standard.per_deal_yearly[2].saas_revenue:,.0f} vs Revenue Optimized ${revenue_opt.per_deal_yearly[2].saas_revenue:,.0f} vs $ Margin Optimized ${margin_opt.per_deal_yearly[2].saas_revenue:,.0f}{vas_section}

Remember: provide INSIGHT, not summary. Follow the exact output format."""

    return context


def run_ai_analysis(
    standard,
    revenue_opt,
    margin_opt,
    api_key: str,
) -> str:
    """Send model outputs to GPT-4o and return the analysis."""
    client = OpenAI(api_key=api_key)

    context = _build_context(standard, revenue_opt, margin_opt)

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": context},
        ],
        temperature=0.3,
        max_tokens=2000,
    )

    return response.choices[0].message.content


# ── AI Scenario Agent ────────────────────────────────────────

_AI_SCENARIO_PROMPT = f"""You are a senior pricing strategist with complete knowledge of a B2B payments pricing model.

You will see the results of two mathematical optimizers — one that purely maximizes revenue, one that purely maximizes margin dollars. Your job is to find the BEST OVERALL pricing that maximizes risk-adjusted 3-year value.

YOUR GOAL: Maximize total 3-year value (revenue and margin) while managing retention risk. The math optimizers prove that winning MORE DEALS is the single most powerful lever — the Revenue Optimizer wins ~120 deals vs Standard's ~75, generating massive additional revenue. You should be AGGRESSIVE on deal count. Don't settle for Standard-level deal counts.

CRITICAL INSIGHT — DEAL COUNT IS KING:
- Each additional deal won generates ~$25,000/year in Value-Added Services (VAS) fee revenue ON TOP of SaaS and processing revenue. This is pure margin.
- VAS fees include: transfer fees, payout fees, seat fees, dispute fees, payment failure fees, etc. (25 items totaling ~$19M ARR across 750 customers).
- The Revenue Optimizer proves ~120 deals is achievable. Your target should be 90-120+ deals.
- A deal won at lower SaaS but with processing + VAS revenue is worth MORE than a deal lost at higher SaaS.

Think like a deal desk strategist: aggressive enough to win lots of deals, smart about extracting margin from ACH/CC pricing and controlling churn.

COMPLETE MODEL MECHANICS:

1. WIN RATE ({cfg.FUNNEL_Q4_ROI_TO_WIN:.0%} baseline at standard pricing, determines how many deals you win):
   - SaaS Y1 price is the DOMINANT lever. It follows a convex curve (power=1.3):
     * Best case: $7,200/yr (flat $600/mo) → +25pp above baseline
     * Worst case: $30,476/yr (0% discount) → -28pp below baseline
     * The convex shape means: going from 0% to 40% discount gives large win rate gains; going from 60% to 80% gives diminishing gains per point
   - CC rates: lowest rates (1.90%/3.00%) → +5pp; highest (2.50%/3.60%) → -8pp
   - ACH (3-component): reducing accelerated % from 100% helps (+4pp max); high BPS hurts (-8pp max); high fixed fees hurt mildly (-2pp max); customer preference for predictable fixed fees (+1pp max)
   - Impl fee: full waiver → +3pp; no discount → -6pp
   - Total range: ~10% to ~90% win rate

2. DEAL COUNT: Win rate feeds through a sales funnel ({cfg.FUNNEL_SQLS_PER_QUARTER} SQLs → conversion stages → deals won). Higher win rate = more deals, and the effect compounds through upstream funnel stages. The relationship is non-linear — small win rate improvements yield large deal count gains.

3. REVENUE PER DEAL:
   - SaaS: Y1 = list price × (1-discount). Y2/Y3 = partial discount removal + 7% escalator, capped at 2× Y1.
   - CC: volume × blended rate (Y1 uses scenario rates; Y2/Y3 reverts to standard 2.20%/3.50%)
   - ACH: accel volume × BPS + non-accel txns × fixed fee (same rates all 3 years)
   - Impl fee: Y1 only
   - Float income: from holding funds during settlement (driven by hold days)
   - VAS Fees: ~$25,000/deal/year in value-added service fees (not affected by your pricing — purely a function of deal count)

4. CHURN (critical for Y2/Y3 value):
   - 0% Y2 price increase → 5% annual churn
   - Each 1% price increase adds 0.20pp annual churn
   - 25% increase → 10% annual churn; capped at 35%
   - Flat monthly SaaS = 0% increase = lowest churn (5%)
   - 2% quarterly growth partially offsets churn
   - A 50% discount with 25% removal causes ~20% price increase → ~9% annual churn
   - A 50% discount with 50% removal causes ~40% price increase → ~13% annual churn

5. DISCOUNT REMOVAL:
   - removal_pct (0-50%): what fraction of Y1 discount is clawed back at Y2
   - Only 75% of planned removals succeed (attainment)
   - Higher removal = more Y2 SaaS revenue BUT higher churn
   - This is the core tension: aggressive removal recovers SaaS but kills retention

6. KEY DYNAMICS:
   - DEAL COUNT IS THE #1 LEVER: Each deal generates processing + VAS revenue that dwarfs the SaaS discount cost. Win more deals.
   - Logos compound: each deal processes increasing volume over time. More deals at lower margins can beat fewer deals at higher margins.
   - CC rates revert to standard at Y2 — so discounting CC Y1 has limited cost (only 1 year of lower rev)
   - ACH is currently given away at 0.10% — there is margin to capture here
   - Flat monthly SaaS ($600-$800/mo) gives very high win rates WITH lowest churn — consider this seriously

LEVER BOUNDS (you MUST stay within these):

SaaS Strategy — pick ONE:
  A) "discount_remove": saas_arr_discount_pct (0.00 to 1.00), removal_pct (0.00 to 0.50)
  B) "flat_monthly": saas_flat_monthly ($600 to $1000/month, no discount removal)

Other levers:
  cc_base_rate: {cfg.LEVER_BOUNDS['cc_base_rate']['min']} to {cfg.LEVER_BOUNDS['cc_base_rate']['max']}
  cc_amex_rate: {cfg.LEVER_BOUNDS['cc_amex_rate']['min']} to {cfg.LEVER_BOUNDS['cc_amex_rate']['max']}
  ach_accel_pct: {cfg.LEVER_BOUNDS['ach_accel_pct']['min']} to {cfg.LEVER_BOUNDS['ach_accel_pct']['max']}
  ach_accel_bps: {cfg.LEVER_BOUNDS['ach_accel_bps']['min']} to {cfg.LEVER_BOUNDS['ach_accel_bps']['max']}
  ach_fixed_fee: {cfg.LEVER_BOUNDS['ach_fixed_fee']['min']} to {cfg.LEVER_BOUNDS['ach_fixed_fee']['max']}
  impl_fee_discount_pct: 0.00 to 1.00

RESPOND WITH EXACTLY THIS JSON FORMAT (no markdown, no code fences):
{{
  "saas_strategy": "discount_remove" or "flat_monthly",
  "saas_arr_discount_pct": 0.XX,
  "saas_flat_monthly": XXX,
  "removal_pct": 0.XX,
  "cc_base_rate": 0.0XXX,
  "cc_amex_rate": 0.0XXX,
  "ach_accel_pct": 0.XX,
  "ach_accel_bps": 0.00XX,
  "ach_fixed_fee": X.XX,
  "impl_fee_discount_pct": 0.XX,
  "reasoning": "3-4 sentences explaining your strategic logic and why you believe this produces the best overall 3-year outcome."
}}

For unused fields (e.g. saas_flat_monthly if using discount_remove), set to 0.
Do NOT include any text outside the JSON object."""


def _build_scenario_context(standard, revenue_opt, margin_opt) -> str:
    """Build full context for the AI scenario agent."""

    def _full_summary(s) -> str:
        p = s.per_deal_pricing
        if p.saas_strategy == "flat_monthly":
            saas = f"Flat ${p.saas_flat_monthly:,.0f}/mo (${p.saas_flat_monthly*12:,.0f}/yr)"
            removal = "N/A (flat monthly)"
        else:
            saas = (
                f"List ${p.saas_arr_list:,.0f}, {p.saas_arr_discount_pct:.0%} discount "
                f"→ Y1 effective ${p.effective_y1_saas:,.0f}"
            )
            removal = f"{p.removal_pct:.0%} removal (75% attainment)"

        return (
            f"  SaaS: {saas}\n"
            f"  Discount Removal: {removal}\n"
            f"  Y2 Price Increase: {p.y2_price_increase_pct:.1%}\n"
            f"  CC Rates: base {p.cc_base_rate:.2%}, AMEX {p.cc_amex_rate:.2%}\n"
            f"  ACH: {p.ach_accel_pct:.0%} accelerated @ {p.ach_accel_bps:.2%} BPS, "
            f"{1-p.ach_accel_pct:.0%} fixed @ ${p.ach_fixed_fee:.2f}/txn\n"
            f"  Impl Fee: ${p.effective_impl_fee:,.0f} ({p.impl_fee_discount_pct:.0%} discount)\n"
            f"  ---\n"
            f"  Win Rate: {s.win_rate:.1%} → {s.deals_won} deals won\n"
            f"  3-Year Revenue: ${s.three_year_revenue:,.0f}\n"
            f"  3-Year Margin: ${s.three_year_margin:,.0f} ({s.three_year_margin_pct:.1%})\n"
            f"  Take Rate: {s.three_year_take_rate:.2%}\n"
            f"  Y1: ${s.cohort_yearly[1].total_revenue:,.0f} rev, "
            f"${s.cohort_yearly[1].margin:,.0f} margin ({s.cohort_yearly[1].margin_pct:.1%})\n"
            f"  Y2: ${s.cohort_yearly[2].total_revenue:,.0f} rev, "
            f"${s.cohort_yearly[2].margin:,.0f} margin ({s.cohort_yearly[2].margin_pct:.1%})\n"
            f"  Y3: ${s.cohort_yearly[3].total_revenue:,.0f} rev, "
            f"${s.cohort_yearly[3].margin:,.0f} margin ({s.cohort_yearly[3].margin_pct:.1%})"
        )

    rev_delta = revenue_opt.three_year_revenue - standard.three_year_revenue
    mar_delta = margin_opt.three_year_margin - standard.three_year_margin

    vas_note = ""
    if hasattr(standard, 'upside_detail') and standard.upside_detail:
        std_vas = sum(v for v in standard.upside_detail.values()) if standard.upside_detail else 0
        rev_vas = sum(v for v in revenue_opt.upside_detail.values()) if revenue_opt.upside_detail else 0
        mar_vas = sum(v for v in margin_opt.upside_detail.values()) if margin_opt.upside_detail else 0
        vas_note = (
            f"\n\nVAS FEE IMPACT (included in above revenue numbers):\n"
            f"  Standard ({standard.deals_won} deals): ${std_vas:,.0f}/yr in VAS fees\n"
            f"  Revenue Opt ({revenue_opt.deals_won} deals): ${rev_vas:,.0f}/yr in VAS fees\n"
            f"  $ Margin Opt ({margin_opt.deals_won} deals): ${mar_vas:,.0f}/yr in VAS fees\n"
            f"  Each additional deal = ~${rev_vas / revenue_opt.deals_won if revenue_opt.deals_won else 0:,.0f}/yr in VAS fees\n"
            f"  This means winning MORE DEALS has a massive compounding effect on total revenue."
        )

    return f"""Here are the results of three scenarios. Study them carefully — the Revenue Optimizer wins {revenue_opt.deals_won} deals and the $ Margin Optimizer wins {margin_opt.deals_won}. Notice how many more deals they win vs Standard's {standard.deals_won}. DEAL COUNT drives total value.

STANDARD (current pricing — your baseline):
{_full_summary(standard)}

REVENUE OPTIMIZED (pure revenue maximization — {revenue_opt.deals_won - standard.deals_won:+d} deals, ${rev_delta:+,.0f} rev vs Standard):
{_full_summary(revenue_opt)}

$ MARGIN OPTIMIZED (pure margin $ maximization — {margin_opt.deals_won - standard.deals_won:+d} deals, ${mar_delta:+,.0f} margin vs Standard):
{_full_summary(margin_opt)}
{vas_note}

Your target: maximize 3-year revenue + margin by winning as many deals as possible while maintaining healthy margins. The Revenue Optimizer's deal count ({revenue_opt.deals_won}) is achievable — aim for it. Propose your scenario as JSON."""


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


# ── Function-calling tool definition for GPT-4o ──────────────

_EVALUATE_TOOL = {
    "type": "function",
    "function": {
        "name": "evaluate_pricing",
        "description": (
            "Run a pricing configuration through the full financial model. "
            "Returns deals won, 3-year revenue, margin, margin %, take rate, "
            "churn rate, and year-by-year breakdown."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "saas_strategy": {
                    "type": "string",
                    "enum": ["discount_remove", "flat_monthly"],
                    "description": "SaaS pricing strategy",
                },
                "saas_arr_discount_pct": {
                    "type": "number",
                    "description": "SaaS discount 0.0-1.0 (only for discount_remove)",
                },
                "saas_flat_monthly": {
                    "type": "number",
                    "description": "Monthly SaaS price $600-$1000 (only for flat_monthly)",
                },
                "removal_pct": {
                    "type": "number",
                    "description": "Fraction of Y1 discount removed at Y2 (0.0-0.50, only for discount_remove)",
                },
                "cc_base_rate": {
                    "type": "number",
                    "description": "CC base rate (0.019-0.025)",
                },
                "cc_amex_rate": {
                    "type": "number",
                    "description": "CC AMEX rate (0.030-0.036)",
                },
                "ach_accel_pct": {
                    "type": "number",
                    "description": "Fraction on accelerated ACH (0.25-0.75)",
                },
                "ach_accel_bps": {
                    "type": "number",
                    "description": "BPS rate for accelerated ACH (0.0010-0.0049)",
                },
                "ach_fixed_fee": {
                    "type": "number",
                    "description": "Fixed fee per non-accelerated ACH txn ($2.00-$5.00)",
                },
                "impl_fee_discount_pct": {
                    "type": "number",
                    "description": "Implementation fee discount 0.0-1.0",
                },
            },
            "required": [
                "saas_strategy", "cc_base_rate", "cc_amex_rate",
                "ach_accel_pct", "ach_accel_bps", "ach_fixed_fee",
                "impl_fee_discount_pct",
            ],
        },
    },
}

_SUBMIT_TOOL = {
    "type": "function",
    "function": {
        "name": "submit_final_pricing",
        "description": (
            "Submit your final pricing recommendation after testing. "
            "Call this ONLY when you are confident this is your best option."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "saas_strategy": {"type": "string", "enum": ["discount_remove", "flat_monthly"]},
                "saas_arr_discount_pct": {"type": "number"},
                "saas_flat_monthly": {"type": "number"},
                "removal_pct": {"type": "number"},
                "cc_base_rate": {"type": "number"},
                "cc_amex_rate": {"type": "number"},
                "ach_accel_pct": {"type": "number"},
                "ach_accel_bps": {"type": "number"},
                "ach_fixed_fee": {"type": "number"},
                "impl_fee_discount_pct": {"type": "number"},
                "reasoning": {
                    "type": "string",
                    "description": "3-5 sentences explaining why this is the best overall pricing.",
                },
            },
            "required": [
                "saas_strategy", "cc_base_rate", "cc_amex_rate",
                "ach_accel_pct", "ach_accel_bps", "ach_fixed_fee",
                "impl_fee_discount_pct", "reasoning",
            ],
        },
    },
}


def _evaluate_pricing_fn(args: dict, standard, revenue_opt, margin_opt, volumes, include_float: bool) -> str:
    """Run pricing through the real model and return results with comparison to all scenarios."""
    from models.revenue_model import PricingScenario, compute_three_year_financials
    from models.win_probability import win_rate as compute_win_rate, compute_retention_factors
    from models.funnel_model import compute_funnel

    lb = cfg.LEVER_BOUNDS
    fb = cfg.SAAS_FLAT_MONTHLY_BOUNDS

    strategy = args.get("saas_strategy", "discount_remove")
    saas_list = standard.per_deal_pricing.saas_arr_list
    impl_list = standard.per_deal_pricing.impl_fee_list

    pricing = PricingScenario(
        saas_arr_discount_pct=_clamp(float(args.get("saas_arr_discount_pct", 0.30)), 0.0, 1.0),
        cc_base_rate=_clamp(float(args.get("cc_base_rate", 0.022)),
                            lb["cc_base_rate"]["min"], lb["cc_base_rate"]["max"]),
        cc_amex_rate=_clamp(float(args.get("cc_amex_rate", 0.035)),
                            lb["cc_amex_rate"]["min"], lb["cc_amex_rate"]["max"]),
        ach_accel_pct=_clamp(float(args.get("ach_accel_pct", 0.50)),
                             lb["ach_accel_pct"]["min"], lb["ach_accel_pct"]["max"]),
        ach_accel_bps=_clamp(float(args.get("ach_accel_bps", 0.0035)),
                             lb["ach_accel_bps"]["min"], lb["ach_accel_bps"]["max"]),
        ach_fixed_fee=_clamp(float(args.get("ach_fixed_fee", 2.50)),
                             lb["ach_fixed_fee"]["min"], lb["ach_fixed_fee"]["max"]),
        impl_fee_discount_pct=_clamp(float(args.get("impl_fee_discount_pct", 0.0)), 0.0, 1.0),
        hold_days_cc=2,
        saas_arr_list=saas_list,
        impl_fee_list=impl_list,
        saas_strategy=strategy,
        saas_flat_monthly=_clamp(float(args.get("saas_flat_monthly", 800)),
                                 fb["min"], fb["max"]),
        removal_pct=_clamp(float(args.get("removal_pct", 0.25)),
                           lb["removal_pct"]["min"], lb["removal_pct"]["max"]),
    )

    wp = compute_win_rate(pricing)
    ret = compute_retention_factors(pricing, 0.02)
    yearly = compute_three_year_financials(volumes, pricing, include_float=include_float)
    funnel = compute_funnel(cfg.FUNNEL_SQLS_PER_QUARTER, wp, standard.win_rate)

    deals = funnel.deals_won
    rev_3yr = sum(yearly[y].total_revenue * deals * ret[y] for y in [1, 2, 3])
    cost_3yr = sum(yearly[y].total_cost * deals * ret[y] for y in [1, 2, 3])
    margin_3yr = rev_3yr - cost_3yr
    margin_pct = margin_3yr / rev_3yr if rev_3yr > 0 else 0
    vol_3yr = sum(
        (yearly[y].total_revenue / yearly[y].take_rate * deals * ret[y])
        if yearly[y].take_rate > 0 else 0
        for y in [1, 2, 3]
    )
    take_rate = rev_3yr / vol_3yr if vol_3yr > 0 else 0

    y2_increase = pricing.y2_price_increase_pct
    annual_churn = min(0.35, 0.05 + 0.002 * y2_increase * 100) if strategy == "discount_remove" else 0.05

    lines = [
        f"Win Rate: {wp:.1%} → {deals} deals won",
        f"3-Year Revenue: ${rev_3yr:,.0f}",
        f"3-Year Margin: ${margin_3yr:,.0f} ({margin_pct:.1%})",
        f"Take Rate: {take_rate:.2%}",
        f"Y2 Price Increase: {y2_increase:.1%}",
        f"Annual Churn: {annual_churn:.1%}",
    ]
    for y in [1, 2, 3]:
        yr_rev = yearly[y].total_revenue * deals * ret[y]
        yr_margin = (yearly[y].total_revenue - yearly[y].total_cost) * deals * ret[y]
        yr_mpct = yr_margin / yr_rev if yr_rev > 0 else 0
        lines.append(
            f"Y{y}: ${yr_rev:,.0f} rev, ${yr_margin:,.0f} margin ({yr_mpct:.1%}), "
            f"SaaS/deal ${yearly[y].saas_revenue:,.0f}"
        )

    lines.append("")
    lines.append("COMPARISON TO EXISTING SCENARIOS:")
    for label, scen in [("Standard", standard), ("Revenue Opt", revenue_opt), ("$ Margin Opt", margin_opt)]:
        d_rev = rev_3yr - scen.three_year_revenue
        d_mar = margin_3yr - scen.three_year_margin
        d_deals = deals - scen.deals_won
        verdict = ""
        if d_rev < 0 and d_mar < 0:
            verdict = " ← WORSE on both rev & margin"
        elif d_rev > 0 and d_mar > 0:
            verdict = " ← BETTER on both rev & margin"
        elif d_rev > 0:
            verdict = " ← more rev, less margin"
        elif d_mar > 0:
            verdict = " ← less rev, more margin"
        lines.append(
            f"  vs {label}: {d_deals:+d} deals, ${d_rev:+,.0f} rev, "
            f"${d_mar:+,.0f} margin{verdict}"
        )

    lines.append("")
    lines.append(
        f"YOUR GOAL: Maximize 3-year revenue + margin. Target {revenue_opt.deals_won}+ deals. "
        f"Each deal also generates ~$25K/yr in VAS fees (not shown here). "
        "More deals = dramatically more total value. Prioritize win rate."
    )

    return "\n".join(lines)


_MIN_TESTS = 5
_MAX_ITERATIONS = 12
_MODEL = "gpt-4o"


def _call_openai_with_retry(client, **kwargs) -> object:
    """Call OpenAI with retry on rate-limit (429) errors."""
    import time
    for attempt in range(3):
        try:
            return client.chat.completions.create(**kwargs)
        except Exception as e:
            if "429" in str(e) and attempt < 2:
                time.sleep(10 * (attempt + 1))
                continue
            raise


def run_ai_scenario(
    standard,
    revenue_opt,
    margin_opt,
    api_key: str,
) -> tuple[dict, str]:
    """GPT-4o iteratively tests pricing via function calling, then submits its best.

    Returns (lever_dict, reasoning_string).
    Falls back to best tested config if AI doesn't formally submit.
    """
    client = OpenAI(api_key=api_key)
    context = _build_scenario_context(standard, revenue_opt, margin_opt)
    volumes = standard.per_deal_volumes
    include_float = standard.cohort_yearly[1].float_income > 0

    messages = [
        {"role": "system", "content": _AI_SCENARIO_PROMPT},
        {"role": "user", "content": (
            context + "\n\n"
            "You have an `evaluate_pricing` tool — use it to test different pricing configurations "
            "and see the real model results. Each result includes a direct comparison to all three "
            "existing scenarios so you can see exactly where you stand.\n\n"
            "GOAL: Maximize 3-year revenue + margin. The #1 lever is DEAL COUNT — each deal generates "
            "~$25K/yr in VAS fees on top of SaaS and processing revenue. Target 90-120+ deals.\n\n"
            f"You MUST test at least {_MIN_TESTS} configurations before submitting. "
            "MANDATORY: Test BOTH saas strategies at least once.\n\n"
            "STRATEGY TIPS:\n"
            "- flat_monthly at $600/mo gives same win rate as ~76% discount but only 5% churn vs ~13% — this is often the BEST strategy\n"
            "- Higher ACH rates/fees boost margin % and take rate with modest win rate impact\n"
            "- CC rates revert to standard at Y2, so Y1 CC discounts have limited cost\n"
            "- Lower discount removal = less churn = more Y2/Y3 revenue from retained deals\n"
            "- Aggressive SaaS discounting (60%+) wins many more deals — the VAS and processing revenue from extra deals more than compensates\n\n"
            "Test at least 5 configs then submit your best. Don't overthink — submit when you "
            "have a config you're confident in."
        )},
    ]

    tools = [_EVALUATE_TOOL, _SUBMIT_TOOL]
    lb = cfg.LEVER_BOUNDS
    fb = cfg.SAAS_FLAT_MONTHLY_BOUNDS

    best_tested = None
    best_tested_score = 0

    def _count_tests():
        return sum(
            1 for m in messages
            if hasattr(m, "tool_calls") and m.tool_calls
            for t in m.tool_calls if t.function.name == "evaluate_pricing"
        )

    def _tested_strategies():
        strategies = set()
        for m in messages:
            if hasattr(m, "tool_calls") and m.tool_calls:
                for t in m.tool_calls:
                    if t.function.name == "evaluate_pricing":
                        args = json.loads(t.function.arguments)
                        strategies.add(args.get("saas_strategy", "discount_remove"))
        return strategies

    def _validate_levers(fn_args):
        strategy = fn_args.get("saas_strategy", "discount_remove")
        return {
            "saas_strategy": strategy,
            "saas_arr_discount_pct": _clamp(
                float(fn_args.get("saas_arr_discount_pct", 0.30)),
                lb["saas_arr_discount_pct"]["min"], lb["saas_arr_discount_pct"]["max"],
            ),
            "saas_flat_monthly": _clamp(
                float(fn_args.get("saas_flat_monthly", 0)),
                fb["min"], fb["max"],
            ),
            "removal_pct": _clamp(
                float(fn_args.get("removal_pct", 0.25)),
                lb["removal_pct"]["min"], lb["removal_pct"]["max"],
            ),
            "cc_base_rate": _clamp(
                float(fn_args.get("cc_base_rate", 0.022)),
                lb["cc_base_rate"]["min"], lb["cc_base_rate"]["max"],
            ),
            "cc_amex_rate": _clamp(
                float(fn_args.get("cc_amex_rate", 0.035)),
                lb["cc_amex_rate"]["min"], lb["cc_amex_rate"]["max"],
            ),
            "ach_accel_pct": _clamp(
                float(fn_args.get("ach_accel_pct", 0.50)),
                lb["ach_accel_pct"]["min"], lb["ach_accel_pct"]["max"],
            ),
            "ach_accel_bps": _clamp(
                float(fn_args.get("ach_accel_bps", 0.0035)),
                lb["ach_accel_bps"]["min"], lb["ach_accel_bps"]["max"],
            ),
            "ach_fixed_fee": _clamp(
                float(fn_args.get("ach_fixed_fee", 2.50)),
                lb["ach_fixed_fee"]["min"], lb["ach_fixed_fee"]["max"],
            ),
            "impl_fee_discount_pct": _clamp(
                float(fn_args.get("impl_fee_discount_pct", 0.0)),
                lb["impl_fee_discount_pct"]["min"], lb["impl_fee_discount_pct"]["max"],
            ),
        }

    def _parse_score(result_str):
        import re as _re
        rev_m = _re.search(r"3-Year Revenue: \$([\d,]+)", result_str)
        mar_m = _re.search(r"3-Year Margin: \$([\d,]+)", result_str)
        rev = float(rev_m.group(1).replace(",", "")) if rev_m else 0
        mar = float(mar_m.group(1).replace(",", "")) if mar_m else 0
        return rev + mar

    rejections = 0
    _MAX_REJECTIONS = 2

    for _ in range(_MAX_ITERATIONS):
        response = _call_openai_with_retry(
            client,
            model=_MODEL,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=0.3,
            max_tokens=800,
        )

        msg = response.choices[0].message
        messages.append(msg)

        if not msg.tool_calls:
            break

        for tc in msg.tool_calls:
            fn_name = tc.function.name
            fn_args = json.loads(tc.function.arguments)

            if fn_name == "submit_final_pricing":
                n_tests = _count_tests()
                tested = _tested_strategies()
                missing = {"discount_remove", "flat_monthly"} - tested

                if n_tests < _MIN_TESTS or missing:
                    reasons = []
                    if n_tests < _MIN_TESTS:
                        reasons.append(
                            f"Only tested {n_tests}/{_MIN_TESTS} required configurations."
                        )
                    if missing:
                        reasons.append(
                            f"You have NOT tested: {', '.join(missing)}. Both SaaS strategies must be tested."
                        )
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": f"REJECTED: {' '.join(reasons)} Keep testing.",
                    })
                    continue

                submit_result = _evaluate_pricing_fn(
                    fn_args, standard, revenue_opt, margin_opt, volumes, include_float,
                )
                import re as _re
                _rev_m = _re.search(r"3-Year Revenue: \$([\d,]+)", submit_result)
                _mar_m = _re.search(r"3-Year Margin: \$([\d,]+) \(([\d.]+)%\)", submit_result)
                _tr_m = _re.search(r"Take Rate: ([\d.]+)%", submit_result)
                ai_rev = float(_rev_m.group(1).replace(",", "")) if _rev_m else 0
                ai_mar = float(_mar_m.group(1).replace(",", "")) if _mar_m else 0
                ai_mpct = float(_mar_m.group(2)) / 100 if _mar_m else 0
                ai_tr = float(_tr_m.group(1)) / 100 if _tr_m else 0

                _deals_m = re.search(r"(\d+) deals won", submit_result)
                ai_deals = int(_deals_m.group(1)) if _deals_m else 0

                too_few_deals = ai_deals < standard.deals_won
                if too_few_deals and rejections < _MAX_REJECTIONS:
                    rejections += 1
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": (
                            f"REJECTED ({rejections}/{_MAX_REJECTIONS} max): "
                            f"Only {ai_deals} deals — that's fewer than Standard's {standard.deals_won}. "
                            f"Revenue Optimizer achieves {revenue_opt.deals_won} deals. "
                            f"Each deal generates ~$25K/yr in VAS fees. "
                            f"Be more aggressive on SaaS discount or try flat_monthly at $600-$700/mo. "
                            "Submit your best attempt — next rejection will be accepted."
                        ),
                    })
                    continue

                validated = _validate_levers(fn_args)
                reasoning = f"Tested {n_tests} configurations across both SaaS strategies."
                return validated, reasoning

            elif fn_name == "evaluate_pricing":
                result = _evaluate_pricing_fn(fn_args, standard, revenue_opt, margin_opt, volumes, include_float)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })
                score = _parse_score(result)
                if score > best_tested_score:
                    best_tested_score = score
                    best_tested = dict(fn_args)

    if best_tested:
        validated = _validate_levers(best_tested)
        n = _count_tests()
        return validated, f"Fallback: best of {n} tested configurations (AI did not formally submit)."

    raise RuntimeError("AI did not submit a final pricing recommendation within the iteration limit.")
