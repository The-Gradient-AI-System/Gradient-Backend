# Деплой бекенду на Render.com

## 1. Репо на GitHub

У репо **The-Gradient-AI-System/Gradient-Backend** мають бути: `Dockerfile`, `requirements.txt`, `render.yaml`, код (main.py, routes, service, db тощо). Гілка для деплою — зазвичай **haw-haw** або **main**.

## 2. Render Dashboard

1. Зайди на https://dashboard.render.com і залогінься (або через GitHub).
2. **New +** → **Web Service**.
3. Підключи репо **Gradient-Backend** (якщо ще не підключений — **Connect account** для GitHub і вибери організацію/репо).
4. Налаштуй:
   - **Name:** gradient-backend (або на свій смак).
   - **Region:** Frankfurt (або Oregon).
   - **Branch:** haw-haw (або та гілка, з якої хочеш деплоїти).
   - **Runtime:** **Docker** (Render визначить Dockerfile з кореня репо).
   - **Instance type:** **Free**.

Якщо не використовуєш `render.yaml`, вручну не задавай Build Command / Start Command — для Docker вони не потрібні.

## 3. Environment Variables

У проєкті на Render: **Environment** → **Add Environment Variable**. Додай:

| Key             | Value (приклад) |
|-----------------|------------------|
| `SECRET_KEY`    | твій JWT-секрет  |
| `OPENAI_API_KEY`| sk-...           |
| `CORS_ORIGINS`  | https://твій-фронт.vercel.app |

Можна додати й інші з `.env.example` (наприклад `OPENAI_MODEL`, `SPREADSHEET_ID`), якщо потрібно.

## 4. Deploy

Натисни **Create Web Service**. Render збере Docker-образ і запустить сервіс. Після успішного деплою з’явиться URL типу:

**https://gradient-backend.onrender.com**

(або з твоїм ім’ям сервісу).

## 5. Фронт (Vercel)

У проєкті фронту на Vercel додай змінну:

- **Name:** `REACT_APP_API_URL`
- **Value:** `https://gradient-backend.onrender.com` (твій URL з Render)

Потім зроби **Redeploy** фронту.

## 6. Free tier

На безкоштовному плані сервіс “засинає” після ~15 хв без запитів; перший запит після цього може йти 30–60 с. Для розробки цього зазвичай достатньо.

## 7. Оновлення коду

Пуш у вибрану гілку (наприклад haw-haw) у GitHub автоматично запускає новий деплой на Render (якщо в налаштуваннях увімкнено **Auto-Deploy**).
