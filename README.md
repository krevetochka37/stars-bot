## Stars Payment Bot (Telegram Stars)

Сервис для приёма платежей через **Telegram Stars** с поддержкой **нескольких ботов** (multi-token) и обработкой через **webhook**.

### Возможности

- **Меню оплаты** в боте: выбор суммы пополнения и создание invoice.
- **Безопасная обработка** оплаты: проверка `pre_checkout_query` и `successful_payment`.
- **Антидублирование**: если платеж уже `completed`, повторно не начисляем.
- **Multi-bot режим**: каждый токен из `stars_bot_tokens` работает на своём webhook пути `/stars/{token_id}`.
- **Admin endpoint** для ручной обработки платежа (защищён admin token).

---

## Как это работает (коротко)

1. Пользователь нажимает кнопку суммы → создаётся запись в `payments` со статусом `pending` и `external_payment_id = stars_{id}`.
2. Создаётся Telegram invoice link через Stars API, ссылка отдаётся пользователю.
3. После оплаты Telegram присылает webhook (`successful_payment`) → начисляем кредиты и ставим `completed`.

---

## Требования

- Python **3.10+**
- PostgreSQL (или доступ к БД, которую использует `asyncpg`)
- Публичный HTTPS URL для webhook (для production)

---

## Установка

### Вариант A: `uv` (рекомендуется)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync
source .venv/bin/activate
```

### Вариант B: `pip`

```bash
pip install -e .
cp .env.example .env
```

---

## Настройка окружения (.env)

Минимально необходимое:

- **DB_HOST**, **DB_PORT**, **DB_NAME**, **DB_USER**, **DB_PASSWORD**
- **STARS_WEBHOOK_URL** — базовый URL (без завершающего `/`), например `https://example.com`
- **ADMIN_TOKEN** — секрет для защищённых admin эндпоинтов

Опционально:

- **PROXY_USER**, **PROXY_PASS**, **PROXY_HOST**, **PROXY_PORT** — прокси для исходящих запросов
- **ENVIRONMENT** — `DEV`/`PROD`
- **MAIN_APP_URL** — URL основного приложения (если используются внешние уведомления)

Генерация ADMIN_TOKEN:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

## Запуск

### Webhook режим (production / staging)

```bash
uvicorn app:app --host 0.0.0.0 --port 8003
```

или через uv:

```bash
uv run uvicorn app:app --host 0.0.0.0 --port 8003
```

### Dev режим (с автоперезагрузкой)

```bash
uvicorn app:app --host 0.0.0.0 --port 8003 --reload
```

---

## База данных

Ожидается минимум:

- Таблица **`stars_bot_tokens`** с колонками (примерно):
  - `id` (int, PK)
  - `token` (text)
  - `bot_username` (text, nullable)
  - `is_active` (bool)
- Таблица **`payments`**:
  - `id` (int, PK)
  - `user_id` (bigint)
  - `amount` (int)
  - `status` (`pending`/`completed`)
  - `payment_provider` (например `stars`)
  - `external_payment_id` (например `stars_123`)
  - `bot_id` (используется для сохранения `stars_token_{token_id}`)

Важно: перед запуском убедитесь, что в `stars_bot_tokens` есть хотя бы один активный токен (`is_active = TRUE`).

---

## API

### Webhook

- `POST /stars/{token_id}` — входящий webhook от Telegram для конкретного бота.

### Служебные endpoints

- `GET /` — информация о сервисе
- `GET /health` — health check
- `POST /setup-webhooks` — переустановка webhook’ов для всех активных токенов

### Admin endpoint (защищён)

- `POST /process-payment/{external_payment_id}` — ручная обработка платежа

Требует admin token:
- Заголовок: `X-Admin-Token: <token>` (рекомендуется)
- или query параметр: `?admin_token=<token>` (менее безопасно — попадёт в логи/историю)

Примеры:

```bash
curl -X POST "http://localhost:8003/process-payment/stars_123" \
  -H "X-Admin-Token: YOUR_ADMIN_TOKEN"

curl -X POST "http://localhost:8003/process-payment/stars_123?admin_token=YOUR_ADMIN_TOKEN"
```

---

## Безопасность

- **Никогда не коммитьте `.env`** и реальные токены ботов.
- Для `/process-payment/...` используйте **сложный** `ADMIN_TOKEN` и храните его как secret.
- В обработке оплаты делается проверка:
  - платеж существует
  - провайдер совпадает
  - пользователь из `successful_payment` совпадает с пользователем в `payments`
  - если статус уже `completed` — повторно не начисляем

---

## Troubleshooting

### 502 / Bad Gateway от `/stars/{token_id}`

Обычно это означает исключение при обработке update.
Проверьте логи приложения и убедитесь, что сервис отвечает Telegram **200 OK**.

### Кнопки не работают

- Убедитесь, что webhook реально установлен на URL вида:
  - `{STARS_WEBHOOK_URL}/stars/{token_id}`
- Убедитесь, что сервер доступен по HTTPS из интернета.

---

## Структура проекта

```
stars-payment-bot/
├── app.py
├── stars_bot/
│   ├── handlers.py
│   ├── services.py
│   ├── transport.py
│   ├── database/operations.py
│   ├── config/settings.py
│   ├── ui/translations.py
│   └── ...
└── pyproject.toml
```

