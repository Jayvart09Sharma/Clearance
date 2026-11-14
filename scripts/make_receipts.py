"""Generate the synthetic benchmark set: PDFs (+1 .eml), bench/labels.csv, data/history.json.

~64% clean receipts, ~36% with planted violations. Run:  python scripts/make_receipts.py
Real receipts can be added alongside; just add a row for each to bench/labels.csv.
"""
from __future__ import annotations

import csv
import json
import sys
from datetime import date
from email.message import EmailMessage
from pathlib import Path

from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.state import HOLIDAYS  # noqa: E402

OUT = ROOT / "data" / "receipts"
TAX = {"meals": 0.0875, "office": 0.0875, "travel": 0.0, "software": 0.0, "other": 0.0875}

HISTORY = [
    {"date": "2026-10-28", "vendor": "Sweetgreen", "total": 19.60},
    {"date": "2026-10-30", "vendor": "Shell", "total": 51.20},
    {"date": "2026-11-01", "vendor": "Uber", "total": 23.10},
    {"date": "2026-11-03", "vendor": "Notion", "total": 10.00},
]

# (file, vendor, address, date, time, category, items[(qty, desc, unit)], violations, opts)
R = [
    # ---------------- clean ----------------
    ("r01_blue_bottle", "Blue Bottle Coffee", "300 Webster St, Oakland CA", "2026-11-10", "08:41", "meals",
     [(2, "Latte", 6.00), (1, "Pastry", 6.50)], [], {}),
    ("r02_uber", "Uber", "Trip: SFO to 2nd St", "2026-11-09", "18:12", "travel",
     [(1, "UberX trip", 31.70), (1, "Booking fee", 2.50)], [], {}),
    ("r03_marriott", "San Jose Marriott", "301 S Market St, San Jose CA", "2026-11-05", "11:02", "travel",
     [(2, "Room night", 169.00), (2, "Occupancy tax", 25.50)], [], {}),
    ("r04_delta_flight", "Delta Air Lines", "Confirmation GX7Q2M", "2026-11-04", "09:15", "travel",
     [(1, "SJC-SEA Main Cabin", 368.20), (1, "Taxes and fees", 44.40)], [], {}),
    ("r05_shell", "Shell", "1200 El Camino Real, Santa Clara CA", "2026-11-12", "07:55", "travel",
     [(1, "Unleaded 12.4 gal", 58.40)], [], {}),
    ("r06_sfo_parking", "SFO Long Term Parking", "San Francisco International Airport", "2026-11-06", "20:30", "travel",
     [(3, "Day parking", 24.00)], [], {}),
    ("r07_notion", "Notion", "Notion Labs Inc, San Francisco CA", "2026-11-02", "00:00", "software",
     [(1, "Plus plan, 8 seats, monthly", 96.00)], [], {"invoice": True}),
    ("r08_github", "GitHub", "GitHub Inc, San Francisco CA", "2026-11-02", "00:00", "software",
     [(1, "Team plan, 21 seats", 84.00)], [], {"invoice": True}),
    ("r09_figma", "Figma", "Figma Inc, San Francisco CA", "2026-10-27", "00:00", "software",
     [(1, "Professional, 12 editors", 180.00)], [], {"invoice": True}),
    ("r10_aws", "Amazon Web Services", "AWS Inc, Seattle WA", "2026-11-03", "00:00", "software",
     [(1, "EC2 usage", 161.12), (1, "S3 storage", 51.25)], [], {"invoice": True}),
    ("r11_staples", "Staples", "1 Main St, Mountain View CA", "2026-11-09", "13:20", "office",
     [(2, "Printer paper ream", 9.99), (1, "Gel pens 12 pack", 12.49), (1, "Stapler", 10.00)], [], {}),
    ("r12_ikea", "IKEA", "1700 E Bayshore Rd, East Palo Alto CA", "2026-10-29", "16:45", "office",
     [(1, "MARKUS office chair", 137.00)], [], {}),
    ("r13_office_depot", "Office Depot", "2400 Stevens Creek Blvd, San Jose CA", "2026-11-05", "10:05", "office",
     [(1, "HP 67 toner cartridge", 81.84)], [], {}),
    ("r14_chipotle", "Chipotle", "2 N Market St, San Jose CA", "2026-11-12", "12:30", "meals",
     [(1, "Burrito bowl", 11.95), (1, "Chips and guac", 5.25), (1, "Iced tea", 4.75)], [], {}),
    ("r15_sweetgreen", "Sweetgreen", "180 University Ave, Palo Alto CA", "2026-11-04", "12:52", "meals",
     [(2, "Harvest bowl", 14.45)], [], {}),
    ("r16_doordash", "DoorDash", "Order from Pho Ha Noi", "2026-11-06", "12:10", "meals",
     [(4, "Pho combo", 13.50), (1, "Delivery fee", 3.99)], [], {}),
    ("r17_lyft", "Lyft", "Ride: Caltrain to office", "2026-11-13", "08:20", "travel",
     [(1, "Standard ride", 25.40), (1, "Service fee", 2.50)], [], {}),
    ("r18_amtrak", "Amtrak", "Capitol Corridor, San Jose to Sacramento", "2026-10-30", "06:40", "travel",
     [(2, "Coach fare", 48.00)], [], {}),
    ("r19_zoom", "Zoom", "Zoom Video Communications, San Jose CA", "2026-11-02", "00:00", "software",
     [(1, "Pro plan monthly", 15.99)], [], {"invoice": True, "eml": True}),
    ("r20_fedex_office", "FedEx Office", "1 University Ave, Palo Alto CA", "2026-11-10", "15:12", "other",
     [(40, "Color print page", 0.89), (1, "Binding", 6.00)], [], {}),
    ("r22_best_buy", "Best Buy", "2220 Bridgepointe Pkwy, San Mateo CA", "2026-11-12", "17:40", "office",
     [(1, "Logitech MX Keys keyboard", 119.99)], [], {}),
    ("r23_hilton", "Hilton Seattle", "1301 6th Ave, Seattle WA", "2026-11-04", "11:30", "travel",
     [(1, "Room night", 249.00), (1, "Occupancy tax", 30.00)], [], {}),
    ("r37_peets", "Peet's Coffee", "100 Castro St, Mountain View CA", "2026-10-28", "09:05", "meals",
     [(1, "Cappuccino", 5.45), (1, "Bagel", 3.95)], [], {}),

    # ---------------- planted violations ----------------
    ("r21_dinner_wine", "Nopa", "560 Divisadero St, San Francisco CA", "2026-11-10", "20:14", "meals",
     [(2, "Roast chicken entree", 24.00), (1, "Bottle Pinot Noir wine", 54.00)],
     ["non_reimbursable", "over_limit"], {}),
    ("r24_steakhouse_over", "Morton's The Steakhouse", "177 Park Ave, San Jose CA", "2026-11-05", "19:40", "meals",
     [(2, "Filet mignon", 58.00), (2, "Sparkling water", 6.00), (1, "Side of spinach", 12.00)],
     ["over_limit"], {}),
    ("r25_hilton_over", "Hilton Seattle", "1301 6th Ave, Seattle WA", "2026-11-09", "11:30", "travel",
     [(3, "Room night", 249.00), (1, "Occupancy tax", 90.00)], ["over_limit"], {}),
    ("r26_monitor_over", "Apple Store", "Valley Fair, Santa Clara CA", "2026-11-06", "14:22", "office",
     [(1, "Studio Display stand monitor", 349.00)], ["over_limit"], {}),
    ("r27_uber_duplicate", "Uber", "Trip: office to SJC", "2026-11-02", "17:05", "travel",
     [(1, "UberX trip", 20.60), (1, "Booking fee", 2.50)], ["duplicate"], {}),
    ("r28_notion_duplicate", "Notion", "Notion Labs Inc, San Francisco CA", "2026-11-03", "00:00", "software",
     [(1, "Plus plan, 1 seat, monthly", 10.00)], ["duplicate"], {"invoice": True}),
    ("r29_weekend_lunch", "Sweetgreen", "180 University Ave, Palo Alto CA", "2026-11-07", "13:05", "meals",
     [(1, "Kale caesar", 13.95), (1, "Lemonade", 4.50)], ["weekend"], {}),
    ("r30_holiday_lunch", "Chipotle", "2 N Market St, San Jose CA", "2026-11-11", "12:44", "meals",
     [(1, "Burrito", 11.45), (1, "Chips", 2.65)], ["weekend"], {}),
    ("r31_fake_vendor", "Zentrova Quickserve Holdings", "PO Box 0000, Wilmington DE", "2026-11-09", "00:00", "other",
     [(1, "Advisory services", 88.00)], ["fake_vendor"], {"invoice": True}),
    ("r32_fake_vendor", "Brightpath Meridian Supply Co", "Suite 9, 1 Commerce Way", "2026-11-12", "10:10", "office",
     [(1, "Assorted office supplies", 140.00)], ["fake_vendor"], {}),
    ("r33_blurred_total", "Staples", "1 Main St, Mountain View CA", "2026-11-13", "11:11", "office",
     [(1, "Whiteboard markers", 14.99), (1, "Sticky notes", 8.49)], ["missing_info"], {"blur_total": True}),
    ("r34_no_items", "Cafe Luna", "48 Santa Cruz Ave, Los Gatos CA", "2026-11-12", "12:58", "meals",
     [(1, "Food and beverage", 41.20)], ["missing_info"], {"no_items": True}),
    ("r35_tobacco", "7-Eleven", "880 W San Carlos St, San Jose CA", "2026-11-10", "21:05", "other",
     [(1, "Marlboro cigarettes", 12.50), (1, "Bottled water", 2.49)], ["non_reimbursable"], {}),
    ("r36_gift_card", "Amazon", "Order 112-0000000", "2026-11-09", "16:00", "other",
     [(1, "Amazon gift card", 50.00)], ["non_reimbursable"], {}),
]


def is_weekend_or_holiday(d: str) -> bool:
    return date.fromisoformat(d).weekday() >= 5 or d in HOLIDAYS


def totals(cat, items):
    sub = round(sum(q * u for q, _, u in items), 2)
    tax = round(sub * TAX[cat], 2)
    return sub, tax, round(sub + tax, 2)


def lines_for(r):
    _, vendor, addr, d, tm, cat, items, viol, opt = r
    sub, tax, total = totals(cat, items)
    W = 40
    sep = "-" * W
    out = [vendor, addr]
    out.append("INVOICE" if opt.get("invoice") else "Sales receipt")
    out.append(f"Date: {d}" + (f"  {tm}" if tm != "00:00" else ""))
    out.append(sep)
    if opt.get("no_items"):
        out.append(f"{'Food and beverage':<30}{'':>10}")
    else:
        for q, desc, unit in items:
            left = f"{q} x {desc}"
            if len(left) > 30:
                left = left[:30]
            out.append(f"{left:<30}{q * unit:>10.2f}")
    out.append(sep)
    out.append(f"{'Subtotal':<30}{sub:>10.2f}")
    if tax:
        out.append(f"{'Sales tax':<30}{tax:>10.2f}")
    if opt.get("blur_total"):
        out.append(f"{'TOTAL USD':<30}{'$ ##.#':>10}")
    else:
        out.append(f"{'TOTAL USD':<30}{total:>10.2f}")
    out.append("")
    out.append("Paid: VISA ending 4417")
    out.append("Thank you!")
    return out, total


def write_pdf(path: Path, lines: list[str], blur: bool):
    h = (len(lines) * 5 + 30) * mm
    c = canvas.Canvas(str(path), pagesize=(80 * mm, h))
    y = h - 14 * mm
    for i, line in enumerate(lines):
        if i == 0:
            c.setFont("Helvetica-Bold", 12)
            c.drawCentredString(40 * mm, y, line)
        else:
            c.setFont("Courier", 7.6)
            c.drawString(5 * mm, y, line)
        if blur and line.startswith("TOTAL"):
            c.setFillGray(0.55)
            c.rect(52 * mm, y - 1.2 * mm, 22 * mm, 4.5 * mm, stroke=0, fill=1)
            c.setFillGray(0)
        y -= 5 * mm
    c.showPage()
    c.save()


def write_eml(path: Path, vendor: str, lines: list[str]):
    m = EmailMessage()
    m["From"] = f"{vendor} Billing <billing@example.com>"
    m["To"] = "employee@example.com"
    m["Subject"] = f"Your {vendor} invoice"
    m.set_content("\n".join(lines))
    path.write_bytes(bytes(m))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for r in R:
        name, vendor, _, d, _, cat, _, viol, opt = r
        # sanity: labels must agree with the calendar
        assert ("weekend" in viol) == is_weekend_or_holiday(d), f"{name}: weekend label mismatch for {d}"
        lines, _ = lines_for(r)
        if opt.get("eml"):
            fn = f"{name}.eml"
            write_eml(OUT / fn, vendor, lines)
        else:
            fn = f"{name}.pdf"
            write_pdf(OUT / fn, lines, bool(opt.get("blur_total")))
        if "duplicate" in viol or "non_reimbursable" in viol:
            dec = "reject"
        elif viol:
            dec = "flag"
        else:
            dec = "approve"
        rows.append({"file": fn, "expected_decision": dec, "expected_category": cat,
                     "violations": ";".join(viol)})
    with open(ROOT / "bench" / "labels.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["file", "expected_decision", "expected_category", "violations"])
        w.writeheader()
        w.writerows(sorted(rows, key=lambda x: x["file"]))
    (ROOT / "data" / "history.json").write_text(json.dumps(HISTORY, indent=2))
    n_v = sum(1 for x in rows if x["violations"])
    print(f"wrote {len(rows)} receipts ({len(rows) - n_v} clean, {n_v} with violations)")


if __name__ == "__main__":
    main()
