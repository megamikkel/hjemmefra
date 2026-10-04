"""Travel cost approximation. Clearly marked as an estimate."""
from __future__ import annotations

from dataclasses import dataclass

from hjemmefra.domain.store import StoreDistance


@dataclass(frozen=True)
class TravelConfig:
    cost_minor_per_km: int = 250  # 2.50 kr/km (fuel + wear) documented default
    minutes_per_km: float = 2.5
    value_of_time_minor_per_minute: int = 0  # user may set own value of time
    round_trip: bool = True


def travel_cost_minor(d: StoreDistance, cfg: TravelConfig = TravelConfig()) -> int:
    km = d.distance_km * (2 if cfg.round_trip else 1)
    money = int(round(km * cfg.cost_minor_per_km))
    time_cost = int(round(km * cfg.minutes_per_km * cfg.value_of_time_minor_per_minute))
    return money + time_cost
