"""Proiezione di un singolo match dai profili reali (data/history.json).

Uso:
    python scripts/quote.py "Luke Littler" "Gian van Veen" --round QF

I nomi possono essere anche solo cognomi ("Littler", "v.Veen"). Scrive
output/quote.json e stampa i mercati principali.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from darts.formats import get_format, normalize_round  # noqa: E402
from darts.io import records_from_json  # noqa: E402
from darts.markets import summarize  # noqa: E402
from darts.names import NameResolver  # noqa: E402
from darts.profiles import build_profiles, prior_profile  # noqa: E402
from darts.schema import Fixture  # noqa: E402
from darts.simulator import DEFAULT_SIMS, project_fixture  # noqa: E402


def _fmt_ou(title: str, block: dict) -> str:
    rows = "  ".join(f"{r['line']:g}: O {r['odds_over']} / U {r['odds_under']}" for r in block["lines"])
    return f"{title:<14} linea fair {block['fair_line']:g} (media {block['mean']:.1f})\n    {rows}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("player_a")
    ap.add_argument("player_b")
    ap.add_argument("--round", default="R1", help="R1 R2 R3 R4 QF SF F")
    ap.add_argument("--date", default="2026-12-11")
    ap.add_argument("--history", default=str(ROOT / "data" / "history.json"))
    ap.add_argument("--sims", type=int, default=DEFAULT_SIMS)
    ap.add_argument("--out", default="output")
    args = ap.parse_args()

    when = date.fromisoformat(args.date)
    resolver = NameResolver.from_config(ROOT / "config")
    profiles = build_profiles(records_from_json(args.history), as_of=when)
    profs = []
    for raw in (args.player_a, args.player_b):
        name, status = resolver.resolve(raw)
        if status == "ambiguous":
            sys.exit(f"Nome ambiguo: {raw!r}. Usare nome e cognome.")
        profs.append(profiles.get(name) or prior_profile(name))
    pa, pb = profs
    rnd = normalize_round(args.round)
    fmt = get_format(rnd)
    fx = Fixture("quote", when, "PDC World Championship 2027", rnd, pa.name, pb.name)
    sim = project_fixture(fx, pa, pb, n_sims=args.sims, fmt=fmt)
    s = summarize(sim, pa.name, pb.name, fmt.sets_to_win)
    s.update(round=rnd, profile_a=vars(pa), profile_b=vars(pb))

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "quote.json").write_text(json.dumps(s, indent=1, ensure_ascii=False), encoding="utf-8")

    print(f"{pa.name} vs {pb.name} - {rnd}, primo a {fmt.sets_to_win} set, {s['n_sims']} simulazioni")
    for p in (pa, pb):
        print(f"  {p.name}: media {p.avg3:.1f}, 180/leg {p.n180_per_leg:.3f}, "
              f"checkout {p.checkout_pct:.1%}, confidenza {p.confidence} ({p.eff_legs:.0f} leg effettivi)")
    h = s["h2h"]
    print(f"\nH2H            {pa.name} {h['p_a']:.1%} (quota {h['odds_a']})  |  "
          f"{pb.name} {h['p_b']:.1%} (quota {h['odds_b']})")
    hc = "  ".join(f"{r['handicap']:+g}: {r['p_a_covers']:.1%}" for r in s["set_handicap_a"])
    print(f"Handicap set   ({pa.name})  {hc}")
    print(_fmt_ou("Totale set", s["total_sets"]))
    print(_fmt_ou("Totale leg", s["total_legs"]))
    print(_fmt_ou(f"180 {pa.name.split()[-1]}", s["n180_a"]))
    print(_fmt_ou(f"180 {pb.name.split()[-1]}", s["n180_b"]))
    print(_fmt_ou("180 totali", s["n180_total"]))
    m = s["most_180s"]
    print(f"Piu' 180       {pa.name} {m['p_a']:.1%}  pari {m['p_tie']:.1%}  {pb.name} {m['p_b']:.1%}")


if __name__ == "__main__":
    main()
