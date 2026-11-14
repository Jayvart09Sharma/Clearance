"""Is the vendor a real business? One Keenable web search, keyless by default."""
from __future__ import annotations

import re
from functools import lru_cache

from .config import MOCK, env

# Used only in MOCK mode, so the offline demo still has a fake vendor to catch.
_MOCK_FAKE = re.compile(r"zentrova|brightpath meridian", re.I)


@lru_cache(maxsize=512)
def check_vendor(vendor: str | None) -> dict:
    if not vendor:
        return {"verified": False, "matches": 0, "summary": "no vendor name on the receipt"}
    if MOCK:
        fake = bool(_MOCK_FAKE.search(vendor))
        return {"verified": not fake, "matches": 0 if fake else 3, "mock": True,
                "summary": "no matching business found (mock)" if fake else "verified business (mock)"}
    try:
        from keenable import Keenable
        client = Keenable(env("KEENABLE_API_KEY") or None)
        results = list(client.search(f'"{vendor}" business', max_results=5,
                                     snippet_max_length=300, mode="realtime"))
    except Exception as e:
        return {"verified": None, "matches": 0, "summary": f"vendor lookup unavailable ({type(e).__name__})"}

    # Strict match: the vendor's name (minus generic suffixes) must appear as a phrase in a result.
    generic = {"co", "inc", "llc", "ltd", "corp", "corporation", "company", "holdings", "group"}
    norm = lambda x: " ".join(re.findall(r"[a-z0-9]+", x.lower().replace("'", "")))
    words = norm(vendor).split()
    while len(words) > 1 and words[-1] in generic:  # drop trailing "Co", "LLC", ...
        words.pop()
    core = " ".join(words)
    compact = core.replace(" ", "")
    matches = 0
    top = []
    for r in results:
        hay = norm(f"{r.title or ''} {r.url or ''} {(r.snippet or '')[:300]}")
        if core in hay or compact in hay.replace(" ", ""):
            matches += 1
            top.append(r.url)
    verified = matches >= 1
    return {
        "verified": verified,
        "matches": matches,
        "urls": top[:3],
        "summary": (f"verified business (Keenable, {matches} matching results)" if verified
                    else "no matching business found on the web (Keenable)"),
    }
