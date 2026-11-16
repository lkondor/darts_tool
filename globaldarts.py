"""Parser delle pagine "Statistics" di globaldarts.de.

Scritto e testato sulla pagina reale dello UK Open 2024. Ogni riga:
    Ave | 180s | Doubles | Player | v | Player | Ave | 180s | Doubles
dove Doubles = chiusure/tentativi (le chiusure coincidono con i leg vinti) e
i giocatori sono indicati col solo cognome ("v.Gerwen").

Limiti: la pagina non riporta data e turno del singolo match; la data viene
passata dal chiamante. Il turno resta vuoto.
"""
from __future__ import annotations

import re
from datetime import date
from typing import List

from ..schema import MatchRecord, PlayerMatchStats

_RE_SCORE = re.compile(r"^(\d+)\s*:\s*(\d+)$")
_RE_DOUBLES = re.compile(r"^(\d+)\s*/\s*(\d+)$")


def parse_stats_html(content: bytes, tournament: str, match_date: date,
                     format_type: str = "legs", default_stage: str = "tv") -> List[MatchRecord]:
    from bs4 import BeautifulSoup  # import locale

    soup = BeautifulSoup(content, "html.parser")
    records: List[MatchRecord] = []
    for table in soup.find_all("table"):
        stage_label = ""
        for row in table.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
            if len(cells) == 1 and cells[0]:
                stage_label = cells[0]
                continue
            if len(cells) != 9 or cells[0] == "Ave":
                continue
            score = _RE_SCORE.match(cells[4])
            d1, d2 = _RE_DOUBLES.match(cells[2]), _RE_DOUBLES.match(cells[8])
            if not (score and d1 and d2):
                continue
            try:
                avg1, avg2 = float(cells[0]), float(cells[6])
                n180_1, n180_2 = int(cells[1]), int(cells[7])
            except ValueError:
                continue
            is_sets = format_type == "sets"

            def stats(name, avg, n180, dbl, won):
                hits, att = int(dbl[1]), int(dbl[2])
                return PlayerMatchStats(
                    player=name, legs_won=hits, sets_won=won if is_sets else None,
                    average=avg, n180=n180, checkout_hits=hits, checkout_attempts=att,
                )

            n = len(records) + 1
            records.append(MatchRecord(
                match_id=f"globaldarts:{tournament}:{n}", source="globaldarts",
                date=match_date, tournament=tournament, round=stage_label,
                stage=default_stage, format_type=format_type,
                p1=stats(cells[3], avg1, n180_1, d1, int(score[1])),
                p2=stats(cells[5], avg2, n180_2, d2, int(score[2])),
            ))
    return records
