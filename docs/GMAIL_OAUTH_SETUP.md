# Налаштування Gmail/Sheets через веб-вхід (Render)

Інструкція для того, хто має доступ до Google Cloud Console та Render. Потрібно виконати кроки по порядку.

---

## Що потрібно мати

- Доступ до **Google Cloud Console** під акаунтом, в якому створювався OAuth-клієнт (Client ID / Client Secret або файл `credentials.json`).
- Доступ до **Render** (Dashboard сервісу бекенду).
- URL бекенду: `https://gradient-backend-xb7i.onrender.com` (якщо у вас інший — замініть у всіх кроках).

---

## Крок 1. Google Cloud Console — додати Redirect URI

1. Відкрийте **Google Cloud Console**: https://console.cloud.google.com/
2. Увійдіть **тим самим Google-акаунтом**, під яким створювали OAuth-клієнт (звідки брали Client ID і Client Secret).
3. У верхній панелі виберіть **проєкт**, до якого належить цей OAuth-клієнт.
4. Меню зліва: **APIs & Services** → **Credentials** (або **Уподобання** → **Облікові дані**).
5. У списку **OAuth 2.0 Client IDs** знайдіть потрібний клієнт (той, з якого взято Client ID для бекенду) і натисніть на нього (назву або іконку редагування).
6. У блоці **Authorized redirect URIs** натисніть **+ ADD URI**.
7. Введіть **точно** такий URI (без пробілів, з `https`):
   ```
   https://gradient-backend-xb7i.onrender.com/gmail/oauth2callback
   ```
   Якщо бекенд на іншому домені — замініть на свій, наприклад: `https://ВАШ-СЕРВІС.onrender.com/gmail/oauth2callback`.
8. Натисніть **SAVE** (Зберегти) внизу сторінки.

Готово: Google тепер дозволяє редірект на ваш бекенд після входу.

---

## Крок 2. Render — додати змінні середовища

1. Відкрийте **Render**: https://dashboard.render.com/
2. Виберіть ваш **веб-сервіс** (бекенд).
3. У лівому меню натисніть **Environment**.
4. Додайте три змінні (кнопка **Add Environment Variable** для кожної):

   | Key | Value |
   |-----|--------|
   | `BACKEND_URL` | `https://gradient-backend-xb7i.onrender.com` |
   | `GOOGLE_CLIENT_ID` | Ваш Client ID (закінчується на `.apps.googleusercontent.com`) |
   | `GOOGLE_CLIENT_SECRET` | Ваш Client Secret |

   **Звідки взяти Client ID і Client Secret:**
   - У тому ж Google Cloud Console: **APIs & Services** → **Credentials** → ваш **OAuth 2.0 Client ID** — там показані Client ID і Client secret.
   - Або з файлу `credentials.json`: розділ `installed` або `web` → поля `client_id` та `client_secret`.

5. Натисніть **Save Changes**. Render перезапустить сервіс (це нормально).

---

## Крок 3. Перший вхід і отримання токена

1. У браузері відкрийте посилання:
   ```
   https://gradient-backend-xb7i.onrender.com/gmail/auth
   ```
2. Відкриється сторінка Google — **увійдіть у той Gmail-акаунт**, з якого хочете читати листи та працювати з таблицею (це може бути інший акаунт, не обов’язково той самий, що в Google Cloud).
3. Натисніть **Дозволити** (Allow), якщо Google запитає доступ до Gmail і Google Sheets.
4. Після редіректу ви потрапите на сторінку бекенду з текстом на кшталт «Gmail connected». Токен вже збережено на сервері — автосинхронізація та `/gmail/leads` будуть працювати.

**Опційно (щоб токен не зникав після рестарту Render):**

- На тій же сторінці натисніть **Copy token**.
- У Render → ваш сервіс → **Environment** додайте змінну:
  - **Key:** `GMAIL_TOKEN_JSON`
  - **Value:** вставте скопійований токен (один довгий рядок JSON).
- Збережіть зміни. Після наступних рестартів бекенд підхопить токен із цієї змінної.

---

## Якщо щось пішло не так

- **«Redirect URI mismatch»** — перевірте, що в Google Console в **Authorized redirect URIs** додано **точно** той самий URL, що й у `BACKEND_URL` + `/gmail/oauth2callback` (з `https`, без слеша в кінці).
- **«Set GOOGLE_CLIENT_ID...»** — на Render не задані `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` або `BACKEND_URL`; перевірте **Environment** і після змін дочекайтесь перезапуску.
- **«Invalid or expired state»** — просто відкрийте ще раз `https://.../gmail/auth` і пройдіть вхід з початку.

---

## Короткий чеклист

- [ ] Google Cloud Console: у OAuth-клієнта додано Redirect URI `https://...onrender.com/gmail/oauth2callback`.
- [ ] Render: задані `BACKEND_URL`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`.
- [ ] Відкрито в браузері `https://.../gmail/auth`, виконано вхід у Google і натиснуто «Дозволити».
- [ ] (За бажанням) Токен скопійовано і вставлено в `GMAIL_TOKEN_JSON` на Render.

Після цього Gmail і Sheets у додатку працюють через веб-вхід без ручного створення `token.json` на сервері.
