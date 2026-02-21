# Деплой бекенду на Fly.io

## Передумови

- [Fly CLI](https://fly.io/docs/hands-on/install-flyctl/) встановлений
- Акаунт на [fly.io](https://fly.io)
- Репо бекенду (окремо або в монорепо)

## 1. Логін і створення volume (опційно)

```bash
fly auth login
```

Якщо потрібна збереження DuckDB між деплоями — створіть volume (один раз):

```bash
fly volumes create gradient_db --region ord --size 1
```

Регіон можна змінити (`iad`, `lax`, `ams` тощо). Якщо volume не створювати — прибрати секцію `[mounts]` з `fly.toml`.

## 2. Деплой з Dockerfile

У корені бекенду (де лежать `Dockerfile` і `fly.toml`):

```bash
cd Gradient-Backend
fly launch --no-deploy
```

Якщо питають "Copy configuration from an existing app?" — виберіть **No**. Потім:

```bash
fly deploy
```

## 3. Секрети (обовʼязково)

Встановіть змінні середовища через Fly secrets (не потраплять у образ):

```bash
fly secrets set SECRET_KEY="ваш-секретний-ключ"
fly secrets set OPENAI_API_KEY="sk-..."
fly secrets set CORS_ORIGINS="https://ваш-фронт.vercel.app,https://ваш-домен.vercel.app"
```

Додатково за потреби: `ALGORITHM`, `ACCESS_TOKEN_EXPIRE_HOURS`, `OPENAI_MODEL`, `COMPANY_SEARCH_ENABLED` тощо.

## 4. Google OAuth (Gmail/Sheets)

Бекенд очікує `credentials/credentials.json` і `credentials/token.json`. На Fly їх можна:

- Змонтувати через [Fly Volumes](https://fly.io/docs/reference/configuration/#mounts) у інший шлях і змінити код на читання з нього, або
- Зберегти вміст у секретах і при старті контейнера записувати у `credentials/` (скрипт у Dockerfile/entrypoint).

Найпростіше для початку: локально згенерувати `token.json` (через `auth_init.py`), потім завантажити файли на сервер (наприклад, через `fly ssh sftp` або тимчасовий volume).

## 5. Перевірка

```bash
fly open
fly logs
```

API: `https://gradient-backend.fly.dev` (або ваше ім’я з `fly.toml`).

## 6. Фронт

У Vercel для проєкту фронту додайте змінну:

- `REACT_APP_API_URL=https://gradient-backend.fly.dev`

Потім перезберіть/задеплойте фронт.
