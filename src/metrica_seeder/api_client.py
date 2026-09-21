"""HTTP-клиент для API Яндекс.Метрики (offline_conversions)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import requests

from .config import CONFIG

API_BASE = "https://api-metrika.yandex.net/management/v1"


def _headers() -> dict[str, str]:
    return {"Authorization": f"OAuth {CONFIG['oauth_token']}"}


def _check_response(resp: requests.Response) -> dict[str, Any]:
    if resp.status_code >= 400:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:500]}")
    try:
        return resp.json()
    except ValueError:
        return {"raw": resp.text}


def upload_conversions(csv_path: Path) -> dict[str, Any]:
    counter = CONFIG["counter_id"]
    client_id_type = CONFIG["client_id_type"]
    timeout = int(CONFIG["http"]["timeout_upload"])
    url = f"{API_BASE}/counter/{counter}/offline_conversions/upload"
    params = {"client_id_type": client_id_type}

    with open(csv_path, "rb") as f:
        files = {"file": (csv_path.name, f, "text/csv")}
        resp = requests.post(
            url, params=params, files=files, headers=_headers(), timeout=timeout
        )
    return _check_response(resp)


def check_upload_status(uploading_id: int) -> dict[str, Any]:
    counter = CONFIG["counter_id"]
    timeout = int(CONFIG["http"]["timeout_get"])
    url = f"{API_BASE}/counter/{counter}/offline_conversions/uploading/{uploading_id}"
    resp = requests.get(url, headers=_headers(), timeout=timeout)
    return _check_response(resp)


def list_uploadings() -> dict[str, Any]:
    counter = CONFIG["counter_id"]
    timeout = int(CONFIG["http"]["timeout_get"])
    url = f"{API_BASE}/counter/{counter}/offline_conversions/uploadings"
    resp = requests.get(url, headers=_headers(), timeout=timeout)
    return _check_response(resp)