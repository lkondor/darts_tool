"""Test dei parser sui file reali scaricati dalla sonda del 16/11/2026."""
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from darts.adapters.darts1 import parse_text  # noqa: E402
from darts.adapters.globaldarts import parse_stats_html  # noqa: E402
from darts.names import normalize_name, surname_key  # noqa: E402
from darts.profiles import build_profiles  # noqa: E402

FIX = ROOT / "tests" / "fixtures"


def _darts1():
    text = (FIX / "darts1_wm2026_viertelfinale.txt").read_text(encoding="utf-8")
    return parse_text(text, "PDC World Championship 2026", date(2026, 1, 1))


def test_darts1_quarter_finals():
    recs = _darts1()
    assert len(recs) == 4
    first = recs[0]
    assert (first.p1.player, first.p2.player) == ("Ryan Searle", "Jonny Clayton")
    assert first.format_type == "sets" and first.round == "Viertelfinale"
    assert (first.p1.sets_won, first.p2.sets_won) == (5, 2)
    assert (first.p1.legs_won, first.p2.legs_won) == (17, 10)
    assert first.set_scores[0] == (3, 1) and len(first.set_scores) == 7
    assert first.p1.average == 91.32 and first.p2.average == 93.67
    assert (first.p1.checkout_hits, first.p1.checkout_attempts) == (17, 30)
    assert (first.p1.n180, first.p2.n180) == (3, 8)
    assert first.p1.n140_plus == 16 and first.p1.n100_plus == 59
    assert first.p1.highest_checkout == 125
    # totale 180 della pagina riepilogativa del PDF
    assert sum(r.p1.n180 + r.p2.n180 for r in recs) == 60
    for r in recs:
        assert r.p1.legs_won == sum(a for a, _ in r.set_scores)
        assert r.p2.legs_won == sum(b for _, b in r.set_scores)
        assert r.p1.legs_won == r.p1.checkout_hits
    assert recs[3].p2.player == "Gian van Veen"


def test_darts1_feeds_profiles():
    profs = build_profiles(_darts1(), as_of=date(2026, 12, 11))
    assert len(profs) == 8
    assert profs["Gian van Veen"].avg3 > profs["Ryan Searle"].avg3


def test_globaldarts_uk_open():
    html = (FIX / "globaldarts_ukopen2024_statistik.html").read_bytes()
    recs = parse_stats_html(html, "UK Open 2024", date(2024, 3, 1))
    assert len(recs) == 52
    first = recs[0]
    assert (first.p1.player, first.p2.player) == ("Puha", "Klaasen")
    assert (first.p1.legs_won, first.p2.legs_won) == (6, 4)
    assert first.p1.average == 89.50 and first.p1.n180 == 2
    assert (first.p1.checkout_hits, first.p1.checkout_attempts) == (6, 12)
    assert first.round == "Mainstage"


def test_names():
    assert normalize_name("Gian van VEEN") == "Gian van Veen"
    assert normalize_name("Mike DE DECKER") == "Mike De Decker"
    assert surname_key("Gian van Veen") == surname_key("v.Veen") == "veen"


def test_darts1_final_and_leg_format():
    text = (FIX / "darts1_wm2026_finale.txt").read_text(encoding="utf-8")
    recs = parse_text(text, "PDC World Championship 2026", date(2026, 1, 3))
    assert len(recs) == 1
    fin = recs[0]
    assert (fin.p1.player, fin.p1.sets_won, fin.p2.sets_won) == ("Luke Littler", 7, 1)
    assert (fin.p1.legs_won, fin.p2.legs_won) == (23, 8)
    assert (fin.p1.n180, fin.p2.n180) == (16, 9)

    text = (FIX / "darts1_pcfinals2025_achtelfinale.txt").read_text(encoding="utf-8")
    recs = parse_text(text, "Players Championship Finals 2025", date(2025, 11, 22))
    assert len(recs) == 8
    first = recs[0]
    assert first.format_type == "legs" and first.p1.sets_won is None
    assert (first.p1.player, first.p1.legs_won, first.p2.legs_won) == ("Gerwyn Price", 10, 6)
    assert all(r.p1.legs_won == r.p1.checkout_hits for r in recs)


def test_globaldarts_european_tour_and_links():
    import importlib.util
    spec = importlib.util.spec_from_file_location("bh", ROOT / "scripts" / "build_history.py")
    bh = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bh)

    stats = (FIX / "globaldarts_et1_2026_statistik.html").read_bytes()
    recs = parse_stats_html(stats, "European Tour 1 2026", date(2026, 2, 20))
    assert len(recs) == 47                      # 16 + 16 + 8 + 4 + 2 + 1
    assert (recs[0].p1.player, recs[0].p1.legs_won, recs[0].p1.n180) == ("Littler", 8, 7)

    event = (FIX / "globaldarts_et1_2026_event.html").read_bytes()
    base = "https://globaldarts.de/globalDartsEN/Turniere/Turniere2026/europeantour26/E1Krakau.html"
    assert bh.stat_links(event, base) == [
        "https://globaldarts.de/globalDartsEN/Turniere/Turniere2026/europeantour26/Krakau4.html"]
    assert bh.guess_date(event, 2026) == date(2026, 2, 20)

    wm = (FIX / "globaldarts_wm2026_event.html").read_bytes()
    links = bh.stat_links(wm, "https://globaldarts.de/globalDartsEN/Turniere/Turniere2026/pdcwm26/pdcwm0.html")
    assert len(links) == 20 and links[0].endswith("pdcwm1.html") and links[-1].endswith("pdcwm20.html")


def test_history_roundtrip_and_dedupe(tmp_path):
    import importlib.util
    from darts.io import records_from_json, records_to_json
    spec = importlib.util.spec_from_file_location("bh", ROOT / "scripts" / "build_history.py")
    bh = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bh)

    recs = _darts1()
    records_to_json(recs, tmp_path / "h.json")
    back = records_from_json(tmp_path / "h.json")
    assert back == recs

    # lo stesso match visto da globaldarts (solo cognomi) viene scartato
    import copy
    dup = copy.deepcopy(recs[0])
    dup.source, dup.p1.player, dup.p2.player = "globaldarts", "Searle", "Clayton"
    assert len(bh.dedupe(recs + [dup])) == len(recs)
