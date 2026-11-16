"""Schema dati canonico.

Ogni fonte (Sportradar, darts1.de, sintetico, ...) viene convertita in questi
oggetti da un adapter. Il resto del software non conosce le fonti.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional, Tuple


@dataclass(frozen=True)
class MatchFormat:
    """Formato a set di un match (Mondiale PDC)."""

    sets_to_win: int
    legs_per_set_to_win: int = 3
    # Nel set decisivo serve un vantaggio di due leg...
    final_set_tiebreak: bool = True
    # ...fino a questo punteggio pari, poi leg secco (5-5 -> si chiude 6-5).
    tiebreak_sudden_death_at: int = 5


@dataclass
class PlayerMatchStats:
    """Statistiche di un giocatore in un match. None = dato non disponibile."""

    player: str
    legs_won: int
    sets_won: Optional[int] = None
    average: Optional[float] = None          # media 3 freccette
    n180: Optional[int] = None
    n140_plus: Optional[int] = None
    n100_plus: Optional[int] = None
    checkout_hits: Optional[int] = None
    checkout_attempts: Optional[int] = None
    highest_checkout: Optional[int] = None


@dataclass
class MatchRecord:
    """Un match concluso, con le statistiche dei due giocatori."""

    match_id: str
    source: str
    date: date
    tournament: str
    round: str
    p1: PlayerMatchStats
    p2: PlayerMatchStats
    stage: str = "tv"                 # "tv" oppure "floor"
    format_type: str = "sets"         # "sets" oppure "legs"
    set_scores: Optional[List[Tuple[int, int]]] = None  # leg per set (p1, p2)

    @property
    def legs_played(self) -> int:
        return self.p1.legs_won + self.p2.legs_won

    def stats_for(self, player: str) -> Optional[PlayerMatchStats]:
        if self.p1.player == player:
            return self.p1
        if self.p2.player == player:
            return self.p2
        return None


@dataclass
class Fixture:
    """Un match in calendario."""

    fixture_id: str
    date: date
    tournament: str
    round: str
    player_a: str
    player_b: str


@dataclass
class PlayerProfile:
    """Parametri di un giocatore usati dal simulatore."""

    name: str
    avg3: float               # media 3 freccette attesa
    n180_per_leg: float       # 180 per leg giocato
    checkout_pct: float       # chiusure / freccette al doppio (0-1)
    eff_legs: float = 0.0     # campione effettivo (leg pesati per recency)
    matches: int = 0
    confidence: str = "prior"
    notes: List[str] = field(default_factory=list)
