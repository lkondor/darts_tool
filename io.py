"""Lettura e scrittura dello storico in JSON."""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import List

from .schema import MatchRecord, PlayerMatchStats


def records_to_json(records: List[MatchRecord], path: str | Path) -> None:
    rows = []
    for rec in records:
        row = asdict(rec)
        row["date"] = rec.date.isoformat()
        rows.append(row)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")


def records_from_json(path: str | Path) -> List[MatchRecord]:
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    out = []
    for row in rows:
        row = dict(row)
        row["date"] = date.fromisoformat(row["date"])
        row["p1"] = PlayerMatchStats(**row["p1"])
        row["p2"] = PlayerMatchStats(**row["p2"])
        if row.get("set_scores"):
            row["set_scores"] = [tuple(x) for x in row["set_scores"]]
        out.append(MatchRecord(**row))
    return out
