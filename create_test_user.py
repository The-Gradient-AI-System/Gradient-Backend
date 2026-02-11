from db import conn
from hashPswd import hash_password

# Спочатку перевіримо структуру таблиці
try:
    columns = conn.execute("DESCRIBE users").fetchall()
    print("Структура таблиці users:")
    for col in columns:
        print(f"  {col}")
except:
    print("Перевіряємо наявність таблиці...")
    tables = conn.execute("SHOW TABLES").fetchall()
    print("Існуючі таблиці:", tables)

# Створюємо тестового користувача
username = 'admin'
email = 'admin@example.com'
password = 'admin123'
hashed_password = hash_password(password)

# Перевіряємо чи існує
try:
    exists = conn.execute('SELECT 1 FROM users WHERE username = ? OR email = ?', [username, email]).fetchone()

    if not exists:
        next_id = conn.execute('SELECT COALESCE(MAX(id), 0) + 1 FROM users').fetchone()[0]
        conn.execute('INSERT INTO users (id, username, email, password) VALUES (?, ?, ?, ?)', 
                    [next_id, username, email, hashed_password])
        conn.commit()
        print('✅ Створено користувача:')
        print(f'   Логін: {username}')
        print(f'   Email: {email}')
        print(f'   Пароль: {password}')
    else:
        print('ℹ️  Користувач вже існує. Поточні облікові записи:')
        users = conn.execute('SELECT username, email FROM users').fetchall()
        for existing_username, existing_email in users:
            print(f'   - {existing_username} ({existing_email})')
except Exception as e:
    print(f"Помилка: {e}")
    print("Спробуємо створити таблицю...")
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username VARCHAR UNIQUE,
            email VARCHAR UNIQUE,
            password VARCHAR,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    print("Таблицю users створено! Запустіть скрипт ще раз для створення користувача.")
