"""Simulatore Monte Carlo del match a set (vettorizzato sulle simulazioni)."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np

from .formats import get_format
from .leg_model import LegPool, calibrate, concat_pools, generate_pool, play_legs
from .schema import Fixture, MatchFormat, PlayerProfile

DEFAULT_SIMS = 10_000

# Varianza di forma tra un match e l'altro, stimata sullo storico reale 2026
# (964 match): la media di un giocatore oscilla da match a match piu' di quanto
# spieghi il solo rumore campionario, e i 180 sono piu' dispersi di una Poisson.
FORM_SD_AVG = 2.0     # punti di media 3 freccette
FORM_SD_180 = 0.40    # deviazione standard del logaritmo del tasso di 180
BLOCK_SIZE = 6_000    # leg simulati per ciascun livello di forma

_Z_AVG = np.array([-1.2816, -0.5244, 0.0, 0.5244, 1.2816])
_Z_AVG = _Z_AVG / _Z_AVG.std()               # 5 livelli equiprobabili, varianza 1
_Z_180 = np.array([-1.2247, 0.0, 1.2247])    # 3 livelli equiprobabili, varianza 1


@dataclass
class FormPool:
    """Pool di leg di un giocatore, a blocchi: un blocco per livello di forma."""

    pool: LegPool
    n_blocks: int
    block_size: int


def _as_form_pool(pool) -> FormPool:
    return pool if isinstance(pool, FormPool) else FormPool(pool, 1, len(pool))


@dataclass
class SimResult:
    """Esito di ogni simulazione, dal punto di vista di (A, B)."""

    a_wins: np.ndarray
    sets_a: np.ndarray
    sets_b: np.ndarray
    legs_a: np.ndarray
    legs_b: np.ndarray
    n180_a: np.ndarray
    n180_b: np.ndarray

    def mirror(self) -> "SimResult":
        return SimResult(
            a_wins=~self.a_wins,
            sets_a=self.sets_b, sets_b=self.sets_a,
            legs_a=self.legs_b, legs_b=self.legs_a,
            n180_a=self.n180_b, n180_b=self.n180_a,
        )


def simulate_match(pool_a, pool_b, fmt: MatchFormat,
                   n_sims: int, rng: np.random.Generator) -> SimResult:
    """pool_a / pool_b: LegPool oppure FormPool. Con un FormPool ogni
    simulazione estrae un livello di forma per giocatore, valido per tutto il match."""
    n = n_sims
    fa, fb = _as_form_pool(pool_a), _as_form_pool(pool_b)
    pool_a, pool_b = fa.pool, fb.pool
    off_a = rng.integers(0, fa.n_blocks, n) * fa.block_size
    off_b = rng.integers(0, fb.n_blocks, n) * fb.block_size
    S, L = fmt.sets_to_win, fmt.legs_per_set_to_win
    sd_legs = fmt.tiebreak_sudden_death_at + 1

    sets_a = np.zeros(n, dtype=np.int16)
    sets_b = np.zeros(n, dtype=np.int16)
    la = np.zeros(n, dtype=np.int16)      # leg nel set corrente
    lb = np.zeros(n, dtype=np.int16)
    tot_a = np.zeros(n, dtype=np.int16)
    tot_b = np.zeros(n, dtype=np.int16)
    n180_a = np.zeros(n, dtype=np.int32)
    n180_b = np.zeros(n, dtype=np.int32)
    leg_in_set = np.zeros(n, dtype=np.int16)
    # Chi tira per primo nel match si decide al bull: 50/50.
    set_starter_a = rng.random(n) < 0.5
    done = np.zeros(n, dtype=bool)

    max_legs = (2 * S - 1) * (2 * L - 1) + 2 * sd_legs + 2
    for _ in range(max_legs):
        act = ~done
        if not act.any():
            break
        a_starts = set_starter_a ^ (leg_in_set % 2 == 1)
        out = play_legs(
            pool_a, off_a + rng.integers(0, fa.block_size, n),
            pool_b, off_b + rng.integers(0, fb.block_size, n),
            a_starts,
        )
        aw = out["a_wins"] & act
        bw = ~out["a_wins"] & act
        la += aw
        lb += bw
        tot_a += aw
        tot_b += bw
        n180_a += np.where(act, out["n180_a"], 0)
        n180_b += np.where(act, out["n180_b"], 0)

        deciding = fmt.final_set_tiebreak & (sets_a == S - 1) & (sets_b == S - 1)
        win_a = np.where(deciding, ((la >= L) & (la - lb >= 2)) | (la >= sd_legs), la >= L) & act
        win_b = np.where(deciding, ((lb >= L) & (lb - la >= 2)) | (lb >= sd_legs), lb >= L) & act
        set_over = win_a | win_b

        sets_a += win_a
        sets_b += win_b
        la = np.where(set_over, 0, la)
        lb = np.where(set_over, 0, lb)
        leg_in_set = np.where(set_over, 0, leg_in_set + act)
        set_starter_a = np.where(set_over, ~set_starter_a, set_starter_a)
        done |= (sets_a == S) | (sets_b == S)

    if not done.all():
        raise RuntimeError("Simulazione non terminata: controllare il formato")
    return SimResult(sets_a == S, sets_a, sets_b, tot_a, tot_b, n180_a, n180_b)


def _seed(*parts: str) -> int:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def player_pool(profile: PlayerProfile, seed: int, form: bool = True) -> FormPool:
    """Pool del giocatore. Con form=True: 15 blocchi (5 livelli di media x 3 di 180)."""
    rng = np.random.default_rng(seed)
    if not form:
        params = calibrate(profile.avg3, profile.n180_per_leg, profile.checkout_pct)
        return FormPool(generate_pool(params, BLOCK_SIZE * 3, rng), 1, BLOCK_SIZE * 3)
    blocks = []
    for za in _Z_AVG:
        for zk in _Z_180:
            avg = profile.avg3 + FORM_SD_AVG * za
            rate = profile.n180_per_leg * float(np.exp(FORM_SD_180 * zk - 0.5 * FORM_SD_180 ** 2))
            blocks.append(generate_pool(calibrate(avg, rate, profile.checkout_pct), BLOCK_SIZE, rng))
    return FormPool(concat_pools(blocks), len(blocks), BLOCK_SIZE)


def project_fixture(fixture: Fixture, prof_a: PlayerProfile, prof_b: PlayerProfile,
                    n_sims: int = DEFAULT_SIMS, fmt: MatchFormat | None = None,
                    form: bool = True) -> SimResult:
    """Simula un match in calendario.

    Deterministico: il seed deriva dall'identita' del match. I giocatori
    vengono ordinati in modo canonico, cosi' il risultato non dipende
    dall'ordine in cui sono elencati.
    """
    fmt = fmt or get_format(fixture.round)
    swap = prof_a.name > prof_b.name
    first, second = (prof_b, prof_a) if swap else (prof_a, prof_b)
    key = (first.name, second.name, fixture.date.isoformat(), fixture.tournament, fixture.round)
    pool_1 = player_pool(first, _seed("pool", first.name, *key), form)
    pool_2 = player_pool(second, _seed("pool", second.name, *key), form)
    res = simulate_match(pool_1, pool_2, fmt, n_sims, np.random.default_rng(_seed("match", *key)))
    return res.mirror() if swap else res
