"""Shared settings. Everything comes from .env so nothing secret lives in code."""
from __future__ import annotations
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "data"
RECEIPTS_DIR = DATA_DIR / "receipts"
HISTORY_FILE = DATA_DIR / "history.json"
BENCH_DIR = ROOT / "bench"
WEB_DIR = ROOT / "web"


def env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def env_float(key: str, default: float | None = None) -> float | None:
    v = env(key)
    if not v:
        return default
    try:
        return float(v)
    except ValueError:
        return default


# MOCK=1 runs Drex/NDI/LLM offline with heuristics so the UI can be developed
# without keys. Every result produced this way is tagged "mock": true.
MOCK = env("MOCK", "0") == "1"

# Company policy. The same text is sent to Drex and to the LLM baseline.
LIMITS = {"meals": 75.0, "travel": 500.0, "software": 300.0, "office": 200.0, "other": 100.0}
NOT_REIMBURSABLE = ["alcohol", "tobacco", "gifts", "personal items"]

POLICY_TEXT = (
    f"Meals limit {LIMITS['meals']:.0f} USD per receipt. Travel limit {LIMITS['travel']:.0f}. "
    f"Software limit {LIMITS['software']:.0f}. Office {LIMITS['office']:.0f}. "
    f"Other {LIMITS['other']:.0f}.\n"
    f"Not reimbursable: {', '.join(NOT_REIMBURSABLE)}.\n"
    "Required fields: vendor, date, total, itemization."
)
