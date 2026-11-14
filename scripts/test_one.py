"""One-receipt smoke test: NDI/pypdf -> Keenable -> Drex -> policy -> Qwen. Prints everything, no keys."""
import json, sys, time, traceback
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.config import env, MOCK

name = sys.argv[1] if len(sys.argv) > 1 else "r21_dinner_wine.pdf"
print("MOCK =", MOCK, "| Drex URL =", env("DREX_BASE_URL").rstrip("/") + env("DREX_PATH", "/v1/systemone"))
from app.pipeline import read
from app.drex import QUESTIONS, normalize
from app.policy import decide, confidence
from app.explain import explain
import httpx

data = (ROOT / "data" / "receipts" / name).read_bytes()
fields, vendor, state, t = read(data, name)
print("read source:", fields.get("source"), "| vendor check:", vendor.get("summary"), "|", {k: round(v) for k, v in t.items()}, "ms")
print("--- state ---\n" + state + "\n-------------")
url = env("DREX_BASE_URL").rstrip("/") + env("DREX_PATH", "/v1/systemone")
try:
    t0 = time.perf_counter()
    r = httpx.post(url, headers={"Authorization": f"Bearer {env('NACE_API_KEY')}"},
                   json={"model": env("DREX_MODEL", "drex-latest"), "state": state, "questions": QUESTIONS}, timeout=30)
    ms = (time.perf_counter() - t0) * 1000
    print("Drex HTTP", r.status_code, f"{ms:.0f} ms")
    print("raw:", r.text[:3000])
    r.raise_for_status()
    raw = r.json()
    a = normalize(raw.get("answers", raw))
    print("normalized:", json.dumps({k: (v.get("noul") if "noul" in v else v.get("choice", v.get("score"))) for k, v in a.items()}))
    d, reasons = decide(a)
    print("DECISION:", d, reasons, f"confidence {confidence(a):.2f}")
    print("Qwen:", explain(d, reasons, state))
except Exception:
    traceback.print_exc()
