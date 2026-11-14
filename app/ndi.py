"""Document reading: NDI first, local fallbacks second.

extract(data, filename) -> fields dict:
  {vendor, date, total, currency, tax, items:[{qty,desc,amount}], raw_text, source}

NDI endpoint path and response shape are configurable because they must be
confirmed in the console.nace.ai docs (NDI_BASE_URL / NDI_EXTRACT_PATH).
"""
from __future__ import annotations

import base64
import email
import io
import re
from datetime import datetime
from email import policy as email_policy

import httpx

from .config import MOCK, env

EMPTY = {"vendor": None, "date": None, "total": None, "currency": "USD",
         "tax": None, "items": [], "raw_text": ""}


# ---------------------------------------------------------------- public API
def extract(data: bytes, filename: str) -> dict:
    name = filename.lower()
    if name.endswith(".eml"):
        data, filename, text = _unwrap_email(data, filename)
        if text is not None and data is None:
            return {**_parse_text(text), "source": "email-body"}
        name = filename.lower()

    if env("NDI_BASE_URL") and not MOCK:
        try:
            return {**_ndi(data, filename), "source": "ndi"}
        except Exception as e:  # fall through to local parsing
            print(f"[ndi] falling back to local parser: {e}")

    if name.endswith(".pdf"):
        return {**_parse_text(_pdf_text(data)), "source": "pypdf"}
    if name.endswith((".txt", ".md")):
        return {**_parse_text(data.decode("utf-8", "ignore")), "source": "text"}
    if name.endswith((".jpg", ".jpeg", ".png", ".webp", ".heic")):
        text = _vision_ocr(data, filename)
        return {**_parse_text(text), "source": "vision" if text else "none"}
    return {**EMPTY, "source": "none"}


# ---------------------------------------------------------------- NDI
def _ndi(data: bytes, filename: str) -> dict:
    url = env("NDI_BASE_URL").rstrip("/") + env("NDI_EXTRACT_PATH", "/v1/extract")
    r = httpx.post(
        url,
        headers={"Authorization": f"Bearer {env('NACE_API_KEY')}"},
        files={"file": (filename, data)},
        data={"schema": "receipt"},
        timeout=60,
    )
    r.raise_for_status()
    return _normalize_ndi(r.json())


def _pick(d: dict, *keys):
    for k in keys:
        if isinstance(d, dict) and d.get(k) not in (None, ""):
            return d[k]
    return None


def _normalize_ndi(j: dict) -> dict:
    """Accept a few plausible shapes; adjust once the real NDI response is known."""
    f = _pick(j, "fields", "extracted", "data", "result") or j
    if isinstance(f, list):  # [{name, value}] style
        f = {x.get("name") or x.get("key"): x.get("value") for x in f}
    items = _pick(f, "line_items", "items", "lineItems") or []
    norm_items = []
    for it in items:
        if isinstance(it, dict):
            norm_items.append({
                "qty": _num(_pick(it, "quantity", "qty")) or 1,
                "desc": str(_pick(it, "description", "desc", "name") or ""),
                "amount": _num(_pick(it, "amount", "total", "price")),
            })
    text = _pick(j, "text", "raw_text", "markdown", "content") or ""
    out = {
        "vendor": _pick(f, "vendor", "merchant", "vendor_name", "merchant_name"),
        "date": _norm_date(str(_pick(f, "date", "transaction_date", "invoice_date") or "")),
        "total": _num(_pick(f, "total", "total_amount", "amount_due", "grand_total")),
        "currency": _pick(f, "currency") or "USD",
        "tax": _num(_pick(f, "tax", "tax_amount", "vat")),
        "items": norm_items,
        "raw_text": text,
    }
    # If NDI gave text but missed fields, fill the gaps from the text.
    if text:
        local = _parse_text(text)
        for k in ("vendor", "date", "total", "tax"):
            out[k] = out[k] if out[k] not in (None, "") else local[k]
        out["items"] = out["items"] or local["items"]
    return out


# ---------------------------------------------------------------- fallbacks
def _pdf_text(data: bytes) -> str:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    return "\n".join((p.extract_text() or "") for p in reader.pages)


def _unwrap_email(data: bytes, filename: str):
    msg = email.message_from_bytes(data, policy=email_policy.default)
    for part in msg.iter_attachments():
        fn = part.get_filename() or ""
        if fn.lower().endswith((".pdf", ".jpg", ".jpeg", ".png")):
            return part.get_payload(decode=True), fn, None
    body = msg.get_body(preferencelist=("plain", "html"))
    text = body.get_content() if body else ""
    text = re.sub(r"<[^>]+>", " ", text)
    return None, filename, text


def _vision_ocr(data: bytes, filename: str) -> str:
    model = env("VISION_MODEL")
    if not (model and env("DEEPINFRA_API_KEY")) or MOCK:
        return ""
    from openai import OpenAI
    client = OpenAI(api_key=env("DEEPINFRA_API_KEY"), base_url=env("DEEPINFRA_BASE_URL"))
    mime = "image/png" if filename.lower().endswith(".png") else "image/jpeg"
    b64 = base64.b64encode(data).decode()
    r = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": [
            {"type": "text", "text": "Transcribe this receipt exactly as plain text, one line per printed line."},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
        ]}],
        max_tokens=1500,
    )
    return r.choices[0].message.content or ""


# ---------------------------------------------------------------- text parser
_ITEM = re.compile(r"^\s*(\d+)\s*[xX×]\s+(.+?)\s+\$?(-?\d[\d,]*\.\d{2})\s*$")
_TOTAL = re.compile(r"^\s*(?:grand\s+)?total(?:\s+due)?\b[^\d\n]*?\$?\s*(\d[\d,]*\.\d{2})", re.I)
_TAX = re.compile(r"^\s*(?:sales\s+)?tax\b[^\d\n]*?\$?\s*(\d[\d,]*\.\d{2})", re.I)
_SKIP_VENDOR = re.compile(r"receipt|invoice|tax|date|order|^\W*$", re.I)


def _parse_text(text: str) -> dict:
    lines = [l.rstrip() for l in (text or "").splitlines()]
    out = {**EMPTY, "items": [], "raw_text": text or ""}

    for l in lines:
        s = l.strip()
        if s and not _SKIP_VENDOR.search(s) and not re.search(r"\d{3,}", s):
            out["vendor"] = s.title() if s.isupper() else s
            break
    m = re.search(r"(?im)^\s*vendor:\s*(.+)$", text or "")
    if m:
        out["vendor"] = m.group(1).strip()

    out["date"] = _norm_date(text or "")

    for l in lines:
        if re.match(r"^\s*sub\s*-?total", l, re.I):
            continue
        m = _TOTAL.match(l)
        if m:
            out["total"] = _num(m.group(1))
        m = _TAX.match(l)
        if m:
            out["tax"] = _num(m.group(1))
        m = _ITEM.match(l)
        if m:
            out["items"].append({"qty": int(m.group(1)), "desc": m.group(2).strip(),
                                 "amount": _num(m.group(3))})
    cur = re.search(r"\b(USD|EUR|GBP|CAD|INR|JPY)\b", text or "")
    if cur:
        out["currency"] = cur.group(1)
    return out


def _num(v):
    if v is None:
        return None
    try:
        return round(float(str(v).replace(",", "").replace("$", "")), 2)
    except ValueError:
        return None


def _norm_date(s: str) -> str | None:
    m = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", s)
    if m:
        return m.group(0)
    m = re.search(r"\b(\d{1,2})/(\d{1,2})/(20\d{2})\b", s)
    if m:
        return f"{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    m = re.search(r"\b([A-Z][a-z]{2,8})\.? (\d{1,2}),? (20\d{2})\b", s)
    if m:
        for fmt in ("%b %d %Y", "%B %d %Y"):
            try:
                return datetime.strptime(f"{m.group(1)[:3] if fmt == '%b %d %Y' else m.group(1)} {m.group(2)} {m.group(3)}", fmt).strftime("%Y-%m-%d")
            except ValueError:
                pass
    return None
