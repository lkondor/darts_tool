"""Backtest del modello su un torneo a set gia' giocato.

Uso:
    python scripts/backtest.py --history data/history.json \
        --tournament "PDC World Championship 2026" --mode strict

--mode strict     profili costruiti solo con i match PRECEDENTI al torneo
                  (il test corretto: nessun dato dal futuro).
--mode lookahead  profili costruiti con tutti gli altri match dello storico,
                  anche successivi. NON e' un vero backtest: serve solo a
                  controllare la forma del modello quando i profili sono buoni.

Scrive output/backtest_<mode>.json e stampa un riepilogo.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from concurrent.futures import ProcessPoolExecutor
from datetime import date, timedelta
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from darts.io import records_from_json  # noqa: E402
from darts.markets import fair_half_line  # noqa: E402
from darts.profiles import build_profiles, prior_profile  # noqa: E402
from darts.schema import Fixture, MatchFormat  # noqa: E402
from darts.simulator import project_fixture  # noqa: E402


def infer_format(rec) -> MatchFormat:
    """Formato dal punteggio in set. Al Mondiale il primo turno (giornate 1-9
    di globaldarts) non ha tie-break nel set decisivo."""
    sets_to_win = max(rec.p1.sets_won, rec.p2.sets_won)
    page = re.search(r":p(\d+):", rec.match_id)
    first_round = sets_to_win == 3 and page is not None and int(page[1]) <= 9
    return MatchFormat(sets_to_win=sets_to_win, final_set_tiebreak=not first_round)


def _one(args):
    rec, pa, pb, n_sims, form = args
    fmt = infer_format(rec)
    fx = Fixture(rec.match_id, rec.date, rec.tournament, f"S{fmt.sets_to_win}", pa.name, pb.name)
    sim = project_fixture(fx, pa, pb, n_sims=n_sims, fmt=fmt, form=form)
    actual = {
        "a_wins": rec.p1.sets_won > rec.p2.sets_won,
        "total_sets": rec.p1.sets_won + rec.p2.sets_won,
        "total_legs": rec.legs_played,
        "n180_a": rec.p1.n180, "n180_b": rec.p2.n180,
        "n180_total": rec.p1.n180 + rec.p2.n180,
    }
    samples = {
        "total_sets": sim.sets_a + sim.sets_b,
        "total_legs": sim.legs_a + sim.legs_b,
        "n180_a": sim.n180_a, "n180_b": sim.n180_b,
        "n180_total": sim.n180_a + sim.n180_b,
    }
    row = {
        "match": f"{pa.name} v {pb.name}", "sets_to_win": fmt.sets_to_win,
        "p_a": float(sim.a_wins.mean()), "a_wins": bool(actual["a_wins"]),
        "conf": [pa.confidence, pb.confidence],
    }
    for key, smp in samples.items():
        line = fair_half_line(smp)
        lo, hi = np.percentile(smp, [10, 90])
        row[key] = {
            "actual": int(actual[key]), "mean": float(smp.mean()), "fair_line": line,
            "p_over": float((smp > line).mean()), "over": bool(actual[key] > line),
            "in_80": bool(lo <= actual[key] <= hi),
        }
    return row


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--history", default="data/history.json")
    ap.add_argument("--tournament", default="PDC World Championship 2026")
    ap.add_argument("--mode", choices=["strict", "lookahead"], default="strict")
    ap.add_argument("--sims", type=int, default=4000)
    ap.add_argument("--no-form", action="store_true")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--out", default="output")
    args = ap.parse_args()

    records = records_from_json(args.history)
    target = [r for r in records if r.tournament == args.tournament and r.format_type == "sets"]
    others = [r for r in records if r.tournament != args.tournament]
    if not target:
        sys.exit(f"Nessun match a set per {args.tournament!r}")
    start = min(r.date for r in target)
    if args.mode == "strict":
        as_of = start
    else:
        as_of = max(r.date for r in records) + timedelta(days=1)
    profiles = build_profiles(others, as_of=as_of)

    jobs = []
    for rec in target:
        pa = profiles.get(rec.p1.player) or prior_profile(rec.p1.player)
        pb = profiles.get(rec.p2.player) or prior_profile(rec.p2.player)
        jobs.append((rec, pa, pb, args.sims, not args.no_form))
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        rows = list(ex.map(_one, jobs, chunksize=4))

    p = np.array([r["p_a"] for r in rows])
    y = np.array([r["a_wins"] for r in rows], dtype=float)
    pc = np.clip(p, 1e-4, 1 - 1e-4)
    fav_p = np.maximum(p, 1 - p)
    fav_won = np.where(p >= 0.5, y, 1 - y)
    summary = {
        "tournament": args.tournament, "mode": args.mode, "form": not args.no_form,
        "matches": len(rows),
        "with_prior_only": int(sum("prior" in r["conf"] for r in rows)),
        "h2h": {
            "log_loss": float(-(y * np.log(pc) + (1 - y) * np.log(1 - pc)).mean()),
            "log_loss_coin_flip": float(np.log(2)),
            "brier": float(((p - y) ** 2).mean()),
            "favourite_win_rate": float(fav_won.mean()),
            "favourite_mean_prob": float(fav_p.mean()),
            "buckets": [],
        },
        "markets": {},
    }
    for lo, hi in [(0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.01)]:
        m = (fav_p >= lo) & (fav_p < hi)
        if m.any():
            summary["h2h"]["buckets"].append({
                "range": f"{lo:.1f}-{min(hi, 1.0):.1f}", "n": int(m.sum()),
                "mean_prob": float(fav_p[m].mean()), "win_rate": float(fav_won[m].mean())})
    for key in ("total_sets", "total_legs", "n180_a", "n180_b", "n180_total"):
        act = np.array([r[key]["actual"] for r in rows], dtype=float)
        mean = np.array([r[key]["mean"] for r in rows])
        summary["markets"][key] = {
            "actual_mean": float(act.mean()), "model_mean": float(mean.mean()),
            "bias": float((mean - act).mean()),
            "mae": float(np.abs(mean - act).mean()),
            "over_rate_at_fair_line": float(np.mean([r[key]["over"] for r in rows])),
            "model_p_over_at_fair_line": float(np.mean([r[key]["p_over"] for r in rows])),
            "inside_80pct_interval": float(np.mean([r[key]["in_80"] for r in rows])),
        }

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"backtest_{args.mode}.json").write_text(
        json.dumps({"summary": summary, "matches": rows}, indent=1, ensure_ascii=False),
        encoding="utf-8")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
