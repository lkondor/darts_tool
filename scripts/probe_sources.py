"""Sonda le fonti storiche candidate e salva le risposte grezze.

Serve a scrivere i parser sui contenuti reali invece che su ipotesi.
Legge gli URL da config/probe_urls.txt, salva ogni risposta in probe_output/
e un riepilogo in probe_output/report.json.

Prima di usare una fonte in modo sistematico vanno letti i suoi termini d'uso.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "probe_output"
HEADERS = {"User-Agent": "Mozilla/5.0 (darts_stats_tool probe; uso personale)"}


def main() -> None:
    OUT.mkdir(exist_ok=True)
    urls = [
        line.strip() for line in (ROOT / "config" / "probe_urls.txt").read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]
    report = []
    for n, url in enumerate(urls, 1):
        entry = {"url": url}
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            ctype = resp.headers.get("content-type", "")
            ext = ".pdf" if "pdf" in ctype else ".json" if "json" in ctype else ".html"
            name = f"{n:02d}_" + re.sub(r"[^a-zA-Z0-9]+", "_", url)[:80] + ext
            (OUT / name).write_bytes(resp.content)
            entry.update(status=resp.status_code, content_type=ctype,
                         bytes=len(resp.content), saved_as=name)
        except Exception as exc:  # la sonda non deve fermarsi al primo errore
            entry.update(error=repr(exc))
        report.append(entry)
        print(entry)
        time.sleep(2)
    (OUT / "report.json").write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
