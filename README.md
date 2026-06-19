# broadapps_test_task

Тестовое задание: сервис генерации изображений и видео через Fal.ai API.

## Оглавление

- [Что реализовано](#что-реализовано)
- [Сервисы в Docker Compose](#сервисы-в-docker-compose)
- [Как работает генерация](#как-работает-генерация)
- [Тестовый режим без оплаты Fal.ai](#тестовый-режим-без-оплаты-falai)
- [Переменные окружения](#переменные-окружения)
- [Запуск через Docker](#запуск-через-docker)
- [Как смотреть работу сервиса](#как-смотреть-работу-сервиса)
- [Проверка через curl](#проверка-через-curl)
- [Локальный запуск без Docker](#локальный-запуск-без-docker)

## Что реализовано

- REST API на FastAPI.
- PostgreSQL и асинхронная работа с базой через SQLAlchemy.
- Миграции через Alembic.
- Очереди через RabbitMQ.
- Фоновые обработчики через Celery Workers.
- Flower для мониторинга Celery.
- Пользователи, ключи доступа и баланс в условных токенах.
- Пополнение баланса через платежный вебхук.
- Резерв токенов при создании генерации.
- Списание токенов только после успешной генерации.
- Снятие резерва токенов при ошибке.
- Статусы задач: `created`, `queued`, `processing`, `completed`, `failed`.
- Ограничение запросов: 10 запросов в минуту, затем блокировка на 60 секунд.
- Вебхук клиенту после завершения генерации: 5 попыток с интервалом 15 секунд.
- Метрики Prometheus на `/metrics`.
- Логи HTTP-запросов с ротацией 7 дней.
- Переключение на запасного поставщика при ошибках основного.
- В качестве пакетного менеджера используется uv, в качестве линтера ruff

## Сервисы в Docker Compose

- `api` - HTTP API. Применяет миграции и запускает FastAPI.
- `generation_worker` - берет задачи генерации из очереди, вызывает поставщика, обновляет задачу и баланс.
- `webhook_worker` - доставляет клиентские вебхуки о результате генерации.
- `db` - PostgreSQL, основное хранилище пользователей, балансов, задач и результатов.
- `rabbitmq` - очередь задач для фоновых обработчиков.
- `flower` - веб-интерфейс для просмотра Celery-задач и очередей.

PostgreSQL является источником истины. RabbitMQ используется только как транспорт задач.

## Как работает генерация

1. Клиент регистрируется через `POST /auth/register` и получает `api_key`.
2. Платежный сервис вызывает `POST /webhooks/payments`, баланс пользователя пополняется (это просто делается вручную).
3. Клиент создает задачу генерации.
4. API резервирует токены, сохраняет задачу в БД и кладет `generation_id` в RabbitMQ.
5. `generation_worker` переводит задачу в `processing`, вызывает поставщика и сохраняет результат.
6. При успехе токены списываются. При ошибке резерв возвращается.
7. `webhook_worker` отправляет результат на `callback_url` клиента.

## Тестовый режим без оплаты Fal.ai

В репозитории оставлен готовый `.env` добавлен специально, чтобы не мучиться, поэтому проект можно запускать сразу.

Используются модели Wan 2.5:

- `fal-ai/wan-25-preview/text-to-image`
- `fal-ai/wan-25-preview/image-to-image`
- `fal-ai/wan-25-preview/text-to-video`
- `fal-ai/wan-25-preview/image-to-video`

Для нашего API входное поле изображения называется `source_image_url`. При вызове Fal.ai оно преобразуется так:

- `image-to-image`: `source_image_url` -> `image_urls: [source_image_url]`
- `image-to-video`: `source_image_url` -> `image_url`

Ответ Fal.ai сохраняется целиком в `result_payload`. В `result_url` отдельно кладется первый `images[0].url` для изображений или `video.url` для видео.

**ВАЖНО** - по умолчанию платные модели не вызываются, это сделано специально, дабы не регистрироваться и не тратить деньги.
При этом весь код production вида и соответствует документации моделей и fal.ai.

```env
APP_TEST_FAL=true
APP_PROVIDER_ORDER=fal,mock
APP_FAL_API_KEY=
```

При `APP_TEST_FAL=true` используется тот же класс `FalGenerationProvider`, но вместо обращения к платной модели он возвращает тестовый результат. Так проверяются API, баланс, очереди и вебхуки без оплаты.

Для реального Fal.ai поменяйте `.env`:

```env
APP_TEST_FAL=false - убрать тестовый режим, дабы не применялись "заглушки"
APP_FAL_API_KEY=<real_fal_api_key> - нужно добавить ключ
```

Клиентские вебхуки тоже заглушены по умолчанию:

```env
APP_TEST_CALLBACK_DELIVERY=true
APP_TEST_CALLBACK_FAILURES_BEFORE_SUCCESS=0
```

В таком режиме сервис не делает внешний HTTP-запрос на `callback_url`, а сразу считает доставку успешной. В автотестах значение `APP_TEST_CALLBACK_FAILURES_BEFORE_SUCCESS` переопределяется на `4`, чтобы проверить повторные попытки доставки.

## Переменные окружения

Файл `.env` уже лежит в проекте:

```env
APP_ENVIRONMENT=local
APP_DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/broadapps
APP_CREATE_SCHEMA_ON_STARTUP=false
APP_PAYMENT_WEBHOOK_SECRET=payment-secret
APP_INTERNAL_HEALTHCHECK_SECRET=healthcheck-secret
APP_METRICS_SECRET=metrics-secret
APP_TEST_CALLBACK_DELIVERY=true
APP_TEST_CALLBACK_FAILURES_BEFORE_SUCCESS=0
APP_CELERY_BROKER_URL=amqp://guest:guest@rabbitmq:5672//
APP_CELERY_GENERATION_QUEUE=generation
APP_CELERY_WEBHOOKS_QUEUE=webhooks
APP_CELERY_GENERATION_CONCURRENCY=2
APP_CELERY_WEBHOOK_CONCURRENCY=4
APP_CELERY_FLOWER_PORT=5555
APP_TEST_FAL=true
APP_FAL_API_KEY=
APP_PROVIDER_ORDER=fal,mock
APP_PROVIDER_FAILURE_THRESHOLD=3
APP_PROVIDER_COOLDOWN_SECONDS=60
```

## Запуск через Docker

```bash
docker compose up --build
```

Если ранее уже поднималась старая база:

```bash
docker compose down -v
docker compose up --build
```

При старте `api` выполняет:

```bash
uv run alembic upgrade head
```

Адреса:

- API: `http://localhost:8000`
- Документация API: `http://localhost:8000/docs`
- Метрики: `http://localhost:8000/metrics`
- Flower: `http://localhost:5555`
- RabbitMQ: `http://localhost:15672`

## Как смотреть работу сервиса

### Контейнеры

```bash
docker compose ps
```

Проверить, что API здоров с точки зрения Docker:

```bash
docker inspect --format='{{json .State.Health}}' broadapps_test_task-api-1
```

Внешний `GET /health` закрыт для обычных пользователей. Docker использует внутренний заголовок `X-Internal-Healthcheck`, значение берется из `APP_INTERNAL_HEALTHCHECK_SECRET`.

Это сделано простым секретом ради тестового задания, чтобы не вводить отдельную админскую модель пользователей.

### Логи

API:

```bash
docker compose logs -f api
```

Обработчик генераций:

```bash
docker compose logs -f generation_worker
```

Обработчик клиентских вебхуков:

```bash
docker compose logs -f webhook_worker
```

Файл с HTTP-логами внутри проекта:

```bash
tail -f logs/service.log
```

### Очереди и фоновые задачи

Flower:

```text
http://localhost:5555
```

Там видно задачи Celery, их статусы, время выполнения и ошибки.

RabbitMQ:

```text
http://localhost:15672
```

Логин и пароль по умолчанию:

```text
guest / guest
```

Очереди:

- `generation` - задачи генерации;
- `webhooks` - задачи доставки клиентских вебхуков.

### Метрики

Метрики закрыты отдельным системным секретом. Обычный пользовательский `X-API-Key` для `/metrics` не подходит.

```bash
curl -s http://localhost:8000/metrics \
  -H "X-Metrics-Secret: metrics-secret"
```

Это тоже упрощение для тестового задания: вместо админской роли используется отдельный секрет из `APP_METRICS_SECRET`.

Что искать в ответе:

- `api_requests_total` - количество HTTP-запросов;
- `generation_total` - задачи генерации по статусам;
- `generation_success_total` - успешные генерации;
- `generation_error_total` - ошибки генерации;
- `generation_tokens_spent_total` - списанные условные токены;
- `webhook_delivery_total` - попытки доставки клиентских вебхуков.

### Баланс и списание токенов

До завершения генерации токены находятся в резерве:

```bash
curl -s http://localhost:8000/users/me/balance \
  -H "X-API-Key: вставьте-api-key-из-регистрации"
```

После успешной генерации резерв уменьшается, а `balance_tokens` списывается на стоимость задачи.

Если генерация завершилась ошибкой, резерв снимается, но `balance_tokens` не уменьшается.

### Клиентский вебхук

При регистрации пользователь передает:

```json
{
  "callback_url": "https://client.example/webhook"
}
```

После завершения задачи сервис создает запись доставки и кладет ее в очередь `webhooks`.

По умолчанию внешний HTTP-запрос не выполняется:

```env
APP_TEST_CALLBACK_DELIVERY=true
```

Так можно проверять логику без отдельного клиентского сервиса. Повторные попытки доставки покрыты автотестом: в тестах первые 4 попытки возвращают ошибку, 5-я успешна.

### Платежный вебхук

Это имитация внешней платежной системы. Он открыт без `X-API-Key`, но защищен отдельным секретом:

```bash
curl -s -X POST http://localhost:8000/webhooks/payments \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Secret: payment-secret" \
  -d '{"external_user_id":"fd6ede7b-af96-4d52-8964-d4a4101297e2","amount":100}'
```

Без правильного `X-Webhook-Secret` запрос вернет `401`.

### Переключение поставщика

Состояние поставщиков хранится в таблице `provider_health`.

Посмотреть его можно так:

```bash
docker compose exec db psql -U postgres -d broadapps \
  -c "select * from provider_health;"
```

Если основной поставщик несколько раз подряд возвращает ошибку, он временно блокируется, а следующая задача пробует следующего поставщика из `APP_PROVIDER_ORDER`.

## Проверка через curl

После регистрации возьмите `api_key` из ответа и подставьте его в заголовок `X-API-Key`. После создания генерации возьмите `id` из ответа и подставьте его в URL получения результата.

### 1. Зарегистрировать пользователя

```bash
curl -s -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"external_user_id":"fd6ede7b-af96-4d52-8964-d4a4101297e2","callback_url":"https://client.example/webhook"}'
```

### 2. Проверить системные маршруты

```bash
curl -s http://localhost:8000/health \
  -H "X-Internal-Healthcheck: healthcheck-secret"
```

```bash
curl -s http://localhost:8000/metrics \
  -H "X-Metrics-Secret: metrics-secret"
```

Без этих системных секретов маршруты вернут `401`. Обычный `X-API-Key` пользователя для них не подходит.

### 3. Пополнить баланс через платежный вебхук

```bash
curl -s -X POST http://localhost:8000/webhooks/payments \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Secret: payment-secret" \
  -d '{"external_user_id":"fd6ede7b-af96-4d52-8964-d4a4101297e2","amount":100}'
```

### 4. Посмотреть пользователя и баланс

```bash
curl -s http://localhost:8000/users/me \
  -H "X-API-Key: вставьте-api-key-из-регистрации"
```

```bash
curl -s http://localhost:8000/users/me/balance \
  -H "X-API-Key: вставьте-api-key-из-регистрации"
```

### 5. Создать изображение по тексту

```bash
curl -s -X POST http://localhost:8000/generations/images/text-to-image \
  -H "Content-Type: application/json" \
  -H "X-API-Key: вставьте-api-key-из-регистрации" \
  -d '{"prompt":"Cinematic lighthouse in the fog"}'
```

### 6. Получить статус и результат генерации

```bash
curl -s http://localhost:8000/generations/вставьте-id-генерации \
  -H "X-API-Key: вставьте-api-key-из-регистрации"
```

Повторите команду через несколько секунд. Ожидаемый финальный статус: `completed`.

### 7. Создать изображение из изображения и текста

```bash
curl -s -X POST http://localhost:8000/generations/images/image-to-image \
  -H "Content-Type: application/json" \
  -H "X-API-Key: вставьте-api-key-из-регистрации" \
  -d '{"prompt":"Make it cinematic","source_image_url":"https://example.com/source.png"}'
```

### 8. Создать видео по тексту

```bash
curl -s -X POST http://localhost:8000/generations/videos/text-to-video \
  -H "Content-Type: application/json" \
  -H "X-API-Key: вставьте-api-key-из-регистрации" \
  -d '{"prompt":"A slow dolly shot through fog"}'
```

### 9. Создать видео из изображения и текста

```bash
curl -s -X POST http://localhost:8000/generations/videos/image-to-video \
  -H "Content-Type: application/json" \
  -H "X-API-Key: вставьте-api-key-из-регистрации" \
  -d '{"prompt":"Slow cinematic zoom","source_image_url":"https://example.com/source.png"}'
```

### 10. Получить список задач

```bash
curl -s "http://localhost:8000/generations?limit=10" \
  -H "X-API-Key: вставьте-api-key-из-регистрации"
```

Важно: защищенные маршруты ограничены 10 запросами в минуту на пользователя.

## Локальный запуск без Docker

Для запуска без Docker нужно иметь локально:

- Python 3.13.
- `uv`.
- PostgreSQL.
- RabbitMQ.

Перед запуском настройте `.env` под локальные адреса PostgreSQL и RabbitMQ. Если PostgreSQL запущен на стандартном порту, а RabbitMQ тоже локальный, значения будут такими:

```env
APP_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/broadapps
APP_CELERY_BROKER_URL=amqp://guest:guest@localhost:5672//
```

Установить зависимости:

```bash
uv sync --group dev
```

Применить миграции:

```bash
uv run alembic upgrade head
```

Запустить FastAPI:

```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Запустить worker генераций:

```bash
uv run celery -A app.infrastructure.tasks.celery_app:celery_app worker \
  -n generation-worker@%h \
  --queues generation \
  --loglevel INFO \
  --concurrency 2
```

Запустить worker клиентских вебхуков:

```bash
uv run celery -A app.infrastructure.tasks.celery_app:celery_app worker \
  -n webhook-worker@%h \
  --queues webhooks \
  --loglevel INFO \
  --concurrency 4
```

Запустить Flower:

```bash
uv run celery -A app.infrastructure.tasks.celery_app:celery_app flower --port=5555
```

Команды нужно запускать в отдельных терминалах: API, worker генераций, worker вебхуков и Flower работают как отдельные процессы.

Линтер:

```bash
uv run ruff check .
```

Автотесты:

```bash
uv run pytest
```

Создать новую миграцию после изменения моделей:

```bash
uv run alembic revision --autogenerate -m "describe change"
```
