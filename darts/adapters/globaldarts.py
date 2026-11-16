"""Parser delle pagine "Statistics" di globaldarts.de.

Scritto e testato su pagine reali (UK Open 2024, European Tour 2026,
Mondiale 2025/26). Le tabelle hanno una riga di intestazione con due colonne
"Player"; le colonne a sinistra della prima e a destra della seconda sono le
statistiche dei due giocatori. Formati visti:

    Ave | 180s | Doubles | Player | v | Player | Ave | 180s | Doubles
    Ave | 180s | 100+ | Doubles | High Finish | Player | v | Player | (idem)

Note:
  - Doubles = chiusure/tentativi; le chiusure coincidono con i leg vinti.
  - "100+" conta le visite da 100 a 179 (180 esclusi): nello schema canonico
    n100_plus = 100+ + 180.
  - Un "-" al posto di un numero vale 0; le righe "Bye" vengono saltate.
  - I giocatori sono indicati col cognome ("v.Gerwen", "M.Smith").
  - La pagina non riporta data e turno del singolo match.
"""
from __future__ import annotations

import re
from datetime import date
from typing import List, Optional

from ..schema import MatchRecord, PlayerMatchStats

_RE_SCORE = re.compile(r"^(\d+)\s*:\s*(\d+)$")
_RE_DOUBLES = re.compile(r"^(\d+)\s*/\s*(\d+)$")


def _int(text: str) -> Optional[int]:
    text = text.strip()
    if text in ("-", ""):
        return 0
    return int(text) if text.isdigit() else None


def _side(header: List[str], cells: List[str], won_sets: Optional[int], name: str):
    col = dict(zip(header, cells))
    dbl = _RE_DOUBLES.match(col.get("Doubles", "").strip())
    if not dbl:
        return None
    try:
        avg = float(col["Ave"])
    except (KeyError, ValueError):
        return None
    n180 = _int(col.get("180s", ""))
    if n180 is None:
        return None
    n100 = _int(col["100+"]) if "100+" in col else None
    high = _int(col["High Finish"]) if "High Finish" in col else None
    hits, att = int(dbl[1]), int(dbl[2])
    return PlayerMatchStats(
        player=name, legs_won=hits, sets_won=won_sets, average=avg, n180=n180,
        n100_plus=None if n100 is None else n100 + n180,
        checkout_hits=hits, checkout_attempts=att, highest_checkout=high or None,
    )


def parse_stats_html(content: bytes, tournament: str, match_date: date,
                     format_type: str = "legs", default_stage: str = "tv") -> List[MatchRecord]:
    from bs4 import BeautifulSoup  # import locale

    soup = BeautifulSoup(content, "html.parser")
    records: List[MatchRecord] = []
    is_sets = format_type == "sets"
    for table in soup.find_all("table"):
        if table.find("table"):
            continue  # tabella contenitore: le righe si leggono da quella interna
        header: Optional[List[str]] = None
        stage_label = ""
        for row in table.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
            if cells.count("Player") == 2:
                header = cells
                continue
            if len(cells) == 1 and cells[0]:
                stage_label = cells[0]
                continue
            if header is None or len(cells) != len(header):
                continue
            i1 = header.index("Player")
            i2 = header.index("Player", i1 + 1)
            score = _RE_SCORE.match(cells[i1 + 1])
            if not score or i2 != i1 + 2:
                continue
            p1 = _side(header[:i1], cells[:i1], int(score[1]) if is_sets else None, cells[i1])
            p2 = _side(header[i2 + 1:], cells[i2 + 1:], int(score[2]) if is_sets else None, cells[i2])
            if p1 is None or p2 is None:
                continue
            n = len(records) + 1
            records.append(MatchRecord(
                match_id=f"globaldarts:{tournament}:{n}", source="globaldarts",
                date=match_date, tournament=tournament, round=stage_label,
                stage=default_stage, format_type=format_type, p1=p1, p2=p2,
            ))
    return records
