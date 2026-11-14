"""Drex (System 1): one /v1/systemone call, seven typed questions.

Verify the exact URL and auth header in the console.nace.ai docs; both are
configurable through DREX_BASE_URL / DREX_PATH / DREX_AUTH_HEADER.
"""
from __future__ import annotations

import re
import time

import httpx

from .config import LIMITS, MOCK, env

CATEGORIES = {
    "meals": "Restaurants, cafes, food delivery",
    "travel": "Flights, hotels, taxis, rideshare, fuel, parking",
    "software": "SaaS subscriptions, licenses, cloud services",
    "office": "Supplies, equipment, furniture",
    "other": "Anything else",
}
RISK_LEVELS = ["Clean", "Low risk", "Some concern", "High risk", "Almost certainly a violation"]

QUESTIONS = {
    "over_limit": {
        "type": "noul",
        "instructions": "Is the total above the per-category limit stated in the POLICY section?",
    },
    "category": {
        "type": "choice",
        "instructions": "Which expense category does this receipt belong to?",
        "criteria": CATEGORIES,
    },
    "non_reimbursable": {
        "type": "noul",
        "instructions": "Does the receipt contain alcohol, tobacco, gifts, personal items or other items the POLICY says are not reimbursable?",
    },
    "duplicate": {
        "type": "noul",
        "instructions": "Does this receipt match one in PREVIOUS SUBMISSIONS (same vendor, same amount, same or adjacent date)?",
    },
    "missing_info": {
        "type": "noul",
        "instructions": "Is any required field missing or unreadable: vendor, date, total, or itemization?",
    },
    "weekend_or_holiday": {
        "type": "noul",
        "instructions": "Was this purchase made on a weekend or public holiday?",
    },
    "vendor_unverified": {
        "type": "noul",
        "instructions": "Does the Vendor web check say the vendor could not be found or verified as a real business?",
    },
    "risk": {
        "type": "score",
        "instructions": "Overall, how likely is this expense to violate policy or be fraudulent?",
        "criteria": RISK_LEVELS,
    },
}


def ask_drex(state: str) -> dict:
    t0 = time.perf_counter()
    if MOCK:
        answers = mock_answers(state)
        return {"answers": answers, "latency_ms": (time.perf_counter() - t0) * 1000, "mock": True}

    header = env("DREX_AUTH_HEADER", "Authorization")
    token = env("NACE_API_KEY")
    headers = {header: f"Bearer {token}" if header.lower() == "authorization" else token}
    r = httpx.post(
        env("DREX_BASE_URL").rstrip("/") + env("DREX_PATH", "/v1/systemone"),
        headers=headers,
        json={"model": env("DREX_MODEL", "drex-latest"), "state": state, "questions": QUESTIONS},
        timeout=30,
    )
    latency = (time.perf_counter() - t0) * 1000
    r.raise_for_status()
    raw = r.json()
    return {"answers": normalize(raw.get("answers", raw)), "latency_ms": latency,
            "usage": raw.get("usage"), "server_ms": raw.get("evaluation_time_ms"),
            "served_model": raw.get("model"), "raw": raw}


# ------------------------------------------------------------ normalization
def _f(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def normalize(ans: dict) -> dict:
    """Coerce Drex (or LLM) answers into the README shape, tolerating variants."""
    out = {}
    for key, q in QUESTIONS.items():
        a = ans.get(key, {})
        if q["type"] == "noul":
            if isinstance(a, dict):
                p = a.get("noul", a.get("probability", a.get("yes", a.get("p"))))
                if p is None and isinstance(a.get("probabilities"), dict):
                    p = a["probabilities"].get("yes", a["probabilities"].get("true"))
            else:
                p = a
            if isinstance(p, bool):
                p = 1.0 if p else 0.0
            out[key] = {"type": "noul", "noul": min(1.0, max(0.0, _f(p)))}
        elif q["type"] == "choice":
            if isinstance(a, str):
                a = {"choice": a}
            probs = a.get("probabilities") or {}
            choice = a.get("choice") or (max(probs, key=probs.get) if probs else "other")
            choice = str(choice).lower().strip()
            if choice not in CATEGORIES:
                choice = "other"
            conf = _f(a.get("confidence", probs.get(choice, 1.0)), 1.0)
            out[key] = {"type": "choice", "choice": choice, "confidence": conf, "probabilities": probs}
        else:
            if not isinstance(a, dict):
                a = {"score": a}
            score = a.get("score")
            if isinstance(score, str) and score in RISK_LEVELS:
                score = RISK_LEVELS.index(score)
            out[key] = {"type": "score", "score": _f(score), "confidence": _f(a.get("confidence"), 1.0),
                        "probabilities": a.get("probabilities") or {}}
    return out


# ------------------------------------------------------------ offline mock
_CAT_WORDS = {
    "travel": r"air|flight|hotel|inn|uber|lyft|taxi|shell|chevron|fuel|parking|marriott|hilton|delta|united|southwest|amtrak",
    "software": r"web services|ec2|notion|slack|github|figma|aws|cloud|saas|subscription|license|zoom|openai|vercel|atlassian",
    "office": r"staples|office depot|monitor|display|depot|ikea|paper|toner|monitor|chair|desk|keyboard|best buy",
    "meals": r"steakhouse|entree|bowl|caesar|nopa|coffee|cafe|restaurant|grill|pizza|sushi|bistro|kitchen|latte|burger|taco|doordash|chipotle|diner|bar",
}


def mock_answers(state: str) -> dict:
    """Keyword heuristics. ONLY for building the UI offline; never benchmark numbers."""
    s = state.lower()
    receipt = s.split("policy")[0]
    cat = "other"
    for c, pat in _CAT_WORDS.items():
        if re.search(rf"\b(?:{pat})\b", receipt):
            cat = c
            break
    m = re.search(r"total: ([\d.]+)", receipt)
    total = float(m.group(1)) if m else None
    over = 0.95 if total is not None and total > LIMITS[cat] else 0.03
    nonr = 0.96 if re.search(r"\b(?:wine|beer|vodka|whiskey|tequila|cocktail|cigars?|tobacco|cigarettes?|gift card|perfume)\b", receipt) else 0.02
    missing = 0.93 if "missing" in receipt else 0.03
    wk = 0.97 if re.search(r"\((saturday|sunday)|holiday", receipt) else 0.02
    dup = 0.03
    vm = re.search(r"vendor: (.+)", receipt)
    hist = s.split("previous submissions")[-1]
    if vm and total is not None:
        vendor = vm.group(1).strip()
        if vendor in hist and f"{total:.2f}" in hist:
            dup = 0.95
    fake = "no matching business" in receipt
    unver = 0.95 if fake else 0.03
    risk = 0.4 + 2.2 * max(over, nonr, dup, missing) + (2.3 if fake else 0) + 0.8 * wk
    return normalize({
        "over_limit": {"noul": over}, "non_reimbursable": {"noul": nonr},
        "duplicate": {"noul": dup}, "missing_info": {"noul": missing},
        "weekend_or_holiday": {"noul": wk},
        "vendor_unverified": {"noul": unver},
        "category": {"choice": cat, "confidence": 0.9},
        "risk": {"score": min(4.0, risk), "confidence": 0.8},
    })
