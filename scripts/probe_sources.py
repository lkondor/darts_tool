"""Sonda le fonti storiche candidate e salva le risposte grezze.

Serve a scrivere i parser sui contenuti reali invece che su ipotesi.
Legge gli URL da config/probe_urls.txt, salva ogni risposta in probe_output/
e un riepilogo in probe_output/report.json.

Un URL preceduto da "+" viene anche esplorato: si scaricano i link dello
stesso sito trovati nella pagina (un solo livello, al massimo MAX_CHILDREN).

Prima di usare una fonte in modo sistematico vanno letti i suoi termini d'uso.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "probe_output"
HEADERS = {"User-Agent": "Mozilla/5.0 (darts_stats_tool probe; uso personale)"}
MAX_CHILDREN = 20
PAUSE_S = 1.5


def fetch(url: str, n: int, parent: str | None = None) -> tuple[dict, bytes]:
    entry: dict = {"url": url}
    if parent:
        entry["found_in"] = parent
    body = b""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        ctype = resp.headers.get("content-type", "")
        ext = ".pdf" if "pdf" in ctype else ".json" if "json" in ctype else ".html"
        name = f"{n:03d}_" + re.sub(r"[^a-zA-Z0-9]+", "_", url)[-90:] + ext
        body = resp.content
        (OUT / name).write_bytes(body)
        entry.update(status=resp.status_code, content_type=ctype, bytes=len(body), saved_as=name)
    except Exception as exc:  # la sonda non deve fermarsi al primo errore
        entry.update(error=repr(exc))
    print(entry)
    time.sleep(PAUSE_S)
    return entry, body


def child_links(base_url: str, body: bytes) -> list[str]:
    host = urlparse(base_url).netloc
    text = body.decode("latin-1", errors="replace")
    seen, out = set(), []
    for href in re.findall(r'href\s*=\s*["\']([^"\'#]+)', text, flags=re.I):
        url = urljoin(base_url, href.strip())
        parsed = urlparse(url)
        if parsed.netloc != host or url == base_url or url in seen:
            continue
        if not re.search(r"\.(html?|php|pdf)$", parsed.path, flags=re.I):
            continue
        if re.search(r"/(index|impressum)", parsed.path, flags=re.I):
            continue
        seen.add(url)
        out.append(url)
    return out[:MAX_CHILDREN]


def main() -> None:
    OUT.mkdir(exist_ok=True)
    lines = [
        ln.strip() for ln in (ROOT / "config" / "probe_urls.txt").read_text().splitlines()
        if ln.strip() and not ln.startswith("#")
    ]
    report, done, n = [], set(), 0
    for line in lines:
        crawl = line.startswith("+")
        url = line.lstrip("+").strip()
        if url in done:
            continue
        done.add(url)
        n += 1
        entry, body = fetch(url, n)
        report.append(entry)
        if crawl and entry.get("status") == 200:
            for child in child_links(url, body):
                if child in done:
                    continue
                done.add(child)
                n += 1
                report.append(fetch(child, n, parent=url)[0])
    (OUT / "report.json").write_text(json.dumps(report, indent=2))
    print(f"{n} URL sondati")


if __name__ == "__main__":
    main()
