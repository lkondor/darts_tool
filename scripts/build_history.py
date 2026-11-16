"""Costruisce lo storico (data/history.json) dalle fonti in config/history_sources.csv.

Tipi di riga:
  globaldarts_event  pagina di un torneo su globaldarts.de: lo script segue i
                     link il cui testo contiene "Statistics" e ne estrae le
                     tabelle di statistiche.
  globaldarts_index  calendario annuale di globaldarts.de: lo script trova da
                     solo le pagine dei tornei dell'anno indicato nella colonna
                     `date` (solo l'anno conta) e le tratta come sopra.
  darts1_pdf         PDF "Spielrundenstatistiken" di darts1.de.

Le pagine grezze finiscono in data/raw/, il riepilogo in
data/build_report.json. Lo script non si ferma agli errori: li riporta.
Le date delle pagine globaldarts sono a livello di torneo, non di match.
Esclusi: Grand Prix (si gioca double-in, medie non confrontabili), World Cup
(coppie), tornei femminili/giovanili/WDF e gli eventi senza statistiche.
"""
from __future__ import annotations

import csv
import json
import re
import sys
import time
from collections import Counter
from datetime import date
from pathlib import Path
from urllib.parse import urljoin

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from darts.adapters.darts1 import parse_pdf  # noqa: E402
from darts.adapters.globaldarts import parse_stats_html  # noqa: E402
from darts.io import records_to_json  # noqa: E402
from darts.names import NameResolver, surname_key  # noqa: E402

DATA = ROOT / "data"
RAW = DATA / "raw"
HEADERS = {"User-Agent": "Mozilla/5.0 (darts_stats_tool; uso personale)"}
PAUSE_S = 1.2
_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], 1)}
_SKIP = re.compile(
    r"women|youth|u21|wdf|qualif|senior|pdcwc|world ?cup|grand ?prix|kleinereturniere|"
    r"challenge|development|modus|worldseries|world series", re.I)


def _soup(html: bytes):
    from bs4 import BeautifulSoup

    return BeautifulSoup(html, "html.parser")


def stat_links(html: bytes, base_url: str) -> list[str]:
    """Link (assoluti, senza duplicati) il cui testo contiene 'Statisti'."""
    out: list[str] = []
    for a in _soup(html).find_all("a"):
        href = a.get("href")
        if not href or href.startswith(("#", "mailto")):
            continue
        if "statisti" in a.get_text(" ", strip=True).lower():
            url = urljoin(base_url, href)
            if url not in out and url != base_url:
                out.append(url)
    return out


def index_events(html: bytes, base_url: str, year: int) -> list[tuple[str, str]]:
    """Dal calendario annuale: (url, nome) dei tornei dell'anno, senza duplicati."""
    out, seen = [], set()
    for a in _soup(html).find_all("a"):
        href = a.get("href")
        if not href or href.startswith(("#", "mailto")):
            continue
        url = urljoin(base_url, href.strip())
        text = a.get_text(" ", strip=True).lstrip("-> ").strip()
        if f"/Turniere{year}/" not in url or url in seen or _SKIP.search(url + " " + text):
            continue
        seen.add(url)
        out.append((url, f"{text} {year}"))
    return out


def guess_date(html: bytes, year: int) -> date | None:
    """Prima data del tipo '20. February' trovata nella pagina."""
    text = html.decode("latin-1", errors="replace")
    m = re.search(r"(\d{1,2})\.\s*(%s)" % "|".join(_MONTHS), text, flags=re.I)
    if not m:
        return None
    try:
        return date(year, _MONTHS[m[2].lower()], int(m[1]))
    except ValueError:
        return None


def _raw_name(url: str) -> str:
    return re.sub(r"[^a-zA-Z0-9.]+", "_", url)[-100:]


def _fetch(url: str, folder: str) -> bytes:
    import requests

    resp = requests.get(url, headers=HEADERS, timeout=40)
    time.sleep(PAUSE_S)
    resp.raise_for_status()
    dest = RAW / folder
    dest.mkdir(parents=True, exist_ok=True)
    (dest / _raw_name(url)).write_bytes(resp.content)
    return resp.content


def dedupe(records):
    """Se lo stesso match arriva da darts1 e da globaldarts, tiene darts1."""
    def key(rec):
        pair = frozenset((surname_key(rec.p1.player), surname_key(rec.p2.player)))
        return (rec.tournament, pair, tuple(sorted((rec.p1.legs_won, rec.p2.legs_won))))

    rich = {key(r) for r in records if r.source == "darts1"}
    return [r for r in records if r.source == "darts1" or key(r) not in rich]


def apply_names(records, resolver):
    """Porta i nomi al formato canonico. Restituisce (conteggio nomi, non risolti)."""
    names, unresolved = Counter(), {}
    for rec in records:
        for st in (rec.p1, rec.p2):
            label = st.player
            canonical, status = resolver.resolve(label)
            st.player = canonical
            names[canonical] += 1
            if status in ("ambiguous", "unknown"):
                item = unresolved.setdefault(label, {"status": status, "matches": 0,
                                                     "suggestion": resolver.suggestion(label)})
                item["matches"] += 1
    return names, unresolved


def globaldarts_event(url, tournament, fmt, stage, fixed_date, year):
    """Scarica la pagina di un torneo e tutte le sue pagine di statistiche."""
    entry = {"kind": "globaldarts_event", "url": url, "tournament": tournament, "stat_pages": []}
    records = []
    page = _fetch(url, "globaldarts")
    when = fixed_date or guess_date(page, year)
    entry["date_used"] = str(when)
    if when is None:
        raise ValueError("nessuna data trovata nella pagina")
    for n, link in enumerate(stat_links(page, url), 1):
        sub = {"url": link}
        try:
            recs = parse_stats_html(_fetch(link, "globaldarts"), tournament, when, fmt, stage)
            for rec in recs:   # id univoco anche con piu' pagine per torneo
                rec.match_id = f"globaldarts:{tournament}:p{n}:{rec.match_id.rsplit(':', 1)[-1]}"
            sub["matches"] = len(recs)
            records += recs
        except Exception as exc:
            sub["error"] = repr(exc)
        entry["stat_pages"].append(sub)
    entry["matches"] = len(records)
    return entry, records


def main() -> None:
    records, report, done = [], [], set()
    with open(ROOT / "config" / "history_sources.csv", newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    def run_event(url, tournament, fmt, stage, fixed, year):
        if url in done:
            return
        done.add(url)
        try:
            entry, recs = globaldarts_event(url, tournament, fmt, stage, fixed, year)
            records.extend(recs)
        except Exception as exc:
            entry = {"kind": "globaldarts_event", "url": url, "tournament": tournament,
                     "error": repr(exc)}
        print(f"{entry.get('matches', 0):4d} match  {tournament}  {entry.get('error', '')}")
        report.append(entry)

    for row in rows:
        kind, url = row["kind"], row["url"]
        try:
            if kind == "darts1_pdf":
                _fetch(url, "darts1")
                recs = parse_pdf(str(RAW / "darts1" / _raw_name(url)), row["tournament"],
                                 date.fromisoformat(row["date"]), row["stage"])
                records.extend(recs)
                report.append({"kind": kind, "url": url, "tournament": row["tournament"],
                               "matches": len(recs)})
                print(f"{len(recs):4d} match  {row['tournament']} (darts1)")
            elif kind == "globaldarts_event":
                fixed = date.fromisoformat(row["date"]) if row["date"] else None
                run_event(url, row["tournament"], row["format"], row["stage"], fixed, 2026)
            elif kind == "globaldarts_index":
                year = int(row["date"][:4])
                events = index_events(_fetch(url, "globaldarts"), url, year)
                report.append({"kind": kind, "url": url, "year": year, "events_found": len(events)})
                print(f"calendario {year}: {len(events)} tornei")
                for ev_url, name in events:
                    low = ev_url.lower()
                    is_wm = "pdcwm" in low
                    fmt = "sets" if is_wm or "masters" in low else "legs"
                    fixed = date(year - 1, 12, 22) if is_wm else None
                    run_event(ev_url, name, fmt, row["stage"] or "tv", fixed, year)
            else:
                raise ValueError(f"tipo sconosciuto: {kind}")
        except Exception as exc:
            report.append({"kind": kind, "url": url, "error": repr(exc)})
            print(f"ERRORE {url}: {exc!r}")

    before = len(records)
    records = dedupe(records)
    names, unresolved = apply_names(records, NameResolver.from_config(ROOT / "config"))

    records_to_json(records, DATA / "history.json")
    (DATA / "build_report.json").write_text(json.dumps({
        "matches": len(records),
        "duplicates_removed": before - len(records),
        "by_source": Counter(r.source for r in records),
        "by_tournament": Counter(r.tournament for r in records),
        "players": len(names),
        "player_names": dict(sorted(names.items())),
        "unresolved_names": unresolved,
        "sources": report,
    }, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\n{len(records)} match, {len(names)} nomi distinti -> data/history.json")


if __name__ == "__main__":
    main()
