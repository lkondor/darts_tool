"""Formato del Mondiale PDC per turno.

ATTENZIONE: valori dell'edizione 2025/26 (128 giocatori, tutti dal primo
turno). Da riconfermare sul regolamento ufficiale 2026/27 prima dell'11
dicembre. In particolare `final_set_tiebreak=False` al primo turno e' la
lettura della regola 2025/26 (tie-break solo dal secondo turno) e va
verificata.
"""
from __future__ import annotations

from .schema import MatchFormat

WORLD_CHAMPIONSHIP = {
    "R1": MatchFormat(sets_to_win=3, final_set_tiebreak=False),
    "R2": MatchFormat(sets_to_win=3),
    "R3": MatchFormat(sets_to_win=4),
    "R4": MatchFormat(sets_to_win=4),
    "QF": MatchFormat(sets_to_win=5),
    "SF": MatchFormat(sets_to_win=6),
    "F": MatchFormat(sets_to_win=7),
}

_ALIASES = {
    "1": "R1", "ROUND 1": "R1", "FIRST ROUND": "R1", "LAST 128": "R1",
    "2": "R2", "ROUND 2": "R2", "SECOND ROUND": "R2", "LAST 64": "R2",
    "3": "R3", "ROUND 3": "R3", "THIRD ROUND": "R3", "LAST 32": "R3",
    "4": "R4", "ROUND 4": "R4", "FOURTH ROUND": "R4", "LAST 16": "R4",
    "QUARTER-FINAL": "QF", "QUARTER-FINALS": "QF", "QUARTERFINAL": "QF",
    "SEMI-FINAL": "SF", "SEMI-FINALS": "SF", "SEMIFINAL": "SF",
    "FINAL": "F",
}


def normalize_round(round_name: str) -> str:
    key = str(round_name).strip().upper()
    if key in WORLD_CHAMPIONSHIP:
        return key
    if key in _ALIASES:
        return _ALIASES[key]
    raise ValueError(f"Turno non riconosciuto: {round_name!r}")


def get_format(round_name: str) -> MatchFormat:
    return WORLD_CHAMPIONSHIP[normalize_round(round_name)]
