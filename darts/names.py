"""Riconciliazione dei nomi tra fonti diverse.

darts1.de scrive "Gian van VEEN"; globaldarts.de usa etichette col cognome
("v.Veen", "M.Smith", "Littler") e contiene refusi ("Aspnall"). Il
`NameResolver` porta ogni etichetta al nome completo usando:
  1. gli alias espliciti di config/name_aliases.csv (hanno la precedenza);
  2. il dizionario dei nomi completi di config/players.txt.
Le etichette che non si risolvono in modo univoco restano invariate e vengono
elencate nel report: non si indovina.
"""
from __future__ import annotations

import csv
import difflib
import re
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_PARTICLES = {"v", "d", "van", "de", "den", "der", "vd"}


def normalize_name(raw: str) -> str:
    """'Gian van VEEN' -> 'Gian van Veen'; 'Mike DE DECKER' -> 'Mike De Decker'."""
    tokens = []
    for tok in raw.strip().split():
        if len(tok) > 1 and tok.isupper():
            tok = "-".join(part.title() for part in tok.split("-"))
        tokens.append(tok)
    return " ".join(tokens)


def _ascii(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return text.replace("oe", "o").replace("ue", "u").replace("ae", "a")


def surname_key(name: str) -> str:
    """Ultimo token del nome, minuscolo e senza accenti ('v.Veen' -> 'veen')."""
    parts = [p for p in re.split(r"[\s.]+", _ascii(name).strip()) if p]
    return parts[-1] if parts else ""


def _parse_label(label: str) -> Tuple[Optional[str], str, Optional[str]]:
    """Restituisce (iniziale del nome o None, cognome, nome completo normalizzato o None)."""
    raw = label.strip()
    tokens = [t for t in re.split(r"[\s.]+", raw) if t]
    core = surname_key(raw)
    lead = tokens[:-1]
    if not lead:
        return None, core, None
    first = lead[0]
    if len(first) == 1:
        # 'v.' e 'd.' minuscoli sono particelle (van, de); una maiuscola sola e' un'iniziale
        if first.islower() or (len(lead) > 1 and all(_ascii(t) in _PARTICLES for t in lead)):
            return None, core, None
        return _ascii(first), core, None
    if _ascii(first) in _PARTICLES:
        return None, core, None
    return _ascii(first)[0], core, " ".join(_ascii(raw).split())


class NameResolver:
    def __init__(self, players: List[str], aliases: Optional[Dict[str, str]] = None):
        self.players = players
        self.aliases = {k.strip(): v.strip() for k, v in (aliases or {}).items()}
        self._full = {" ".join(_ascii(p).split()): p for p in players}
        self._by_core: Dict[str, List[str]] = {}
        for p in players:
            self._by_core.setdefault(surname_key(p), []).append(p)
        self._cache: Dict[str, Tuple[str, str]] = {}

    @classmethod
    def from_config(cls, config_dir: str | Path) -> "NameResolver":
        cfg = Path(config_dir)
        players = [ln.strip() for ln in (cfg / "players.txt").read_text(encoding="utf-8").splitlines()
                   if ln.strip() and not ln.startswith("#")]
        aliases: Dict[str, str] = {}
        alias_file = cfg / "name_aliases.csv"
        if alias_file.exists():
            with open(alias_file, newline="", encoding="utf-8") as fh:
                for row in csv.DictReader(fh):
                    aliases[row["label"]] = row["canonical"]
        return cls(players, aliases)

    def resolve(self, label: str) -> Tuple[str, str]:
        """(nome canonico, esito). Esito: alias, exact, unique, ambiguous, unknown."""
        if label not in self._cache:
            self._cache[label] = self._resolve(label)
        return self._cache[label]

    def _resolve(self, label: str) -> Tuple[str, str]:
        if label in self.aliases:
            return self.aliases[label], "alias"
        initial, core, full = _parse_label(label)
        if full and full in self._full:
            return self._full[full], "exact"
        cands = self._by_core.get(core, [])
        if not cands:
            return label, "unknown"
        if initial:
            cands = [c for c in cands if _ascii(c)[0] == initial]
        if len(cands) == 1:
            return cands[0], "unique"
        return label, "ambiguous" if cands else "unknown"

    def suggestion(self, label: str) -> Optional[str]:
        """Nome simile nel dizionario (possibile refuso). Solo un suggerimento:
        va confermato a mano in name_aliases.csv."""
        core = surname_key(label)
        if len(core) < 5:
            return None
        close = difflib.get_close_matches(core, list(self._by_core), n=1, cutoff=0.84)
        return self._by_core[close[0]][0] if close else None
