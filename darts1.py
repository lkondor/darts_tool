"""Parser dei PDF "Spielrundenstatistiken" di darts1.de.

Scritto e testato sul PDF reale dei quarti del Mondiale 2026 (formato a set).
Il ramo per i match a leg ("Session" al posto di "Satz") segue la stessa
struttura vista nelle anteprime di altri PDF ma NON e' ancora testato su un
file reale.

Significato delle righe nel PDF:
    180     = numero di 180
    140+    = visite da 140 a 179
    100+    = visite da 100 a 139
    Gesamt  = somma delle tre righe
Nello schema canonico n140_plus e n100_plus sono cumulati (>=140, >=100).
"""
from __future__ import annotations

import re
from datetime import date
from typing import List, Optional

from ..names import normalize_name
from ..schema import MatchRecord, PlayerMatchStats

_SEP = r"\s*:?\s*"
_RE_HEADER = re.compile(r"^(?P<round>.+?) - Spiel (?P<n>\d+)/(?P<tot>\d+)$")
_RE_SCORE = re.compile(rf"^(?P<p1>\D+?)\s+(?P<s1>\d+){_SEP}(?P<s2>\d+)\s+(?P<p2>\D+)$")
_RE_SET = re.compile(rf"^Satz \d+\s+(\d+){_SEP}(\d+)\s+Satz \d+$")
_RE_SESSION = re.compile(r"^Session \d+")
_RE_LEGS = re.compile(rf"^Legs Gesamt\s+(\d+){_SEP}(\d+)\s+Legs Gesamt$")
_RE_AVG = re.compile(r"^([\d.,]+)\s+3-Dart-Average\s+([\d.,]+)$")
_RE_CO = re.compile(r"^(\d+)/(\d+) - \d+%\s+Checkout-Quote\s+(\d+)/(\d+) - \d+%$")
_RE_HIGH = re.compile(r"^(\d+)\s+Höchstes Finish\s+(\d+)$")
_RE_180 = re.compile(r"^(\d+)\s+180\s+(\d+)$")
_RE_140 = re.compile(r"^(\d+)\s+140\+\s+(\d+)$")
_RE_100 = re.compile(r"^(\d+)\s+100\+\s+(\d+)$")


def _num(text: str) -> float:
    return float(text.replace(",", "."))


def parse_text(text: str, tournament: str, match_date: date, stage: str = "tv",
               source_tag: Optional[str] = None) -> List[MatchRecord]:
    """Converte il testo estratto da un PDF in MatchRecord."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    records: List[MatchRecord] = []
    cur: Optional[dict] = None

    def close() -> None:
        nonlocal cur
        if cur is None:
            return
        missing = [k for k in ("p1", "avg", "co", "n180") if k not in cur]
        if missing:
            raise ValueError(f"Match {cur.get('header')} incompleto: mancano {missing}")
        is_sets = bool(cur["sets"])
        s1, s2 = cur["score"]
        hits1, att1, hits2, att2 = cur["co"]
        legs1, legs2 = cur.get("legs", (s1, s2) if not is_sets else (hits1, hits2))
        n140 = cur.get("n140", (None, None))
        n100 = cur.get("n100", (None, None))

        def stats(i: int, name: str) -> PlayerMatchStats:
            n180 = cur["n180"][i]
            a140, a100 = n140[i], n100[i]
            return PlayerMatchStats(
                player=name,
                legs_won=(legs1, legs2)[i],
                sets_won=(s1, s2)[i] if is_sets else None,
                average=cur["avg"][i],
                n180=n180,
                n140_plus=None if a140 is None else a140 + n180,
                n100_plus=None if a140 is None or a100 is None else a100 + a140 + n180,
                checkout_hits=(hits1, hits2)[i],
                checkout_attempts=(att1, att2)[i],
                highest_checkout=cur.get("high", (None, None))[i],
            )

        tag = source_tag or tournament
        records.append(MatchRecord(
            match_id=f"darts1:{tag}:{cur['round']}:{cur['n']}",
            source="darts1", date=match_date, tournament=tournament, round=cur["round"],
            stage=stage, format_type="sets" if is_sets else "legs",
            p1=stats(0, cur["p1"]), p2=stats(1, cur["p2"]),
            set_scores=cur["sets"] or None,
        ))
        cur = None

    expect_score = False
    for ln in lines:
        m = _RE_HEADER.match(ln)
        if m:
            close()
            cur = {"header": ln, "round": m["round"].strip(), "n": int(m["n"]), "sets": []}
            expect_score = True
            continue
        if ln == "Finale" and cur is None:
            # il PDF della finale ha un solo match e nessuna riga "Spiel n/m"
            cur = {"header": ln, "round": "Finale", "n": 1, "sets": []}
            expect_score = True
            continue
        if cur is None:
            continue
        if expect_score:
            m = _RE_SCORE.match(ln)
            if not m:
                raise ValueError(f"Riga punteggio non riconosciuta dopo {cur['header']!r}: {ln!r}")
            cur["p1"] = normalize_name(m["p1"])
            cur["p2"] = normalize_name(m["p2"])
            cur["score"] = (int(m["s1"]), int(m["s2"]))
            expect_score = False
            continue
        if (m := _RE_SET.match(ln)):
            cur["sets"].append((int(m[1]), int(m[2])))
        elif _RE_SESSION.match(ln):
            pass
        elif (m := _RE_LEGS.match(ln)):
            cur["legs"] = (int(m[1]), int(m[2]))
        elif (m := _RE_AVG.match(ln)):
            cur["avg"] = (_num(m[1]), _num(m[2]))
        elif (m := _RE_CO.match(ln)):
            cur["co"] = (int(m[1]), int(m[2]), int(m[3]), int(m[4]))
        elif (m := _RE_HIGH.match(ln)):
            cur["high"] = (int(m[1]), int(m[2]))
        elif (m := _RE_180.match(ln)):
            cur["n180"] = (int(m[1]), int(m[2]))
        elif (m := _RE_140.match(ln)):
            cur["n140"] = (int(m[1]), int(m[2]))
        elif (m := _RE_100.match(ln)):
            cur["n100"] = (int(m[1]), int(m[2]))
    close()
    return records


def pdf_to_text(path: str) -> str:
    import pdfplumber  # import locale: serve solo a chi legge i PDF

    with pdfplumber.open(path) as pdf:
        return "\n".join((page.extract_text() or "") for page in pdf.pages)


def parse_pdf(path: str, tournament: str, match_date: date, stage: str = "tv",
              source_tag: Optional[str] = None) -> List[MatchRecord]:
    return parse_text(pdf_to_text(path), tournament, match_date, stage, source_tag)
