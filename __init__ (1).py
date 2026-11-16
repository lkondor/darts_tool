from .base import DataSource
from .synthetic import SyntheticSource

__all__ = ["DataSource", "SyntheticSource", "get_source"]


def get_source(name: str) -> DataSource:
    if name == "synthetic":
        return SyntheticSource()
    if name == "sportradar":
        from .sportradar import SportradarSource
        return SportradarSource()
    raise ValueError(f"Fonte sconosciuta: {name}")
