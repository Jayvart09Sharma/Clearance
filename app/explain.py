"""System 2: Qwen on DeepInfra writes one sentence for the employee. Never decides."""
from __future__ import annotations

import re

from .config import MOCK, env


def _client():
    from openai import OpenAI
    return OpenAI(api_key=env("DEEPINFRA_API_KEY"), base_url=env("DEEPINFRA_BASE_URL", "https://api.deepinfra.com/v1/openai"))


def explain(decision: str, reasons: list[str], state: str) -> str | None:
    if decision == "approve":
        return None
    if MOCK or not env("DEEPINFRA_API_KEY"):
        return f"This receipt was {'rejected' if decision == 'reject' else 'flagged'}: {'; '.join(reasons).lower() or 'high risk score'}."
    try:
        r = _client().chat.completions.create(
            model=env("EXPLAIN_MODEL", "Qwen/Qwen3.8-27B"),
            messages=[
                {"role": "system", "content": "You explain expense-policy decisions to employees. "
                 "Write exactly one friendly, specific sentence (max 30 words). Mention the item or amount "
                 "that caused it. Do not change the decision. No preamble."},
                {"role": "user", "content": f"Decision: {decision}\nReasons: {', '.join(reasons)}\n\n{state}\n\n/no_think"},
            ],
            max_tokens=1000,
            temperature=0.2,
        )
        text = r.choices[0].message.content or ""
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip().strip('"')
        if text:
            return text
        print("[explain] empty reply from model, using fallback sentence")
    except Exception as e:
        print(f"[explain] {e}")
    return f"This receipt was {'rejected' if decision == 'reject' else 'flagged'}: {'; '.join(reasons).lower() or 'high risk score'}."
