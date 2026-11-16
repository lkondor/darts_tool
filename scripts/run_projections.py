"""Genera le proiezioni per i match in calendario.

Uso:
    python scripts/run_projections.py --source synthetic --sims 10000

Scrive output/projections.json (dettaglio completo) e output/projections.csv
(una riga per match con le linee principali).
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from darts.adapters import get_source  # noqa: E402
from darts.formats import get_format  # noqa: E402
from darts.markets import summarize  # noqa: E402
from darts.profiles import build_profiles, prior_profile  # noqa: E402
from darts.simulator import DEFAULT_SIMS, project_fixture  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="synthetic")
    ap.add_argument("--sims", type=int, default=DEFAULT_SIMS)
    ap.add_argument("--out", default="output")
    args = ap.parse_args()

    source = get_source(args.source)
    history = source.fetch_history()
    fixtures = source.fetch_fixtures()
    as_of = min(f.date for f in fixtures) if fixtures else date.today()
    profiles = build_profiles(history, as_of=as_of)

    results, rows = [], []
    for fx in fixtures:
        pa = profiles.get(fx.player_a) or prior_profile(fx.player_a)
        pb = profiles.get(fx.player_b) or prior_profile(fx.player_b)
        fmt = get_format(fx.round)
        sim = project_fixture(fx, pa, pb, n_sims=args.sims, fmt=fmt)
        summary = summarize(sim, fx.player_a, fx.player_b, fmt.sets_to_win)
        summary.update({
            "fixture_id": fx.fixture_id, "date": fx.date.isoformat(),
            "tournament": fx.tournament, "round": fx.round, "source": source.name,
            "profile_a": vars(pa), "profile_b": vars(pb),
        })
        results.append(summary)
        rows.append({
            "date": fx.date.isoformat(), "round": fx.round,
            "player_a": fx.player_a, "player_b": fx.player_b,
            "p_a": summary["h2h"]["p_a"], "odds_a": summary["h2h"]["odds_a"],
            "odds_b": summary["h2h"]["odds_b"],
            "fair_total_sets": summary["total_sets"]["fair_line"],
            "fair_total_legs": summary["total_legs"]["fair_line"],
            "fair_leg_hcp_a": summary["leg_handicap_a"]["fair_line"],
            "fair_180_a": summary["n180_a"]["fair_line"],
            "fair_180_b": summary["n180_b"]["fair_line"],
            "fair_180_total": summary["n180_total"]["fair_line"],
            "conf_a": pa.confidence, "conf_b": pb.confidence,
        })

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "projections.json").write_text(json.dumps(results, indent=2, ensure_ascii=False))
    if rows:
        with open(out / "projections.csv", "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    for r in rows:
        print(f"{r['round']:>3}  {r['player_a']} vs {r['player_b']}: "
              f"P(A)={r['p_a']:.3f}  set {r['fair_total_sets']}  leg {r['fair_total_legs']}  "
              f"180 A/B/tot {r['fair_180_a']}/{r['fair_180_b']}/{r['fair_180_total']}")
    print(f"\n{len(rows)} match -> {out}/projections.json, {out}/projections.csv")


if __name__ == "__main__":
    main()
