"""CLI-интерфейс metrica-seeder."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

from .api_client import check_upload_status, upload_conversions
from .config import CONFIG, CONFIG_PATH, load_config, require_config
from .csv_writer import write_csv
from .db import get_connection, init_db
from .id_generator import generate_client_id
from .journey_builder import build_journey


# =========================================================================
# Вспомогательные
# =========================================================================

def now_utc_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def normalize_phone(raw: str) -> str:
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    return digits


def ensure_client(phone: str, name: str = "") -> str:
    phone = normalize_phone(phone)
    if not phone:
        raise ValueError("Пустой номер телефона")

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT client_id FROM clients WHERE phone = ?", (phone,)
        ).fetchone()
        if row:
            return row["client_id"]

        client_id = generate_client_id()
        conn.execute(
            "INSERT INTO clients (phone, name, client_id, created_at) VALUES (?, ?, ?, ?)",
            (phone, name, client_id, now_utc_str()),
        )
        conn.commit()
        return client_id
    finally:
        conn.close()


def add_events_for_client(client_id: str) -> int:
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT COUNT(*) AS c FROM events WHERE client_id = ?", (client_id,)
        ).fetchone()["c"]
        if existing > 0:
            return 0

        events = build_journey(client_id)
        for ev in events:
            conn.execute(
                """
                INSERT INTO events
                    (client_id, target, datetime_unix, price, currency, status, created_at)
                VALUES (?, ?, ?, ?, ?, 'pending', ?)
                """,
                (ev.client_id, ev.target, ev.datetime_unix, ev.price, ev.currency, now_utc_str()),
            )
        conn.commit()
        return len(events)
    finally:
        conn.close()


# =========================================================================
# Команды
# =========================================================================

def cmd_check_config() -> None:
    safe = json.loads(json.dumps(CONFIG))
    if safe.get("oauth_token"):
        safe["oauth_token"] = safe["oauth_token"][:6] + "...(скрыто)"
    print(f"Конфиг загружен из: {CONFIG_PATH}")
    print(json.dumps(safe, ensure_ascii=False, indent=2))


def cmd_init() -> None:
    init_db()


def cmd_add(phone: str, name: str = "") -> None:
    client_id = ensure_client(phone, name)
    added = add_events_for_client(client_id)
    print(f"[ADD] phone={normalize_phone(phone)}  client_id={client_id}  events_added={added}")


def cmd_add_batch(file_path: str) -> None:
    path = Path(file_path)
    if not path.is_file():
        print(f"Файл не найден: {path}")
        sys.exit(1)

    total = 0
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split(",", 1)]
            phone = parts[0]
            name = parts[1] if len(parts) > 1 else ""
            try:
                client_id = ensure_client(phone, name)
                added = add_events_for_client(client_id)
                print(f"[ADD] phone={normalize_phone(phone)}  client_id={client_id}  events_added={added}")
                total += 1
            except Exception as e:
                print(f"[SKIP] {phone}: {e}")
    print(f"[BATCH] Обработано клиентов: {total}")


def cmd_upload() -> None:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, client_id, target, datetime_unix, price, currency "
            "FROM events WHERE status = 'pending' ORDER BY id"
        ).fetchall()

        if not rows:
            print("Нет событий для загрузки.")
            return

        csv_rows = [
            {
                "ClientId": r["client_id"],
                "Target": r["target"],
                "DateTime": r["datetime_unix"],
                "Price": r["price"],
                "Currency": r["currency"],
            }
            for r in rows
        ]

        csv_path = write_csv(csv_rows)
        print(f"[CSV] Сформирован файл: {csv_path}  ({len(csv_rows)} строк)")

        result = upload_conversions(csv_path)
        uploading = result.get("uploading", {})
        uploading_id = uploading.get("id")
        status = uploading.get("status", "unknown")

        print(f"[UPLOAD] id={uploading_id}  status={status}")
        print(json.dumps(result, ensure_ascii=False, indent=2))

        event_ids = [r["id"] for r in rows]
        placeholders = ",".join("?" * len(event_ids))
        conn.execute(
            f"UPDATE events SET status = 'uploaded', upload_id = ? WHERE id IN ({placeholders})",
            [uploading_id, *event_ids],
        )
        conn.execute(
            """
            INSERT INTO uploads
                (uploading_id, csv_path, status, source_quantity, line_quantity, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                uploading_id,
                str(csv_path),
                "uploaded",
                uploading.get("source_quantity", 0),
                uploading.get("line_quantity", len(csv_rows)),
                now_utc_str(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def cmd_status(uploading_id: int) -> None:
    result = check_upload_status(uploading_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    uploading = result.get("uploading", {})
    new_status = uploading.get("status")
    if new_status:
        conn = get_connection()
        try:
            conn.execute(
                "UPDATE uploads SET status = ?, processed_at = ? WHERE uploading_id = ?",
                (new_status, now_utc_str(), uploading_id),
            )
            if new_status in ("PROCESSED", "LINKAGE_FAILURE"):
                conn.execute(
                    "UPDATE events SET status = ? WHERE upload_id = ?",
                    (new_status.lower(), uploading_id),
                )
            conn.commit()
        finally:
            conn.close()


def cmd_list() -> None:
    conn = get_connection()
    try:
        print("=== Клиенты ===")
        clients = conn.execute(
            """
            SELECT c.phone, c.name, c.client_id,
                   (SELECT COUNT(*) FROM events e WHERE e.client_id = c.client_id) AS events,
                   c.created_at
            FROM clients c ORDER BY c.id
            """
        ).fetchall()
        if not clients:
            print("  (пусто)")
        for c in clients:
            print(f"  {c['phone']:>15}  {c['client_id']}  events={c['events']}  name={c['name'] or '-'}")

        print("\n=== События по статусам ===")
        rows = conn.execute("SELECT status, COUNT(*) AS c FROM events GROUP BY status").fetchall()
        if not rows:
            print("  (пусто)")
        for r in rows:
            print(f"  {r['status']:>15}: {r['c']}")

        print("\n=== Загрузки ===")
        uploads = conn.execute(
            "SELECT uploading_id, status, line_quantity, created_at, processed_at "
            "FROM uploads ORDER BY id DESC LIMIT 20"
        ).fetchall()
        if not uploads:
            print("  (пусто)")
        for u in uploads:
            print(f"  id={u['uploading_id']}  status={u['status']}  lines={u['line_quantity']}  created={u['created_at']}")
    finally:
        conn.close()


# =========================================================================
# Точка входа
# =========================================================================

USAGE = """\
Использование:
    mseeder init
    mseeder add <phone> [name]
    mseeder add-batch <file.txt>
    mseeder upload
    mseeder status <upload_id>
    mseeder list
    mseeder check-config

Конфигурация:
    config.yaml рядом с проектом.
    Переменные YM_COUNTER_ID и YM_OAUTH_TOKEN переопределяют YAML.
"""


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(USAGE)
        return 1

    load_config()
    cmd = argv[1]

    try:
        if cmd == "check-config":
            cmd_check_config()
            return 0
        if cmd == "init":
            require_config()
            cmd_init()
            return 0
        if cmd == "add":
            if len(argv) < 3:
                print("Укажите телефон: add <phone> [name]")
                return 1
            require_config()
            init_db()
            cmd_add(argv[2], argv[3] if len(argv) > 3 else "")
            return 0
        if cmd == "add-batch":
            if len(argv) < 3:
                print("Укажите файл: add-batch <file.txt>")
                return 1
            require_config()
            init_db()
            cmd_add_batch(argv[2])
            return 0
        if cmd == "upload":
            require_config()
            init_db()
            cmd_upload()
            return 0
        if cmd == "status":
            if len(argv) < 3:
                print("Укажите upload_id: status <upload_id>")
                return 1
            require_config()
            cmd_status(int(argv[2]))
            return 0
        if cmd == "list":
            require_config()
            init_db()
            cmd_list()
            return 0
        print(f"Неизвестная команда: {cmd}")
        print(USAGE)
        return 1
    except requests.HTTPError as e:
        print(f"[HTTP ERROR] {e}")
        return 2
    except Exception as e:
        print(f"[ERROR] {type(e).__name__}: {e}")
        return 3