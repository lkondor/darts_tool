"""Profili giocatore dallo storico: pesi per recency e shrinkage verso un prior."""
from __future__ import annotations

from datetime import date
from typing import Dict, Iterable

from .schema import MatchRecord, PlayerProfile

HALF_LIFE_DAYS = 180.0

# Prior verso cui vengono "tirati" i giocatori con pochi dati.
# Valori provvisori: da ricalibrare sullo storico reale (idealmente per fascia
# di ranking, perche' un qualificato sconosciuto e' in media sotto il campo).
PRIOR = {"avg3": 90.0, "n180_per_leg": 0.22, "checkout_pct": 0.38}
PRIOR_LEGS = 120.0           # peso del prior, in leg equivalenti
PRIOR_CHECKOUT_DARTS = 300.0  # peso del prior per il checkout, in freccette al doppio


def _confidence(eff_legs: float) -> str:
    if eff_legs >= 400:
        return "alta"
    if eff_legs >= 150:
        return "media"
    if eff_legs > 0:
        return "bassa"
    return "prior"


def build_profiles(records: Iterable[MatchRecord], as_of: date,
                   half_life_days: float = HALF_LIFE_DAYS) -> Dict[str, PlayerProfile]:
    acc: Dict[str, dict] = {}
    for rec in records:
        if rec.date >= as_of:
            continue  # niente dati dal futuro
        w = 0.5 ** ((as_of - rec.date).days / half_life_days)
        legs = rec.legs_played
        if legs <= 0:
            continue
        for st in (rec.p1, rec.p2):
            a = acc.setdefault(st.player, dict(
                w_legs=0.0, avg_num=0.0, avg_den=0.0, n180=0.0, n180_legs=0.0,
                co_hits=0.0, co_att=0.0, matches=0))
            a["matches"] += 1
            a["w_legs"] += w * legs
            if st.average is not None:
                a["avg_num"] += w * legs * st.average
                a["avg_den"] += w * legs
            if st.n180 is not None:
                a["n180"] += w * st.n180
                a["n180_legs"] += w * legs
            if st.checkout_hits is not None and st.checkout_attempts:
                a["co_hits"] += w * st.checkout_hits
                a["co_att"] += w * st.checkout_attempts

    profiles = {}
    for name, a in acc.items():
        avg3 = (a["avg_num"] + PRIOR_LEGS * PRIOR["avg3"]) / (a["avg_den"] + PRIOR_LEGS)
        n180 = (a["n180"] + PRIOR_LEGS * PRIOR["n180_per_leg"]) / (a["n180_legs"] + PRIOR_LEGS)
        co = ((a["co_hits"] + PRIOR_CHECKOUT_DARTS * PRIOR["checkout_pct"])
              / (a["co_att"] + PRIOR_CHECKOUT_DARTS))
        profiles[name] = PlayerProfile(
            name=name, avg3=round(avg3, 2), n180_per_leg=round(n180, 4),
            checkout_pct=round(co, 4), eff_legs=round(a["w_legs"], 1),
            matches=a["matches"], confidence=_confidence(a["w_legs"]),
        )
    return profiles


def prior_profile(name: str) -> PlayerProfile:
    """Profilo per un giocatore senza storico."""
    return PlayerProfile(name=name, confidence="prior",
                         notes=["nessuno storico: profilo = prior"], **PRIOR)
