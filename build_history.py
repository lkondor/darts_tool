"""Costruisce lo storico (data/history.json) dalle fonti in config/history_sources.csv.

Tipi di riga:
  globaldarts_event  pagina di un torneo su globaldarts.de: lo script segue i
                     link il cui testo contiene "Statistics" e ne estrae le
                     tabelle Ave / 180s / Doubles.
  darts1_pdf         PDF "Spielrundenstatistiken" di darts1.de.

Le pagine grezze finiscono in data/raw/, il riepilogo in
data/build_report.json. Lo script non si ferma agli errori: li riporta.
Le date delle pagine globaldarts sono a livello di torneo (colonna `date`, o
la prima data trovata nella pagina del torneo), non del singolo match.
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
from darts.names import surname_key  # noqa: E402

DATA = ROOT / "data"
RAW = DATA / "raw"
HEADERS = {"User-Agent": "Mozilla/5.0 (darts_stats_tool; uso personale)"}
PAUSE_S = 1.2
_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], 1)}


def stat_links(html: bytes, base_url: str) -> list[str]:
    """Link (assoluti, senza duplicati) il cui testo contiene 'Statisti'."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    out: list[str] = []
    for a in soup.find_all("a"):
        href = a.get("href")
        if not href or href.startswith(("#", "mailto")):
            continue
        if "statisti" in a.get_text(" ", strip=True).lower():
            url = urljoin(base_url, href)
            if url not in out and url != base_url:
                out.append(url)
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


def _fetch(url: str, folder: str) -> bytes:
    import requests

    resp = requests.get(url, headers=HEADERS, timeout=40)
    time.sleep(PAUSE_S)
    resp.raise_for_status()
    dest = RAW / folder
    dest.mkdir(parents=True, exist_ok=True)
    (dest / re.sub(r"[^a-zA-Z0-9.]+", "_", url)[-100:]).write_bytes(resp.content)
    return resp.content


def dedupe(records):
    """Se lo stesso match arriva da darts1 e da globaldarts, tiene darts1."""
    def key(rec):
        pair = frozenset((surname_key(rec.p1.player), surname_key(rec.p2.player)))
        return (rec.tournament, pair, tuple(sorted((rec.p1.legs_won, rec.p2.legs_won))))

    rich = {key(r) for r in records if r.source == "darts1"}
    return [r for r in records if r.source == "darts1" or key(r) not in rich]


def main() -> None:
    records, report = [], []
    with open(ROOT / "config" / "history_sources.csv", newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    for row in rows:
        entry = {"kind": row["kind"], "url": row["url"], "tournament": row["tournament"]}
        try:
            fixed = date.fromisoformat(row["date"]) if row["date"] else None
            if row["kind"] == "darts1_pdf":
                _fetch(row["url"], "darts1")
                path = RAW / "darts1" / re.sub(r"[^a-zA-Z0-9.]+", "_", row["url"])[-100:]
                recs = parse_pdf(str(path), row["tournament"], fixed, row["stage"])
                entry["matches"] = len(recs)
                records += recs
            elif row["kind"] == "globaldarts_event":
                page = _fetch(row["url"], "globaldarts")
                when = fixed or guess_date(page, 2026)
                links = stat_links(page, row["url"])
                entry.update(date_used=str(when), stat_pages=[])
                if when is None:
                    raise ValueError("nessuna data: compilare la colonna date")
                for n, link in enumerate(links, 1):
                    sub = {"url": link}
                    try:
                        recs = parse_stats_html(_fetch(link, "globaldarts"), row["tournament"],
                                                when, row["format"], row["stage"])
                        for rec in recs:   # id univoco anche con piu' pagine per torneo
                            rec.match_id = f"globaldarts:{row['tournament']}:p{n}:{rec.match_id.rsplit(':', 1)[-1]}"
                        sub["matches"] = len(recs)
                        records += recs
                    except Exception as exc:
                        sub["error"] = repr(exc)
                    entry["stat_pages"].append(sub)
                entry["matches"] = sum(s.get("matches", 0) for s in entry["stat_pages"])
            else:
                raise ValueError(f"tipo sconosciuto: {row['kind']}")
        except Exception as exc:
            entry["error"] = repr(exc)
        print(f"{entry.get('matches', 0):4d} match  {row['tournament']}  {entry.get('error', '')}")
        report.append(entry)

    before = len(records)
    records = dedupe(records)
    names = Counter()
    for rec in records:
        names[rec.p1.player] += 1
        names[rec.p2.player] += 1

    records_to_json(records, DATA / "history.json")
    (DATA / "build_report.json").write_text(json.dumps({
        "matches": len(records),
        "duplicates_removed": before - len(records),
        "by_source": Counter(r.source for r in records),
        "by_tournament": Counter(r.tournament for r in records),
        "players": len(names),
        "player_names": dict(sorted(names.items())),
        "sources": report,
    }, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\n{len(records)} match, {len(names)} nomi distinti -> data/history.json")


if __name__ == "__main__":
    main()
