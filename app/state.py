"""Builds the plain-text `state` that both Drex and the LLM baseline see."""
from __future__ import annotations

import json
from datetime import date

from .config import HISTORY_FILE, POLICY_TEXT

# US federal holidays 2025-2027 (observed dates).
HOLIDAYS = {
    "2025-01-01", "2025-01-20", "2025-02-17", "2025-05-26", "2025-06-19", "2025-07-04",
    "2025-09-01", "2025-10-13", "2025-11-11", "2025-11-27", "2025-12-25",
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-05-25", "2026-06-19", "2026-07-03",
    "2026-09-07", "2026-10-12", "2026-11-11", "2026-11-26", "2026-12-25",
    "2027-01-01", "2027-01-18", "2027-02-15", "2027-05-31", "2027-06-18", "2027-07-05",
    "2027-09-06", "2027-10-11", "2027-11-11", "2027-11-25", "2027-12-24",
}


def load_history() -> list[dict]:
    try:
        return json.loads(HISTORY_FILE.read_text())
    except Exception:
        return []


def day_label(d: str | None) -> str:
    if not d:
        return "MISSING"
    try:
        dt = date.fromisoformat(d)
    except ValueError:
        return f"{d} (unparsed)"
    tag = dt.strftime("%A")
    if d in HOLIDAYS:
        tag += ", US public holiday"
    return f"{d} ({tag})"


def build_state(fields: dict, vendor: dict, history: list[dict] | None = None) -> str:
    history = load_history() if history is None else history
    total = fields.get("total")
    items = fields.get("items") or []
    items_txt = "; ".join(
        f"{i.get('qty', 1)}x {i.get('desc', '')} {i['amount']:.2f}" if i.get("amount") is not None
        else f"{i.get('qty', 1)}x {i.get('desc', '')}"
        for i in items
    ) or "MISSING (no itemization)"
    lines = [
        "RECEIPT",
        f"Vendor: {fields.get('vendor') or 'MISSING'}",
        f"Date: {day_label(fields.get('date'))}",
        f"Total: {f'{total:.2f} ' + (fields.get('currency') or 'USD') if total is not None else 'MISSING or unreadable'}",
    ]
    if fields.get("tax") is not None:
        lines.append(f"Tax: {fields['tax']:.2f}")
    lines += [
        f"Items: {items_txt}",
        f"Vendor web check: {vendor.get('summary', 'not run')}",
        "",
        "POLICY",
        POLICY_TEXT,
        "",
        "PREVIOUS SUBMISSIONS (same employee, last 30 days)",
        " · ".join(f"{h['date']} {h['vendor']} {h['total']:.2f}" for h in history) or "none",
    ]
    return "\n".join(lines)
