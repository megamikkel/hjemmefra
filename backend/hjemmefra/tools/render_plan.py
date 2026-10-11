"""Render a PlanResult JSON as a readable Danish Markdown plan + shopping list.

Every number comes from the engine's structured result; this only formats it."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def kr(minor) -> str:
    return "ukendt" if minor is None else f"{minor / 100:.2f} kr".replace(".", ",")


def qty(v, unit) -> str:
    v = float(v)
    if unit == "g" and v >= 1000:
        return f"{v / 1000:g} kg".replace(".", ",")
    if unit == "ml" and v >= 1000:
        return f"{v / 1000:g} l".replace(".", ",")
    return f"{v:g} {unit}".replace(".", ",")


DAYS = ["Mandag", "Tirsdag", "Onsdag", "Torsdag", "Fredag", "Lørdag", "Søndag"]


def render(plan: dict, mode: str) -> str:
    from datetime import date
    s = next(x for x in plan["scenarios"] if x["mode"] == mode and not x["relaxed_constraints"])
    out = [f"# Madplan ({mode})", ""]
    if s["status"] != "OK":
        return "\n".join(out + [f"**Ingen gyldig plan:** {s['infeasibility_reason']}"])
    c = s["confidence"]
    out += [f"**Ved kassen:** {kr(s['checkout_total_minor'])} i {s['store_count']} butik(ker)"
            + (f", heraf pant {kr(s['deposit_total_minor'])}" if s["deposit_total_minor"] else ""),
            f"**Verificerede priser:** {int(float(c['verified_share_of_checkout']) * 100)} % af beløbet"
            + (f". **{len(c['unknown_price_items'])} vare(r) uden kendt pris kommer oveni.**" if c["unknown_price_items"] else ""),
            f"**Optimering:** {s['optimization_status']}" + (" (bevist bedste løsning under kravene)" if s["optimization_status"] == "OPTIMAL" else ""), ""]
    out += ["## Ugen", "", "| Dag | Ret | Tid | Andel af indkøb |", "|---|---|---|---|"]
    for m in s["meals"]:
        d = date.fromisoformat(m["day"])
        name = m["recipe_name"] + (" (rester)" if m["is_leftover_meal"] else "")
        out.append(f"| {DAYS[d.weekday()]} {d.day}/{d.month} | {name} | {m['total_minutes']} min | {kr(m['checkout_contribution_minor'])} |")
    out += ["", "## Indkøbsliste", ""]
    for sb in s["store_breakdown"]:
        out += [f"### {sb['store_name']}: {kr(sb['checkout_minor'])}", ""]
        for l in sorted(sb["lines"], key=lambda x: x["product_name"]):
            tag = " (tilbud)" if l["price_source"] == "OFFER" else ""
            out.append(f"- {l['packages']} × {l['product_name']} à {qty(l['package_quantity'], l['package_unit'])}: "
                       f"{kr(l['checkout_cost_minor'])}{tag}. Bruges {qty(l['consumed_quantity'], l['package_unit'])}, "
                       f"rest {qty(l['remainder_quantity'], l['package_unit'])}. Gælder {l['valid_from']} til {l['valid_to']}.")
        out.append("")
    if s["unpriced_items"]:
        out += ["### Køb også (pris ukendt, ikke med i beløbet)", ""]
        for u in s["unpriced_items"]:
            out.append(f"- {u['line']} (til {u['recipe']})")
        out.append("")
    if s["pantry_uses"]:
        out += ["### Fra jeres eget lager", ""]
        for p in s["pantry_uses"]:
            out.append(f"- {p['canonical_product_id'].lower()}: {qty(p['quantity'], p['unit'])}")
        out.append("")
    out += ["## Forklaring", ""] + [f"- {e}" for e in s["explanations"]] + [""]
    if s["warnings"]:
        out += ["## Advarsler", ""] + [f"- {w}" for w in s["warnings"]] + [""]
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("plan")
    ap.add_argument("--mode", default="BALANCED")
    a = ap.parse_args(argv)
    print(render(json.loads(Path(a.plan).read_text()), a.mode))
    return 0


if __name__ == "__main__":
    sys.exit(main())
