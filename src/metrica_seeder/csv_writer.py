"""Формирование CSV-файла для загрузки в Метрику."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from .config import get_csv_path

CSV_FIELDS = ["ClientId", "Target", "DateTime", "Price", "Currency"]


def write_csv(rows: list[dict[str, Any]], path: Path | None = None) -> Path:
    path = path or get_csv_path()
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return path