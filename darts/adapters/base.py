"""Interfaccia comune delle fonti dati."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from ..schema import Fixture, MatchRecord


class DataSource(ABC):
    """Ogni fonte implementa questi due metodi e restituisce lo schema canonico."""

    name: str = "base"

    @abstractmethod
    def fetch_history(self) -> List[MatchRecord]:
        """Match conclusi con statistiche."""

    @abstractmethod
    def fetch_fixtures(self) -> List[Fixture]:
        """Match in calendario."""
