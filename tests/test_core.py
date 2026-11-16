import sys
from datetime import date
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from darts.adapters import SyntheticSource  # noqa: E402
from darts.formats import get_format, normalize_round  # noqa: E402
from darts.leg_model import _reference_pool, calibrate, duel_stats, generate_pool  # noqa: E402
from darts.markets import edge, fair_half_line, over_under, summarize  # noqa: E402
from darts.profiles import build_profiles  # noqa: E402
from darts.schema import Fixture, MatchFormat, PlayerProfile  # noqa: E402
from darts.simulator import project_fixture, simulate_match  # noqa: E402


def _profile(name, avg=95.0, r180=0.28, co=0.40):
    return PlayerProfile(name=name, avg3=avg, n180_per_leg=r180, checkout_pct=co)


def _fixture(a="Alfa", b="Beta", rnd="R3"):
    return Fixture("fx", date(2026, 12, 20), "Test", rnd, a, b)


def test_round_formats():
    assert normalize_round("Quarter-Finals") == "QF"
    assert get_format("F").sets_to_win == 7
    assert get_format("R1").final_set_tiebreak is False
    with pytest.raises(ValueError):
        get_format("boh")


@pytest.mark.parametrize("avg,r180,co", [(101.0, 0.42, 0.44), (93.0, 0.25, 0.39), (85.0, 0.13, 0.34)])
def test_calibration_reproduces_targets(avg, r180, co):
    params = calibrate(avg, r180, co)
    pool = generate_pool(params, 20000, np.random.default_rng(1))
    st = duel_stats(pool, _reference_pool(), 60000, np.random.default_rng(2))
    assert abs(st["avg3"] - avg) < 1.0
    assert abs(st["n180_per_leg"] - r180) < 0.03


def test_equal_players_are_coin_flip_and_thrower_has_edge():
    params = calibrate(95.0, 0.28, 0.40)
    pa = generate_pool(params, 20000, np.random.default_rng(3))
    pb = generate_pool(params, 20000, np.random.default_rng(4))
    res = simulate_match(pa, pb, get_format("R3"), 20000, np.random.default_rng(5))
    assert abs(res.a_wins.mean() - 0.5) < 0.02
    from darts.leg_model import play_legs
    rng = np.random.default_rng(6)
    out = play_legs(pa, rng.integers(0, 20000, 50000), pb, rng.integers(0, 20000, 50000),
                    np.ones(50000, dtype=bool))
    assert 0.55 < out["a_wins"].mean() < 0.75   # vantaggio di chi tira per primo


def test_set_scores_are_valid():
    params = calibrate(95.0, 0.28, 0.40)
    pool = generate_pool(params, 10000, np.random.default_rng(7))
    for rnd in ("R1", "R2", "QF", "F"):
        fmt = get_format(rnd)
        res = simulate_match(pool, pool, fmt, 5000, np.random.default_rng(8))
        s = fmt.sets_to_win
        assert ((res.sets_a == s) ^ (res.sets_b == s)).all()
        assert (np.maximum(res.sets_a, res.sets_b) == s).all()
        total_legs = res.legs_a + res.legs_b
        assert total_legs.min() >= 3 * s


def test_final_set_tiebreak_rule():
    params = calibrate(95.0, 0.28, 0.40)
    pool = generate_pool(params, 10000, np.random.default_rng(9))
    one_set_tb = MatchFormat(sets_to_win=1, final_set_tiebreak=True)
    res = simulate_match(pool, pool, one_set_tb, 20000, np.random.default_rng(10))
    w = np.maximum(res.legs_a, res.legs_b)
    l = np.minimum(res.legs_a, res.legs_b)
    assert set(zip(w.tolist(), l.tolist())) <= {(3, 0), (3, 1), (4, 2), (5, 3), (6, 4), (6, 5)}
    assert ((w == 6) & (l == 5)).any()          # leg secco sul 5-5
    one_set = MatchFormat(sets_to_win=1, final_set_tiebreak=False)
    res = simulate_match(pool, pool, one_set, 5000, np.random.default_rng(11))
    assert np.maximum(res.legs_a, res.legs_b).max() == 3


def test_deterministic_and_order_invariant():
    a, b = _profile("Alfa", 99.0, 0.36, 0.42), _profile("Beta", 92.0, 0.22, 0.38)
    r1 = project_fixture(_fixture("Alfa", "Beta"), a, b, n_sims=4000)
    r2 = project_fixture(_fixture("Alfa", "Beta"), a, b, n_sims=4000)
    r3 = project_fixture(_fixture("Beta", "Alfa"), b, a, n_sims=4000)
    assert (r1.a_wins == r2.a_wins).all()
    assert r1.a_wins.mean() == pytest.approx(1 - r3.a_wins.mean())
    assert (r1.n180_a == r3.n180_b).all()
    assert r1.a_wins.mean() > 0.6               # il piu' forte e' favorito
    assert r1.n180_a.mean() > r1.n180_b.mean()


def test_markets_are_coherent():
    a, b = _profile("Alfa", 99.0, 0.36, 0.42), _profile("Beta", 92.0, 0.22, 0.38)
    fmt = get_format("R3")
    res = project_fixture(_fixture(), a, b, n_sims=6000, fmt=fmt)
    s = summarize(res, "Alfa", "Beta", fmt.sets_to_win)
    assert s["h2h"]["p_a"] + s["h2h"]["p_b"] == pytest.approx(1.0, abs=1e-3)
    assert sum(s["correct_score_sets"].values()) == pytest.approx(1.0, abs=2e-3)
    m = s["most_180s"]
    assert m["p_a"] + m["p_tie"] + m["p_b"] == pytest.approx(1.0, abs=2e-3)
    for row in s["total_legs"]["lines"]:
        assert row["p_over"] + row["p_under"] == pytest.approx(1.0, abs=1e-3)
    # handicap -0.5 su A equivale alla vittoria di A
    h = {r["handicap"]: r["p_a_covers"] for r in s["set_handicap_a"]}
    assert h[-0.5] == pytest.approx(s["h2h"]["p_a"], abs=1e-4)
    assert [r["line"] for r in s["total_sets"]["lines"]] == [4.5, 5.5, 6.5]


def test_fair_line_uses_distribution_not_mean():
    samples = np.array([0] * 60 + [10] * 40)     # media 4, mediana 0
    assert fair_half_line(samples) in (-0.5, 0.5)
    ou = over_under(np.array([3, 4, 5, 6, 7] * 100))
    assert ou["fair_line"] in (4.5, 5.5)
    assert edge(0.55, 2.0) == pytest.approx(0.10)


def test_profiles_shrink_and_ignore_future():
    src = SyntheticSource()
    hist = src.fetch_history()
    profs = build_profiles(hist, as_of=src.as_of)
    assert len(profs) == 8
    strong, weak = profs["Giocatore A"], profs["Giocatore H"]
    assert strong.avg3 > weak.avg3 and strong.n180_per_leg > weak.n180_per_leg
    assert 85.0 < weak.avg3 < 90.0               # tirato verso il prior (90)
    assert build_profiles(hist, as_of=date(2020, 1, 1)) == {}
