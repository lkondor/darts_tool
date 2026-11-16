"""Modello del leg (501, double out), a livello di visita.

Idea: per ogni giocatore si genera un "pool" di leg giocati da solo, visita
per visita. Un leg tra A e B si ottiene pescando un leg dal pool di A e uno
dal pool di B: vince chi chiude in meno visite (a parita' vince chi tira per
primo). I 180 del perdente sono quelli fatti nelle visite che ha
effettivamente tirato. Ipotesi: i due giocatori sono indipendenti (nessun
effetto pressione).

I parametri di visita non sono osservabili direttamente dalle statistiche
aggregate, quindi vengono calibrati: si cercano i valori che, in un leg
contro un avversario di riferimento, riproducono la media 3 freccette e i
180 per leg del profilo.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np

START_SCORE = 501
MAX_VISITS = 30

# Punteggi tipici di una visita di scoring diversa dal 180, con pesi di base.
# La forma viene "inclinata" (exponential tilting) per centrare la media.
_VALUES = np.array([26, 41, 45, 55, 60, 81, 85, 95, 100, 121, 125, 135, 140], dtype=float)
_WEIGHTS = np.array([3, 6, 7, 3, 12, 9, 9, 8, 14, 4, 4, 5, 12], dtype=float)
_BOGEY = np.array([159, 162, 163, 165, 166, 168, 169])


@dataclass(frozen=True)
class LegParams:
    scoring_mean: float   # media della visita di scoring (180 inclusi)
    p180: float           # P(180) per visita di scoring
    double_rate: float    # P(centrare il doppio) per freccetta
    skill: float          # avg3 / 95, limitato: scala i setup di chiusura


@dataclass
class LegPool:
    n_visits: np.ndarray    # (N,) visite per chiudere il leg
    last_darts: np.ndarray  # (N,) freccette usate nell'ultima visita
    cum180: np.ndarray      # (N, V+1) 180 cumulati dopo k visite
    cumscore: np.ndarray    # (N, V+1) punti cumulati dopo k visite

    def __len__(self) -> int:
        return len(self.n_visits)


def _tilted_probs(target_mean: float) -> np.ndarray:
    """Pesi sui punteggi non-180 con media = target_mean."""
    target_mean = float(np.clip(target_mean, 32.0, 134.0))
    x = (_VALUES - 90.0) / 40.0
    lo, hi = -12.0, 12.0
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        w = _WEIGHTS * np.exp(mid * x)
        mean = float((w * _VALUES).sum() / w.sum())
        if mean < target_mean:
            lo = mid
        else:
            hi = mid
    w = _WEIGHTS * np.exp(0.5 * (lo + hi) * x)
    return w / w.sum()


def visit_distribution(params: LegParams):
    """Valori e probabilita' della visita di scoring."""
    p180 = float(np.clip(params.p180, 0.0, 0.6))
    non180_mean = (params.scoring_mean - 180.0 * p180) / (1.0 - p180)
    probs = _tilted_probs(non180_mean) * (1.0 - p180)
    values = np.append(_VALUES, 180.0).astype(np.int32)
    return values, np.append(probs, p180)


def generate_pool(params: LegParams, n_legs: int, rng: np.random.Generator) -> LegPool:
    """Simula n_legs leg in solitaria, visita per visita (vettorizzato)."""
    values, probs = visit_distribution(params)
    d = float(np.clip(params.double_rate, 0.05, 0.9))
    s = params.skill
    q1 = min(0.95, 0.85 * s)   # 41-70: una freccetta di setup
    q2 = min(0.80, 0.50 * s)   # 71-100: due freccette di setup
    q_d = min(0.60, 0.30 * s)  # 101-135: setup di una chiusura a 3 freccette
    q_e = min(0.30, 0.10 * s)  # 136-170

    n = n_legs
    r = np.full(n, START_SCORE, dtype=np.int32)
    done = np.zeros(n, dtype=bool)
    n_visits = np.zeros(n, dtype=np.int16)
    last_darts = np.full(n, 3, dtype=np.int8)
    scores = np.zeros((n, MAX_VISITS), dtype=np.int16)

    for v in range(MAX_VISITS):
        act = ~done
        if not act.any():
            break
        u = rng.random((n, 3))
        draw = values[rng.choice(len(values), size=n, p=probs)]

        score = np.zeros(n, dtype=np.int32)
        fin = np.zeros(n, dtype=bool)
        darts = np.full(n, 3, dtype=np.int8)

        # --- scoring (resto > 170) ---
        sc = act & (r > 170)
        s_draw = np.where(r - draw < 2, r - 32, draw)  # niente bust: lascia 32
        score = np.where(sc, s_draw, score)

        hit = u < d
        # --- zona A: resto <= 40, tre freccette al doppio ---
        za = act & (r <= 40)
        fin_a = hit.any(axis=1)
        darts_a = np.where(hit[:, 0], 1, np.where(hit[:, 1], 2, 3))
        fin |= za & fin_a
        darts = np.where(za & fin_a, darts_a, darts)

        # --- zona B: 41-70, setup + due freccette al doppio ---
        zb = act & (r > 40) & (r <= 70)
        setup_b = u[:, 0] < q1
        fin_b = setup_b & (hit[:, 1] | hit[:, 2])
        fin |= zb & fin_b
        darts = np.where(zb & fin_b, np.where(hit[:, 1], 2, 3), darts)
        left_b = np.where(setup_b, 32, 40)
        score = np.where(zb & ~fin_b, r - left_b, score)

        # --- zona C: 71-100, due setup + una freccetta al doppio ---
        zc = act & (r > 70) & (r <= 100)
        setup_c = u[:, 0] < q2
        fin_c = setup_c & hit[:, 2]
        fin |= zc & fin_c
        left_c = np.where(setup_c, 32, np.where(u[:, 1] < 0.7, 40, 60))
        score = np.where(zc & ~fin_c, r - left_c, score)

        # --- zona D: 101-135 ---
        zd = act & (r > 100) & (r <= 135)
        fin_d = u[:, 0] < q_d * d
        fin |= zd & fin_d
        left_d = np.where(u[:, 1] < 0.65, 40, 60)
        score = np.where(zd & ~fin_d, r - left_d, score)

        # --- zona E: 136-170 (i bogey non si chiudono) ---
        ze = act & (r > 135) & (r <= 170)
        fin_e = (u[:, 0] < q_e * d) & ~np.isin(r, _BOGEY)
        fin |= ze & fin_e
        score = np.where(ze & ~fin_e, np.where(u[:, 1] < 0.6, 100, 60), score)

        if v == MAX_VISITS - 1:      # sicurezza: chiusura forzata
            fin |= act
        fin &= act
        score = np.where(fin, r, score)
        score = np.where(act, score, 0)

        scores[:, v] = score
        r = r - score
        n_visits = np.where(fin, v + 1, n_visits).astype(np.int16)
        last_darts = np.where(fin, darts, last_darts).astype(np.int8)
        done |= fin

    pad = np.zeros((n, 1), dtype=np.int32)
    cum180 = np.concatenate([pad, np.cumsum(scores == 180, axis=1)], axis=1).astype(np.int16)
    cumscore = np.concatenate([pad, np.cumsum(scores, axis=1, dtype=np.int32)], axis=1)
    return LegPool(n_visits=n_visits, last_darts=last_darts, cum180=cum180, cumscore=cumscore)


def concat_pools(pools) -> LegPool:
    """Unisce piu' pool in uno solo (blocchi consecutivi della stessa dimensione)."""
    return LegPool(
        n_visits=np.concatenate([p.n_visits for p in pools]),
        last_darts=np.concatenate([p.last_darts for p in pools]),
        cum180=np.concatenate([p.cum180 for p in pools]),
        cumscore=np.concatenate([p.cumscore for p in pools]),
    )


def play_legs(pool_a: LegPool, idx_a, pool_b: LegPool, idx_b, a_starts):
    """Gioca un leg per ogni elemento degli array. Restituisce un dict di array."""
    va = pool_a.n_visits[idx_a].astype(np.int32)
    vb = pool_b.n_visits[idx_b].astype(np.int32)
    a_wins = np.where(a_starts, va <= vb, va < vb)

    # visite effettivamente tirate
    thrown_a = np.where(a_wins, va, np.where(a_starts, vb, vb - 1))
    thrown_b = np.where(a_wins, np.where(a_starts, va - 1, va), vb)

    darts_a = np.where(a_wins, 3 * (va - 1) + pool_a.last_darts[idx_a], 3 * thrown_a)
    darts_b = np.where(a_wins, 3 * thrown_b, 3 * (vb - 1) + pool_b.last_darts[idx_b])
    return {
        "a_wins": a_wins,
        "n180_a": pool_a.cum180[idx_a, thrown_a],
        "n180_b": pool_b.cum180[idx_b, thrown_b],
        "darts_a": darts_a,
        "darts_b": darts_b,
        "points_a": pool_a.cumscore[idx_a, thrown_a],
        "points_b": pool_b.cumscore[idx_b, thrown_b],
    }


def _initial_params(avg3: float, n180_per_leg: float, checkout_pct: float) -> LegParams:
    skill = float(np.clip(avg3 / 95.0, 0.75, 1.25))
    return LegParams(
        scoring_mean=avg3 * 1.08,
        p180=float(np.clip(n180_per_leg / 4.3, 0.002, 0.5)),
        double_rate=checkout_pct,
        skill=skill,
    )


@lru_cache(maxsize=1)
def _reference_pool() -> LegPool:
    """Avversario di riferimento per la calibrazione (livello medio da tour)."""
    return generate_pool(_initial_params(92.0, 0.25, 0.40), 8000, np.random.default_rng(777))


def duel_stats(pool: LegPool, opp: LegPool, n: int, rng: np.random.Generator) -> dict:
    """Statistiche emergenti del giocatore del pool contro `opp`."""
    out = play_legs(
        pool, rng.integers(0, len(pool), n),
        opp, rng.integers(0, len(opp), n),
        rng.random(n) < 0.5,
    )
    return {
        "avg3": 3.0 * out["points_a"].sum() / out["darts_a"].sum(),
        "n180_per_leg": out["n180_a"].mean(),
        "leg_win": out["a_wins"].mean(),
    }


@lru_cache(maxsize=4096)
def _calibrate_cached(avg3: float, n180_per_leg: float, checkout_pct: float) -> LegParams:
    params = _initial_params(avg3, n180_per_leg, checkout_pct)
    ref = _reference_pool()
    m, p = params.scoring_mean, params.p180
    for _ in range(8):
        params = LegParams(m, p, params.double_rate, params.skill)
        pool = generate_pool(params, 6000, np.random.default_rng(12345))
        st = duel_stats(pool, ref, 20000, np.random.default_rng(54321))
        m = float(m + 0.9 * (avg3 - st["avg3"]))
        p = float(np.clip(p * (n180_per_leg / max(st["n180_per_leg"], 1e-6)) ** 0.9, 0.001, 0.55))
    return LegParams(m, p, params.double_rate, params.skill)


def calibrate(avg3: float, n180_per_leg: float, checkout_pct: float) -> LegParams:
    """Parametri di visita che riproducono media, 180/leg e checkout % dati."""
    return _calibrate_cached(round(avg3, 1), round(n180_per_leg, 3), round(checkout_pct, 3))
