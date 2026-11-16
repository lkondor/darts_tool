"""Scarica e salva i payload grezzi di Sportradar per scrivere il parser.

Da eseguire UNA volta appena la chiave trial e' attiva. Ogni chiamata consuma
il budget del trial (1.000 in 30 giorni): questo script ne fa una per pagina.

Uso:
    SPORTRADAR_API_KEY=... python scripts/sportradar_dump.py --season sr:season:XXXXX --pages 1

L'id della stagione del Mondiale va letto dalla documentazione o dal portale
Sportradar: non e' noto a priori.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from darts.adapters.sportradar import SportradarSource  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", required=True, help="es. sr:season:137526")
    ap.add_argument("--pages", type=int, default=1, help="pagine da 100 risultati")
    args = ap.parse_args()

    src = SportradarSource()
    for page in range(args.pages):
        payload = src.season_summaries(args.season, start=page * 100)
        print(f"pagina {page}: chiavi di primo livello = {list(payload.keys())}")
    print(f"Chiamate usate finora: {src.calls_used()}")
    print(f"Payload salvati in {src.raw_dir}")


if __name__ == "__main__":
    main()
