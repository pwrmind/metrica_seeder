# metrica-seeder

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

CLI-инструмент для «прогонки» реальных клиентов по пути customer journey и загрузки офлайн-конверсий в Яндекс.Метрику.

Полезен, когда сайт новый, а база клиентов — старая: нужно наполнить дашборды Метрики данными о визитах, заявках и оплатах, чтобы отчёты не были пустыми.

---

## ⚠️ Чего инструмент не делает

Чтобы не было недопонимания — сразу обозначим границы:

- **Не создаёт реальные визиты на сайте.** Визиты остаются виртуальными: Метрика принимает офлайн-конверсии через официальный `offline_conversions/upload`, но источник трафика у них будет пустым (`Прямые заходы`).
- **Не эмулирует клики по рекламе.** Если нужна атрибуция к Директу — сначала нужен реальный `yclid`.
- **Не заменяет сквозную аналитику с реального сайта.** Это дополнение для восстановления истории, а не для подмены данных.
- **Не работает как «накрутка».** Инструмент предназначен для реальных клиентов, у которых есть подтверждённый телефон или email.

---

## 📦 Установка

Требуется Python 3.10+ и [uv](https://github.com/astral-sh/uv).

```bash
git clone https://github.com/yourname/metrica-seeder.git
cd metrica-seeder
uv sync
```

После `uv sync` в окружении появится команда `mseeder`.

---

## 🚀 Быстрый старт

### 1. Заполнить конфиг

Открой `config.yaml` и впиши свои значения:

```yaml
counter_id: "12345678"                    # номер счётчика Метрики
oauth_token: "y0__xxxxxxxxxxxxxxxx"       # OAuth-токен
```

Токен можно получить в [oauth.yandex.ru](https://oauth.yandex.ru/) с правами `metrika:write`.

### 2. Создать цели в Метрике

В интерфейсе Метрики → **Настройки → Цели** создай две цели типа «JavaScript-событие»:

| Идентификатор цели | Что означает |
|---|---|
| `order_created` | Заявка оставлена |
| `order_paid` | Заявка оплачена |

Имена целей могут быть любыми, но **идентификаторы должны совпадать** с ключами в `targets` в `config.yaml`.

Также включи **Настройки → Загрузка данных → Офлайн-конверсии**.

### 3. Проверить конфиг

```bash
uv run mseeder check-config
```

Должен показать JSON с твоими настройками. Токен маскируется.

### 4. Инициализировать базу

```bash
uv run mseeder init
```

Создаст `journey.db` — SQLite-файл с тремя таблицами: `clients`, `events`, `uploads`.

### 5. Добавить клиентов

По одному:

```bash
uv run mseeder add "+79154636270" "Иван"
```

Пакетно из файла:

```bash
uv run mseeder add-batch phones.txt
```

Формат `phones.txt` — по строке на клиента, `телефон[,имя]`:

```
+79154636270,Иван
+79161234567,Мария
# строки, начинающиеся с #, игнорируются
```

### 6. Посмотреть состояние

```bash
uv run mseeder list
```

Покажет список клиентов, статистику событий и историю загрузок.

### 7. Загрузить в Метрику

```bash
uv run mseeder upload
```

Соберёт все события со статусом `pending`, сформирует CSV и отправит через `offline_conversions/upload`.

### 8. Проверить статус через 2–3 часа

```bash
uv run mseeder status 12345
```

Возможные статусы:

| Статус | Значение |
|---|---|
| `PREPARED` | файл принят, обработка не началась |
| `UPLOADED` | файл загружен |
| `MATCHED` | ID сопоставлены |
| `PROCESSED` | ✅ успех, данные в отчётах |
| `LINKAGE_FAILURE` | ❌ ClientID не сопоставлены |

---

## 🛠️ Команды

| Команда | Что делает |
|---|---|
| `mseeder check-config` | Показать текущий конфиг (токен маскируется) |
| `mseeder init` | Создать/обновить схему БД |
| `mseeder add <phone> [name]` | Добавить одного клиента |
| `mseeder add-batch <file>` | Добавить клиентов из файла |
| `mseeder list` | Показать клиентов, события и загрузки |
| `mseeder upload` | Отправить pending-события в Метрику |
| `mseeder status <id>` | Проверить статус загрузки |

---

## ⚙️ Конфигурация

### `config.yaml`

```yaml
counter_id: ""                    # номер счётчика
oauth_token: ""                   # OAuth-токен
client_id_type: "CLIENT_ID"       # CLIENT_ID | USER_ID | YCLID

paths:
  db:  "journey.db"
  csv: "offline_conversions.csv"

targets:
  order_created:
    price: 0
    currency: "RUB"
    offset_seconds: 86400         # 24 часа назад
  order_paid:
    price: 3000
    currency: "RUB"
    offset_seconds: 3600          # 1 час назад

http:
  timeout_upload: 60
  timeout_get:    30
```

### Переопределение через env

Переменные окружения имеют приоритет над YAML. Удобно для CI и хранения секретов вне репозитория:

```bash
export YM_COUNTER_ID=12345678
export YM_OAUTH_TOKEN=y0__xxxxxxxx
uv run mseeder upload
```

---

## 🔍 Как это работает

1. **Генерация ClientID.** Для каждого клиента создаётся уникальный ClientID по алгоритму, аналогичному Яндекс.Метрике: `Unix-время в секундах + случайное число`. Пример: `1758386400123456789`.

2. **Построение пути.** По целям из `config.yaml` формируется цепочка событий: `order_created` → `order_paid`. Каждое событие получает `DateTime` в прошлом (сдвиг задаётся в `offset_seconds`).

3. **Формирование CSV.** События собираются в файл с колонками `ClientId, Target, DateTime, Price, Currency`.

4. **Загрузка.** Файл отправляется в `management/v1/counter/{id}/offline_conversions/upload` с параметром `client_id_type=CLIENT_ID`.

5. **Обработка.** Метрика принимает файл, ищет сессии по ClientID и привязывает к ним офлайн-конверсии. Данные появляются в отчётах в течение 2–3 часов.

---

## ⚠️ Ограничения

| Ограничение | Значение |
|---|---|
| Окно атрибуции | 21 день от последнего визита |
| `DateTime` | только прошлое |
| Обработка | до 2–3 часов |
| Размер файла | до 1 ГБ |
| Кодировка CSV | UTF-8 |
| Обязательный ID | хотя бы один из: ClientID, UserID, Yclid |

**Важно про источник трафика.** У загруженных конверсий источник будет `Прямые заходы` — потому что реального клика по рекламе не было. Если нужна атрибуция к конкретному каналу, потребуется предварительно эмулировать клик с `yclid`.

---

## 📁 Структура проекта

```
metrica-seeder/
├── pyproject.toml
├── config.yaml
├── phones.txt
├── src/
│   └── metrica_seeder/
│       ├── __init__.py
│       ├── __main__.py
│       ├── cli.py
│       ├── config.py
│       ├── db.py
│       ├── id_generator.py
│       ├── journey_builder.py
│       ├── csv_writer.py
│       └── api_client.py
└── tests/
```

---

## 🔗 Документация Яндекс.Метрики

- [Импорт офлайн-данных](https://yandex.ru/support/metrica/ru/data/offline-params)
- [Загрузка офлайн-конверсий (API)](https://yandex.ru/dev/metrika/ru/management/offline-conv)
- [Measurement Protocol](https://yandex.ru/support/metrica/ru/general/measurement-protocol)

---

## 📄 Лицензия

MIT. См. [LICENSE](LICENSE).

---

## 🤝 Contribution

Issues и pull requests приветствуются. Если нашёл баг или хочешь добавить адаптер под другую систему аналитики — открывай issue.