"""Frontier-LLM baseline: same state, same 7 questions, asked as a JSON prompt."""
from __future__ import annotations

import json
import re
import time

from .config import MOCK, env
from .drex import CATEGORIES, QUESTIONS, RISK_LEVELS, mock_answers, normalize

SYSTEM = "You are an expense-policy checker. Answer only with a single JSON object, no prose."


def build_prompt(state: str) -> str:
    qs = []
    for k, q in QUESTIONS.items():
        if q["type"] == "noul":
            qs.append(f'- "{k}": probability 0.0-1.0 that the answer is YES. {q["instructions"]}')
        elif q["type"] == "choice":
            opts = "; ".join(f"{c} = {d}" for c, d in CATEGORIES.items())
            qs.append(f'- "{k}": one of {list(CATEGORIES)}. {q["instructions"]} ({opts})')
        else:
            levels = ", ".join(f"{i} = {n}" for i, n in enumerate(RISK_LEVELS))
            qs.append(f'- "{k}": number 0-4 ({levels}). {q["instructions"]}')
    example = ('{"over_limit": 0.1, "category": "meals", "non_reimbursable": 0.0, "duplicate": 0.0, '
               '"missing_info": 0.0, "weekend_or_holiday": 0.0, "vendor_unverified": 0.0, "risk": 1}')
    return (f"{state}\n\nAnswer these questions about the RECEIPT above:\n" + "\n".join(qs) +
            f"\n\nReturn JSON exactly like: {example}")


def parse(text: str) -> dict | None:
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    try:
        j = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(j, dict) or not all(k in j for k in QUESTIONS):
        return None
    return normalize({
        **{k: {"noul": j[k]} for k, q in QUESTIONS.items() if q["type"] == "noul"},
        "category": {"choice": j["category"]},
        "risk": {"score": j["risk"]},
    })


def ask_baseline(state: str) -> dict:
    t0 = time.perf_counter()
    if MOCK:
        return {"answers": mock_answers(state), "latency_ms": (time.perf_counter() - t0) * 1000,
                "usage": {"prompt_tokens": 0, "completion_tokens": 0}, "parse_failure": False, "mock": True}
    from openai import OpenAI
    client = OpenAI(api_key=env("DEEPINFRA_API_KEY"), base_url=env("DEEPINFRA_BASE_URL", "https://api.deepinfra.com/v1/openai"))
    kwargs = {}
    if env("BASELINE_JSON_MODE", "0") == "1":
        kwargs["response_format"] = {"type": "json_object"}
    r = client.chat.completions.create(
        model=env("BASELINE_MODEL"),
        messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": build_prompt(state)}],
        temperature=0,
        max_tokens=int(env("BASELINE_MAX_TOKENS", "2048")),
        **kwargs,
    )
    latency = (time.perf_counter() - t0) * 1000
    text = r.choices[0].message.content or ""
    answers = parse(text)
    usage = {"prompt_tokens": getattr(r.usage, "prompt_tokens", 0) or 0,
             "completion_tokens": getattr(r.usage, "completion_tokens", 0) or 0}
    return {"answers": answers, "latency_ms": latency, "usage": usage,
            "parse_failure": answers is None, "raw_text": text[:2000]}
