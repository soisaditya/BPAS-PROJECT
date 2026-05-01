import sqlite3
import os

DB_NAME = "bpas.db"

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Drop ONLY analytics tables — never drop users
    cursor.executescript('''
        DROP TABLE IF EXISTS orders;
        DROP TABLE IF EXISTS transactions;
        DROP TABLE IF EXISTS products;
        DROP TABLE IF EXISTS geographics;
        DROP TABLE IF EXISTS reviews;
    ''')

    # Create users table only if it doesn't exist yet (preserve accounts)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Create analytics tables fresh
    cursor.executescript('''
        CREATE TABLE orders (
            order_id TEXT PRIMARY KEY,
            customer_id TEXT,
            status TEXT,
            purchase_timestamp DATETIME,
            delivered_date DATETIME,
            estimated_date DATETIME
        );

        CREATE TABLE transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT,
            payment_type TEXT,
            payment_value REAL
        );

        CREATE TABLE products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT,
            product_id TEXT,
            category TEXT,
            price REAL
        );

        CREATE TABLE geographics (
            customer_id TEXT PRIMARY KEY,
            state TEXT,
            city TEXT
        );
        
        CREATE TABLE reviews (
            order_id TEXT,
            review_score INTEGER
        );
    ''')

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Database initialized.")
