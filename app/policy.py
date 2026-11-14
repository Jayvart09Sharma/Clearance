"""Policy engine: plain Python, no model. Every decision traces to a probability and a threshold."""
from __future__ import annotations

THRESHOLDS = {
    "non_reimbursable": 0.7,
    "duplicate": 0.7,
    "over_limit": 0.6,
    "missing_info": 0.6,
    "weekend_or_holiday": 0.8,
    "vendor_unverified": 0.7,
}
REJECT_DUPLICATE = 0.85
REJECT_NON_REIMBURSABLE = 0.9
RISK_FLAG = 2.5

REASONS = {
    "non_reimbursable": "Contains non-reimbursable items",
    "duplicate": "Looks like a duplicate submission",
    "over_limit": "Over category limit",
    "missing_info": "Missing required information",
    "weekend_or_holiday": "Weekend or holiday purchase",
    "vendor_unverified": "Vendor could not be verified",
}


def decide(a: dict) -> tuple[str, list[str]]:
    p = lambda k: a[k]["noul"]
    reasons = [REASONS[k] for k, t in THRESHOLDS.items() if p(k) > t]

    if p("duplicate") > REJECT_DUPLICATE or p("non_reimbursable") > REJECT_NON_REIMBURSABLE:
        return "reject", reasons
    if reasons or a["risk"]["score"] >= RISK_FLAG:
        if not reasons:
            reasons.append("High overall risk score")
        return "flag", reasons
    return "approve", reasons


def confidence(a: dict) -> float:
    """How sure the yes/no checks are, on average (distance from 50/50)."""
    ps = [a[k]["noul"] for k in THRESHOLDS]
    return sum(max(p, 1 - p) for p in ps) / len(ps)
