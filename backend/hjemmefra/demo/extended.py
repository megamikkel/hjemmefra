"""DEMO prices for the base catalog (fictional but realistic, source_type DEMO).

Used only until a real offer source (Salling / Tjek API) is configured. Every plan built
on these carries the DEMO source id in its provenance and a coverage warning.
"""
from __future__ import annotations

from hjemmefra.demo.dataset import SOURCES, VF, VT, _o
from hjemmefra.ingestion.adapters.manual_json import ManualJsonAdapter

# (canonical id, title, qty, unit, {chain: (normal, offer or None)})
_ITEMS = [
    ("BACON", "Bacon i tern 150 g", 150, "g", {"rema": ("16.00", None), "lidl": ("14.00", None), "netto": ("15.00", "12.00")}),
    ("GARLIC", "Hvidløg 3 stk 150 g", 150, "g", {"rema": ("10.00", None), "lidl": ("9.00", None), "netto": ("10.00", None)}),
    ("MILK", "Letmælk 1 l", 1000, "ml", {"rema": ("11.50", None), "lidl": ("10.95", None), "netto": ("11.25", None)}),
    ("FLOUR", "Hvedemel 2 kg", 2000, "g", {"rema": ("16.00", None), "lidl": ("14.00", None), "netto": ("15.00", None)}),
    ("BUTTER", "Smør 250 g", 250, "g", {"rema": ("22.00", None), "lidl": ("20.00", "17.00"), "netto": ("21.00", None)}),
    ("OATS", "Havregryn 1 kg", 1000, "g", {"rema": ("12.00", None), "lidl": ("11.00", None), "netto": ("12.00", None)}),
    ("CREME_FRAICHE", "Cremefraiche 18% 200 ml", 200, "ml", {"rema": ("12.00", None), "lidl": ("10.00", None), "netto": ("11.00", "8.00")}),
    ("CHEDDAR", "Cheddar revet 200 g", 200, "g", {"rema": ("24.00", None), "lidl": ("21.00", None), "netto": ("23.00", None)}),
    ("MOZZARELLA", "Mozzarella 125 g", 125, "g", {"rema": ("9.00", None), "lidl": ("7.50", None), "netto": ("8.50", None)}),
    ("PARMESAN", "Parmesan 150 g", 150, "g", {"rema": ("30.00", None), "lidl": ("25.00", None), "netto": ("28.00", None)}),
    ("CARROT", "Gulerødder 1 kg", 1000, "g", {"rema": ("10.00", "8.00"), "lidl": ("9.00", None), "netto": ("10.00", None)}),
    ("CELERY", "Bladselleri 400 g", 400, "g", {"rema": ("15.00", None), "lidl": ("13.00", None), "netto": ("14.00", None)}),
    ("ZUCCHINI", "Squash 1 stk 300 g", 300, "g", {"rema": ("8.00", None), "lidl": ("7.00", None), "netto": ("8.00", None)}),
    ("TOMATO_PASTE", "Tomatpuré 140 g", 140, "g", {"rema": ("7.00", None), "lidl": ("6.00", None), "netto": ("6.50", None)}),
    ("SUNDRIED_TOMATO", "Soltørrede tomater 280 g", 280, "g", {"rema": ("22.00", None), "lidl": ("18.00", None), "netto": ("20.00", None)}),
    ("LASAGNA_SHEETS", "Lasagneplader 500 g", 500, "g", {"rema": ("14.00", None), "lidl": ("12.00", None), "netto": ("13.00", None)}),
    ("RED_WINE", "Rødvin 75 cl", 750, "ml", {"rema": ("40.00", None), "lidl": ("35.00", None), "netto": ("39.00", None)}),
    ("CHOCOLATE_DARK", "Mørk chokolade 100 g", 100, "g", {"rema": ("15.00", None), "lidl": ("12.00", None), "netto": ("14.00", None)}),
    ("NACHOS", "Tortillachips 200 g", 200, "g", {"rema": ("15.00", None), "lidl": ("12.00", None), "netto": ("14.00", "10.00")}),
    ("MANGO", "Mango 1 stk", 350, "g", {"rema": ("12.00", None), "lidl": ("10.00", None), "netto": ("12.00", None)}),
    ("AVOCADO", "Avocado 2 stk", 300, "g", {"rema": ("18.00", None), "lidl": ("15.00", None), "netto": ("17.00", None)}),
    ("LIME", "Lime 3 stk", 3, "stk", {"rema": ("10.00", None), "lidl": ("9.00", None), "netto": ("10.00", None)}),
    ("APPLE", "Æbler 1 kg", 1000, "g", {"rema": ("18.00", None), "lidl": ("16.00", None), "netto": ("17.00", None)}),
    ("CORN", "Majs 340 g", 340, "g", {"rema": ("9.00", None), "lidl": ("7.00", None), "netto": ("8.00", None)}),
    ("RUCOLA", "Rucola 65 g", 65, "g", {"rema": ("12.00", None), "lidl": ("10.00", None), "netto": ("11.00", None)}),
    ("CHILI_FRESH", "Rød chili 50 g", 50, "g", {"rema": ("8.00", None), "lidl": ("7.00", None), "netto": ("8.00", None)}),
    ("FRESH_HERBS", "Krydderurter i potte", 20, "g", {"rema": ("14.00", None), "lidl": ("12.00", None), "netto": ("13.00", None)}),
]

EXTRA_RAW_OFFERS = [
    _o(f"x_{chain}_{cid.lower()}", chain, title, cid, qty, unit, normal, offer)
    for cid, title, qty, unit, prices in _ITEMS for chain, (normal, offer) in sorted(prices.items())
]


def extended_adapters():
    by = {}
    for r in EXTRA_RAW_OFFERS:
        by.setdefault(r["retailer"], []).append(r)
    from hjemmefra.demo.dataset import CAPTURED_AT
    return [ManualJsonAdapter(SOURCES[k], records=v, captured_at=CAPTURED_AT) for k, v in sorted(by.items())]
