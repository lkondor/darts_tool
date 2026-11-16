"""Normalizzazione dei nomi tra fonti diverse.

darts1.de scrive "Gian van VEEN", globaldarts.de solo il cognome ("v.Veen").
La riconciliazione completa (alias, omonimi come Michael/Ross Smith) va fatta
quando avremo le pagine 2026 di tutte le fonti: qui c'e' solo la base.
"""
from __future__ import annotations

import re
import unicodedata


def normalize_name(raw: str) -> str:
    """'Gian van VEEN' -> 'Gian van Veen'; 'Mike DE DECKER' -> 'Mike De Decker'."""
    tokens = []
    for tok in raw.strip().split():
        if len(tok) > 1 and tok.isupper():
            tok = "-".join(part.title() for part in tok.split("-"))
        tokens.append(tok)
    return " ".join(tokens)


def surname_key(name: str) -> str:
    """Chiave di confronto approssimata: ultimo token, minuscolo, senza accenti.

    'Gian van Veen' -> 'veen'; 'v.Veen' -> 'veen'. NON distingue gli omonimi.
    """
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    text = re.sub(r"^[a-zA-Z]\.", " ", text.strip())      # 'v.Veen' -> ' Veen'
    parts = re.split(r"[\s.]+", text.strip())
    return parts[-1].lower() if parts and parts[-1] else ""
