import sqlite3

conn = sqlite3.connect(r'C:\Users\whati\OneDrive\Рабочий стол\Jup\Diplomus\Review_gen_v8.1\reviews.db')
cursor = conn.cursor()

# Создаем таблицу users, если она еще не создана
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id_user INTEGER PRIMARY KEY,
    user_name TEXT
)
""")

# Создаем таблицу products, если она еще не создана
cursor.execute("""
CREATE TABLE IF NOT EXISTS products (
    id_product INTEGER PRIMARY KEY,
    product_name TEXT
)
""")

# Создаем таблицу generation, если она еще не создана
cursor.execute("""
CREATE TABLE IF NOT EXISTS generation (
    id_gen INTEGER PRIMARY KEY AUTOINCREMENT,
    id_user INTEGER,
    id_product INTEGER,
    model TEXT,
    rating_pref TEXT,
    num_reviews INTEGER,
    gen_time TIMESTAMP DEFAULT (datetime('now', 'localtime')), 
    FOREIGN KEY (id_user) REFERENCES users(id_user),
    FOREIGN KEY (id_product) REFERENCES products(id_product)
)
""")

# Создаем таблицу reviews, если она еще не создана
cursor.execute("""
CREATE TABLE reviews (
    id_gen INTEGER,
    num_review INTEGER,
    review TEXT,
    rating INTEGER,
    current_situation TEXT,
    sex TEXT,
    profession TEXT,
    marital_status TEXT,
    children TEXT,
    hobby TEXT,
    receipt_time TIMESTAMP DEFAULT (datetime('now', 'localtime')),
    PRIMARY KEY (id_gen, num_review),
    FOREIGN KEY (id_gen) REFERENCES generation(id_gen)
)
""")

conn.commit()
conn.close()