# FastAPI Crypto Alerts

Этот проект представляет собой FastAPI приложение, которое включает в себя регистрацию пользователей, аутентификацию с использованием JWT токенов, а также возможность подписки на обновления курсов криптовалют и отправки сообщений в Telegram.

## Основные функции

- Регистрация пользователей
- Аутентификация с использованием JWT
- Подписка на обновления
- Отправка сообщений в Telegram (нужно инициировать диалог с ботом или дать право писать боту в группе)

## Установка и запуск

### Локальная установка

1. Установите зависимости:

    ```bash
    poetry install
    ```

2. Создайте файл `.env` и добавьте необходимые переменные окружения:

    ```bash
    db_host=localhost
    db_port=5432
    db_user=your_db_user
    db_password=your_db_password
    db_name=your_db_name
    SECRET_KEY=your_secret_key
    ALGORITHM=HS256
    ACCESS_TOKEN_EXPIRE_MINUTES=240
    TELEGRAM_TOKEN=your_telegram_token
    API_PORT=8000
    ```

3. Запустите приложение:

    ```bash
    uvicorn app.main:app --reload
    ```

### Деплой с использованием Docker Compose

1. Убедитесь, что у вас установлены Docker и Docker Compose.

2. Создайте файл `.env` в корне проекта и добавьте необходимые переменные окружения:
   - Важно: `db_host` должен быть равен `postgres`, так как это имя контейнера базы данных в Docker Compose.

    ```bash
    db_host=postgres
    db_port=5432
    db_user=your_db_user
    db_password=your_db_password
    db_name=your_db_name
    SECRET_KEY=your_secret_key
    ALGORITHM=HS256
    ACCESS_TOKEN_EXPIRE_MINUTES=240
    TELEGRAM_TOKEN=your_telegram_token
    API_PORT=8000
    ```

3. Запустите Docker Compose:

    ```bash
    docker-compose up --build
    ```

4. Приложение будет доступно по адресу `http://localhost:8000`.
