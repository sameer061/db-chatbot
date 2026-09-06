import sqlite3
from pathlib import Path

path = Path(__file__).parent / "data" / "demo_company.db"
path.parent.mkdir(exist_ok=True)
if path.exists():
    path.unlink()
with sqlite3.connect(path) as db:
    db.executescript("""
    CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
    CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT NOT NULL, price REAL NOT NULL);
    CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL, product_id INTEGER NOT NULL, quantity INTEGER NOT NULL, order_date TEXT NOT NULL,
      FOREIGN KEY(customer_id) REFERENCES customers(id), FOREIGN KEY(product_id) REFERENCES products(id));
    INSERT INTO customers VALUES (1, 'Asha'), (2, 'Ravi'), (3, 'Mina');
    INSERT INTO products VALUES (1, 'Keyboard', 50.0), (2, 'Mouse', 20.0), (3, 'Monitor', 200.0);
    INSERT INTO orders VALUES (1, 1, 1, 2, '2025-01-10'), (2, 2, 3, 1, '2025-02-15'), (3, 1, 2, 3, '2025-03-20'), (4, 3, 3, 2, '2025-04-05');
    """)
print(path)
