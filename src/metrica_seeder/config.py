"""Загрузка конфигурации из YAML с переопределением через переменные окружения."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import yaml

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = BASE_DIR / "config.yaml"

DEFAULTS: dict[str, Any] = {
    "counter_id": "",
    "oauth_token": "",
    "client_id_type": "CLIENT_ID",
    "paths": {"db": "journey.db", "csv": "offline_conversions.csv"},
    "targets": {
        "order_created": {"price": 0, "currency": "RUB", "offset_seconds": 86400},
        "order_paid": {"price": 3000, "currency": "RUB", "offset_seconds": 3600},
    },
    "http": {"timeout_upload": 60, "timeout_get": 30},
}

CONFIG: dict[str, Any] = {}


def _merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


def _resolve_path(value: str) -> Path:
    p = Path(value)
    return p if p.is_absolute() else (BASE_DIR / p)


def get_db_path() -> Path:
    return _resolve_path(CONFIG["paths"]["db"])


def get_csv_path() -> Path:
    return _resolve_path(CONFIG["paths"]["csv"])


def load_config() -> dict[str, Any]:
    """Читает YAML, накладывает поверх DEFAULTS, переопределяет env. Мутирует CONFIG."""
    user_cfg: dict[str, Any] = {}

    if CONFIG_PATH.is_file():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f)
                if isinstance(loaded, dict):
                    user_cfg = loaded
        except yaml.YAMLError as e:
            print(f"Ошибка чтения {CONFIG_PATH}: {e}")
            sys.exit(1)
    else:
        print(f"[WARN] Файл {CONFIG_PATH.name} не найден. Использую дефолты.")

    cfg = _merge(DEFAULTS, user_cfg)

    env_counter = os.getenv("YM_COUNTER_ID", "").strip()
    env_token = os.getenv("YM_OAUTH_TOKEN", "").strip()
    if env_counter:
        cfg["counter_id"] = env_counter
    if env_token:
        cfg["oauth_token"] = env_token

    cfg["counter_id"] = str(cfg.get("counter_id") or "").strip()
    cfg["oauth_token"] = str(cfg.get("oauth_token") or "").strip()
    cfg["client_id_type"] = str(cfg.get("client_id_type") or "CLIENT_ID").upper()

    targets: dict[str, dict] = {}
    for name, meta in (cfg.get("targets") or {}).items():
        if not isinstance(meta, dict):
            continue
        targets[str(name)] = {
            "price": float(meta.get("price", 0) or 0),
            "currency": str(meta.get("currency") or "RUB"),
            "offset_seconds": int(meta.get("offset_seconds", 0) or 0),
        }
    cfg["targets"] = targets

    CONFIG.clear()
    CONFIG.update(cfg)
    return CONFIG


def require_config() -> None:
    missing = []
    if not CONFIG.get("counter_id"):
        missing.append("counter_id (или YM_COUNTER_ID)")
    if not CONFIG.get("oauth_token"):
        missing.append("oauth_token (или YM_OAUTH_TOKEN)")
    if missing:
        print("Ошибка: не заданы обязательные настройки:")
        for m in missing:
            print(f"  - {m}")
        sys.exit(1)