"""Dai risultati delle simulazioni ai mercati: probabilita' e fair lines.

Le fair lines sono calcolate sulla distribuzione (quantili), non sulla media:
la linea fair e' la mezza linea il cui Over e' piu' vicino al 50%.
"""
from __future__ import annotations

import math
from typing import Dict, Iterable, Optional

import numpy as np

from .simulator import SimResult


def prob_over(samples: np.ndarray, line: float) -> float:
    return float((samples > line).mean())


def fair_odds(p: float) -> Optional[float]:
    return round(1.0 / p, 3) if p > 0 else None


def fair_half_line(samples: np.ndarray) -> float:
    """Mezza linea (x.5) con P(Over) piu' vicina al 50%."""
    lo = math.floor(float(samples.min())) - 0.5
    hi = math.ceil(float(samples.max())) + 0.5
    lines = np.arange(lo, hi + 1.0, 1.0)
    p = np.array([prob_over(samples, x) for x in lines])
    return float(lines[int(np.argmin(np.abs(p - 0.5)))])


def over_under(samples: np.ndarray, lines: Optional[Iterable[float]] = None, width: int = 2) -> dict:
    """Linea fair piu' P(Over)/P(Under) e quote fair su una griglia di linee."""
    fair = fair_half_line(samples)
    if lines is None:
        lines = [fair + k for k in range(-width, width + 1)]
    table = []
    for line in lines:
        p_over = prob_over(samples, line)
        table.append({
            "line": line,
            "p_over": round(p_over, 4),
            "p_under": round(1.0 - p_over, 4),
            "odds_over": fair_odds(p_over),
            "odds_under": fair_odds(1.0 - p_over),
        })
    return {"fair_line": fair, "mean": round(float(samples.mean()), 3), "lines": table}


def edge(p_model: float, odds: float) -> float:
    """Valore atteso per unita' puntata a quota decimale `odds`."""
    return p_model * odds - 1.0


def summarize(res: SimResult, name_a: str, name_b: str, sets_to_win: int) -> Dict:
    p_a = float(res.a_wins.mean())
    total_sets = res.sets_a + res.sets_b
    total_legs = res.legs_a + res.legs_b
    set_margin = res.sets_a.astype(int) - res.sets_b.astype(int)   # A - B
    leg_margin = res.legs_a.astype(int) - res.legs_b.astype(int)

    set_lines = [x + 0.5 for x in range(sets_to_win, 2 * sets_to_win - 1)]
    hcp_lines = [x + 0.5 for x in range(-sets_to_win, sets_to_win)]

    correct = {}
    for sa in range(sets_to_win + 1):
        for sb in range(sets_to_win + 1):
            if (sa == sets_to_win) != (sb == sets_to_win):
                p = float(((res.sets_a == sa) & (res.sets_b == sb)).mean())
                if p > 0:
                    correct[f"{sa}-{sb}"] = round(p, 4)

    return {
        "player_a": name_a,
        "player_b": name_b,
        "n_sims": int(len(res.a_wins)),
        "h2h": {
            "p_a": round(p_a, 4), "p_b": round(1 - p_a, 4),
            "odds_a": fair_odds(p_a), "odds_b": fair_odds(1 - p_a),
        },
        # Handicap set su A: A copre la linea h se (set A - set B) + h > 0.
        "set_handicap_a": [
            {"handicap": h, "p_a_covers": round(float((set_margin + h > 0).mean()), 4)}
            for h in hcp_lines
        ],
        "leg_handicap_a": {
            # margine leg (A - B): linea fair e griglia
            **over_under(leg_margin, width=2),
        },
        "correct_score_sets": correct,
        "total_sets": over_under(total_sets, lines=set_lines),
        "total_legs": over_under(total_legs, width=3),
        "n180_a": over_under(res.n180_a),
        "n180_b": over_under(res.n180_b),
        "n180_total": over_under(res.n180_a + res.n180_b),
        "most_180s": {
            "p_a": round(float((res.n180_a > res.n180_b).mean()), 4),
            "p_tie": round(float((res.n180_a == res.n180_b).mean()), 4),
            "p_b": round(float((res.n180_a < res.n180_b).mean()), 4),
        },
    }
