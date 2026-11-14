"""receipt bytes -> NDI -> Keenable -> Drex -> policy -> (Qwen)."""
from __future__ import annotations

import time

from .drex import ask_drex
from .explain import explain
from .keenable_check import check_vendor
from .ndi import extract
from .policy import confidence, decide
from .state import build_state


def read(data: bytes, filename: str) -> tuple[dict, dict, str, dict]:
    t = {}
    t0 = time.perf_counter()
    fields = extract(data, filename)
    t["read_ms"] = (time.perf_counter() - t0) * 1000
    t0 = time.perf_counter()
    vendor = check_vendor(fields.get("vendor"))
    t["vendor_ms"] = (time.perf_counter() - t0) * 1000
    return fields, vendor, build_state(fields, vendor), t


def review(data: bytes, filename: str, with_explanation: bool = True) -> dict:
    fields, vendor, state, timings = read(data, filename)
    drex = ask_drex(state)
    answers = drex["answers"]
    decision, reasons = decide(answers)
    t0 = time.perf_counter()
    explanation = explain(decision, reasons, state) if with_explanation else None
    timings["explain_ms"] = (time.perf_counter() - t0) * 1000
    fields = {k: v for k, v in fields.items() if k != "raw_text"}
    return {
        "decision": decision,
        "reasons": reasons,
        "explanation": explanation,
        "confidence": confidence(answers),
        "fields": fields,
        "vendor_check": vendor,
        "answers": answers,
        "latency_ms": drex["latency_ms"],
        "timings": timings,
        "state": state,
        "mock": bool(drex.get("mock")),
    }
