"""Fonte sintetica: giocatori e match INVENTATI, solo per provare la pipeline.

Nessun numero qui dentro descrive giocatori reali.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import List

import numpy as np

from ..schema import Fixture, MatchRecord, PlayerMatchStats
from .base import DataSource

# nome, media, 180 per leg, checkout %
_PLAYERS = [
    ("Giocatore A", 101.0, 0.42, 0.44),
    ("Giocatore B", 98.5, 0.33, 0.42),
    ("Giocatore C", 96.0, 0.30, 0.41),
    ("Giocatore D", 94.5, 0.24, 0.40),
    ("Giocatore E", 93.0, 0.27, 0.39),
    ("Giocatore F", 91.5, 0.20, 0.38),
    ("Giocatore G", 89.0, 0.18, 0.37),
    ("Giocatore H", 85.0, 0.13, 0.34),
]


class SyntheticSource(DataSource):
    name = "synthetic"

    def __init__(self, as_of: date = date(2026, 12, 11), seed: int = 2026):
        self.as_of = as_of
        self.seed = seed

    def fetch_history(self) -> List[MatchRecord]:
        rng = np.random.default_rng(self.seed)
        records = []
        k = 0
        for i, (name, avg, r180, co) in enumerate(_PLAYERS):
            for _ in range(30):
                j = int(rng.choice([x for x in range(len(_PLAYERS)) if x != i]))
                opp, oavg, o180, oco = _PLAYERS[j]
                legs_w, legs_l = 6, int(rng.integers(0, 6))
                if rng.random() < 0.5:
                    legs_me, legs_opp = legs_w, legs_l
                else:
                    legs_me, legs_opp = legs_l, legs_w
                legs = legs_me + legs_opp
                day = self.as_of - timedelta(days=int(rng.integers(5, 330)))

                def stats(player, a, r, c, won):
                    att = max(won, int(round(won / max(c + rng.normal(0, 0.06), 0.15))))
                    return PlayerMatchStats(
                        player=player, legs_won=won,
                        average=round(float(a + rng.normal(0, 4.0)), 2),
                        n180=int(rng.poisson(r * legs)),
                        checkout_hits=won, checkout_attempts=att,
                    )

                k += 1
                records.append(MatchRecord(
                    match_id=f"syn-{k}", source=self.name, date=day,
                    tournament="Torneo sintetico", round="R1",
                    stage="floor", format_type="legs",
                    p1=stats(name, avg, r180, co, legs_me),
                    p2=stats(opp, oavg, o180, oco, legs_opp),
                ))
        return records

    def fetch_fixtures(self) -> List[Fixture]:
        pairs = [(0, 7, "R1"), (1, 6, "R1"), (2, 5, "R2"), (3, 4, "R3"), (0, 1, "F")]
        return [
            Fixture(
                fixture_id=f"syn-fx-{n}", date=self.as_of, tournament="Mondiale sintetico",
                round=rnd, player_a=_PLAYERS[a][0], player_b=_PLAYERS[b][0],
            )
            for n, (a, b, rnd) in enumerate(pairs, 1)
        ]
