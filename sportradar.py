"""Adapter Sportradar Darts API v2 - PROVVISORIO.

Cosa e' gia' pronto:
  - client HTTP con chiave da variabile d'ambiente SPORTRADAR_API_KEY
  - contatore delle chiamate (il trial ne concede 1.000 in 30 giorni, 1/sec)
  - salvataggio di ogni risposta grezza in data/raw/sportradar/

Cosa manca volutamente:
  - il parsing verso lo schema canonico. Va scritto sui payload reali, non su
    uno schema ipotizzato. Appena la chiave e' attiva: eseguire
    `scripts/sportradar_dump.py`, caricare i JSON salvati e completare
    `_parse_summaries`.

Unico endpoint visto nella documentazione pubblica (change log, 31/08/2026):
    /seasons/{season_id}/summaries   (paginato con ?start=N)
Gli altri endpoint vanno letti dalla documentazione al momento dell'uso.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import List

from ..schema import Fixture, MatchRecord
from .base import DataSource

BASE_URL = "https://api.sportradar.com/darts/trial/v2/en"
CALL_BUDGET = 950          # margine sotto le 1.000 del trial
MIN_INTERVAL_S = 1.2       # limite: 1 richiesta al secondo


class SportradarSource(DataSource):
    name = "sportradar"

    def __init__(self, data_dir: str = "data"):
        self.api_key = os.environ.get("SPORTRADAR_API_KEY", "")
        self.raw_dir = Path(data_dir) / "raw" / "sportradar"
        self.counter_file = Path(data_dir) / "sportradar_calls.json"
        self._last_call = 0.0

    # ---- budget -----------------------------------------------------------
    def calls_used(self) -> int:
        if self.counter_file.exists():
            return int(json.loads(self.counter_file.read_text()).get("calls", 0))
        return 0

    def _count_call(self) -> None:
        self.counter_file.parent.mkdir(parents=True, exist_ok=True)
        self.counter_file.write_text(json.dumps({"calls": self.calls_used() + 1}))

    # ---- HTTP -------------------------------------------------------------
    def get(self, path: str, params: dict | None = None) -> dict:
        import requests  # import locale: non serve per la fonte sintetica

        if not self.api_key:
            raise RuntimeError("SPORTRADAR_API_KEY non impostata")
        if self.calls_used() >= CALL_BUDGET:
            raise RuntimeError(f"Budget chiamate esaurito ({CALL_BUDGET})")
        wait = MIN_INTERVAL_S - (time.time() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        url = f"{BASE_URL}/{path.strip('/')}.json"
        resp = requests.get(url, params=params, headers={"x-api-key": self.api_key}, timeout=30)
        self._last_call = time.time()
        self._count_call()
        resp.raise_for_status()
        payload = resp.json()

        self.raw_dir.mkdir(parents=True, exist_ok=True)
        tag = path.strip("/").replace("/", "_").replace(":", "-")
        suffix = f"_start{params['start']}" if params and "start" in params else ""
        (self.raw_dir / f"{tag}{suffix}.json").write_text(json.dumps(payload, indent=2))
        return payload

    def season_summaries(self, season_id: str, start: int = 0) -> dict:
        return self.get(f"seasons/{season_id}/summaries", {"start": start} if start else None)

    # ---- schema canonico --------------------------------------------------
    def _parse_summaries(self, payload: dict):
        raise NotImplementedError(
            "Parser da scrivere sui payload reali salvati in data/raw/sportradar/")

    def fetch_history(self) -> List[MatchRecord]:
        raise NotImplementedError("In attesa dei payload reali (vedi docstring)")

    def fetch_fixtures(self) -> List[Fixture]:
        raise NotImplementedError("In attesa dei payload reali (vedi docstring)")
