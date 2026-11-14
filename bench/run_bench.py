"""Drex vs a frontier LLM on the same labeled receipts and the same NDI output.

    python bench/run_bench.py              # uses bench/cache.json for reruns
    python bench/run_bench.py --fresh      # ignore the cache, call everything again
    python bench/run_bench.py --only drex  # run one pipeline

Writes bench/results.json, which /benchmark renders.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.baseline import ask_baseline  # noqa: E402
from app.config import BENCH_DIR, MOCK, RECEIPTS_DIR, env, env_float  # noqa: E402
from app.drex import ask_drex  # noqa: E402
from app.pipeline import read  # noqa: E402
from app.policy import THRESHOLDS, decide  # noqa: E402

CACHE = BENCH_DIR / ("cache.mock.json" if MOCK else "cache.v2.json")  # v2: 8 questions + strict vendor check  # never mix mock and real answers
VIOLATION_CHECK = {  # label name -> Drex question
    "over_limit": "over_limit",
    "non_reimbursable": "non_reimbursable",
    "duplicate": "duplicate",
    "missing_info": "missing_info",
    "weekend": "weekend_or_holiday",
    "fake_vendor": "vendor_unverified",
}


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()[:16]


def pct(xs, q):
    if not xs:
        return None
    xs = sorted(xs)
    k = (len(xs) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def caught(violation: str, answers: dict | None, decision: str) -> bool:
    if answers is None:
        return False
    q = VIOLATION_CHECK.get(violation)
    if q is None:
        return decision != "approve"
    return answers[q]["noul"] > THRESHOLDS[q]


def cost_per_1k(pipeline: str, rows: list[dict]) -> float | None:
    """USD per 1,000 receipts from measured tokens x published price (set prices in .env)."""
    if pipeline == "baseline":
        pin, pout = env_float("BASELINE_PRICE_IN_PER_M"), env_float("BASELINE_PRICE_OUT_PER_M")
        if pin is None or pout is None:
            return None
        tot = sum(r["usage"]["prompt_tokens"] * pin + r["usage"]["completion_tokens"] * pout for r in rows) / 1e6
        return tot / len(rows) * 1000 if rows else None
    per_call = env_float("DREX_PRICE_PER_1K_CALLS")
    if per_call is not None:
        return per_call
    pin = env_float("DREX_PRICE_IN_PER_M")
    if pin is None:
        return None
    toks = [((r.get("usage") or {}).get("prompt_tokens") or (r.get("usage") or {}).get("input_tokens") or 0) for r in rows]
    if not any(toks):
        return None
    return sum(toks) * pin / 1e6 / len(rows) * 1000


def run_pipeline(name: str, fn, state: str, cache: dict, key: str, fresh: bool) -> dict:
    ck = f"{name}:{key}"
    if not fresh and ck in cache:
        return cache[ck]
    try:
        out = fn(state)
    except Exception as e:
        out = {"answers": None, "latency_ms": None, "error": f"{type(e).__name__}: {e}", "parse_failure": False}
    out.pop("raw", None)
    if not out.get("error"):
        cache[ck] = out
    return out


def summarize(rows: list[dict], labels: list[dict], pipeline: str) -> dict:
    n = len(rows)
    dec_ok = sum(r["decision"] == l["expected_decision"] for r, l in zip(rows, labels))
    cat_ok = sum(r["category"] == l["expected_category"] for r, l in zip(rows, labels))
    planted = [(v, r) for r, l in zip(rows, labels) for v in filter(None, l["violations"].split(";"))]
    recall = sum(r["caught"][v] for v, r in planted)
    clean = [(r, l) for r, l in zip(rows, labels) if not l["violations"]]
    false_alarms = sum(r["decision"] != "approve" for r, _ in clean)
    lat = [r["latency_ms"] for r in rows if r["latency_ms"] is not None]
    return {
        "n": n,
        "decision_accuracy": dec_ok / n if n else None,
        "category_accuracy": cat_ok / n if n else None,
        "violation_recall": recall / len(planted) if planted else None,
        "violations_planted": len(planted),
        "violations_caught": recall,
        "false_alarm_rate": false_alarms / len(clean) if clean else None,
        "latency_median_ms": statistics.median(lat) if lat else None,
        "latency_p95_ms": pct(lat, 0.95),
        "parse_failures": sum(bool(r.get("parse_failure")) for r in rows),
        "errors": sum(bool(r.get("error")) for r in rows),
        "cost_per_1k_usd": cost_per_1k(pipeline, rows),
        "server_median_ms": statistics.median([r["server_ms"] for r in rows if r.get("server_ms")]) if any(r.get("server_ms") for r in rows) else None,
        "tokens_in_total": sum((r["usage"].get("prompt_tokens") or r["usage"].get("input_tokens") or 0) for r in rows),
        "tokens_out_total": sum((r["usage"].get("completion_tokens") or r["usage"].get("output_tokens") or 0) for r in rows),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--only", choices=["drex", "baseline"])
    args = ap.parse_args()

    labels = list(csv.DictReader(open(BENCH_DIR / "labels.csv", newline="")))
    labels = [l for l in labels if (RECEIPTS_DIR / l["file"]).exists()]
    cache = {} if args.fresh or not CACHE.exists() else json.loads(CACHE.read_text())
    pipelines = {"drex": ask_drex, "baseline": ask_baseline}
    if args.only:
        pipelines = {args.only: pipelines[args.only]}

    per = {p: [] for p in pipelines}
    for i, l in enumerate(labels, 1):
        data = (RECEIPTS_DIR / l["file"]).read_bytes()
        key = sha(data)
        if not args.fresh and f"state:{key}" in cache:
            state = cache[f"state:{key}"]
        else:
            _, _, state, _ = read(data, l["file"])  # NDI + Keenable once, shared by both pipelines
            cache[f"state:{key}"] = state
        for p, fn in pipelines.items():
            out = run_pipeline(p, fn, state, cache, key, args.fresh)
            a = out.get("answers")
            decision, reasons = decide(a) if a else ("error", [])
            per[p].append({
                "file": l["file"],
                "decision": decision,
                "reasons": reasons,
                "category": a["category"]["choice"] if a else None,
                "latency_ms": out.get("latency_ms"),
                "server_ms": out.get("server_ms"),
                "usage": out.get("usage") or {"prompt_tokens": 0, "completion_tokens": 0},
                "parse_failure": bool(out.get("parse_failure")),
                "error": out.get("error"),
                "caught": {v: caught(v, a, decision) for v in VIOLATION_CHECK},
            })
            mark = "ok " if decision == l["expected_decision"] else "MISS"
            lat = out.get("latency_ms")
            print(f"[{i:>2}/{len(labels)}] {p:<8} {mark} {l['file']:<28} {decision:<8} "
                  f"(expected {l['expected_decision']:<7}) {f'{lat:,.0f} ms' if lat else out.get('error', '')}")
        CACHE.write_text(json.dumps(cache, indent=1))

    summary = {p: summarize(rows, labels, p) for p, rows in per.items()}
    head = {}
    if "drex" in summary and "baseline" in summary:
        d, b = summary["drex"], summary["baseline"]
        if d["latency_median_ms"] and b["latency_median_ms"]:
            head["speedup"] = b["latency_median_ms"] / d["latency_median_ms"]
        if d["cost_per_1k_usd"] and b["cost_per_1k_usd"]:
            head["cost_ratio"] = b["cost_per_1k_usd"] / d["cost_per_1k_usd"]

    results = {
        "meta": {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "n_receipts": len(labels),
            "drex_model": env("DREX_MODEL", "drex-latest"),
            "baseline_model": env("BASELINE_MODEL") or None,
            "mock": MOCK,
        },
        "summary": summary,
        "headline": head,
        "labels": labels,
        "rows": per,
    }
    (BENCH_DIR / "results.json").write_text(json.dumps(results, indent=2))
    print("\n" + json.dumps({"summary": summary, "headline": head}, indent=2))
    if MOCK:
        print("\nMOCK=1: these numbers are NOT real. Unset MOCK and rerun before you report anything.")


if __name__ == "__main__":
    main()
