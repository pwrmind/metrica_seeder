"""Построение пути клиента: список событий на основе конфига."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from .config import CONFIG


@dataclass
class Event:
    client_id: str
    target: str
    datetime_unix: int
    price: float
    currency: str

    def to_csv_row(self) -> dict[str, Any]:
        return {
            "ClientId": self.client_id,
            "Target": self.target,
            "DateTime": self.datetime_unix,
            "Price": self.price,
            "Currency": self.currency,
        }


def build_journey(client_id: str) -> list[Event]:
    now = int(time.time())
    events: list[Event] = []
    for target, meta in CONFIG["targets"].items():
        events.append(
            Event(
                client_id=client_id,
                target=target,
                datetime_unix=now - meta["offset_seconds"],
                price=meta["price"],
                currency=meta["currency"],
            )
        )
    return events