"""Station configuration loaded from a TOML file.

Example `config/stations.toml`:

    [[stations]]
    sensor_id = "tempest:ST-00027770"
    kind = "tempest"
    label = "Backyard Tempest"
    location = "outside"
    latitude = 47.6062
    longitude = -122.3321
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class StationConfig:
    sensor_id: str
    kind: str
    label: str | None = None
    location: str | None = None
    latitude: float | None = None
    longitude: float | None = None


def load_stations(path: Path) -> list[StationConfig]:
    """Parse a stations.toml file. Returns [] if the file does not exist."""
    if not path.exists():
        return []
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    raw = data.get("stations", [])
    if not isinstance(raw, list):
        raise ValueError(f"{path}: expected an array of [[stations]] tables")
    out: list[StationConfig] = []
    for i, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ValueError(f"{path}: stations[{i}] must be a table")
        try:
            out.append(
                StationConfig(
                    sensor_id=entry["sensor_id"],
                    kind=entry["kind"],
                    label=entry.get("label"),
                    location=entry.get("location"),
                    latitude=entry.get("latitude"),
                    longitude=entry.get("longitude"),
                )
            )
        except KeyError as e:
            raise ValueError(f"{path}: stations[{i}] missing required key {e}") from e
    return out
