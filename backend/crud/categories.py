from backend.db import get_connection
from typing import List, Optional, Tuple
import sqlite3

DB_PATH = "database/budget_tracker.db"

def add_category(name: str, limit_amount: Optional[float] = None, category_type: int = 0, currency: str = "EUR") -> None:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            '''
            INSERT INTO category (name, limit_amount, type, currency)
            VALUES (?, ?, ?, ?)
            ''',
            (name, limit_amount, category_type, currency)
        )
        conn.commit()

def edit_category(category_id: int, new_name: Optional[str] = None, new_limit_amount: Optional[float] = None, new_type: Optional[int] = None, new_currency: Optional[str] = None) -> None:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT name, limit_amount, type, currency FROM category WHERE id = ?', (category_id,))
        row = cursor.fetchone()
        if not row:
            return  # silently exit if category not found

        current_name, current_limit_amount, current_type, current_currency = row

        name = new_name if new_name is not None else current_name
        limit_amount = new_limit_amount if new_limit_amount is not None else current_limit_amount
        category_type = new_type if new_type is not None else current_type
        currency = new_currency if new_currency is not None else current_currency

        cursor.execute(
            '''
            UPDATE category
            SET name = ?, limit_amount = ?, type = ?, currency = ?
            WHERE id = ?
            ''',
            (name, limit_amount, category_type, currency, category_id)
        )
        conn.commit()

def remove_category(category_id: int) -> None:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM category WHERE id = ?', (category_id,))
        if not cursor.fetchone():
            return  # silently exit if it doesn't exist
        cursor.execute('DELETE FROM category WHERE id = ?', (category_id,))
        conn.commit()

def get_category_by_id(category_id: int) -> Optional[Tuple]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM category WHERE id = ?', (category_id,))
        return cursor.fetchone()

def get_all_categories():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id, name, limit_amount, type, currency FROM category')
        return cursor.fetchall()

def get_category_id_by_name(category_name: str) -> Optional[int]:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM category WHERE name = ?", (category_name,))
    result = cursor.fetchone()
    conn.close()
    if result:
        return result[0]
    else:
        return None

def get_all_categories_full():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id, name, limit_amount, type, currency FROM category')
        return cursor.fetchall()
    
def add_categories():
    categories_to_add = [
        ("Coffee", 25.0, 0, "EUR"),
        ("Clothes", 50.0, 0, "EUR"),
        ("Extra", 50.0, 0, "EUR"),
        ("Going out", 100.0, 0, "EUR"),
        ("Health Care", 57.0, 1, "EUR"),
        ("Home", 50.0, 0, "EUR"),
        ("Memberships", 70.0, 1, "EUR"),
        ("Personal Projects", 25.0, 0, "EUR"),
        ("Pharmacy", 25.0, 0, "EUR"),
        ("Rent", 533.3, 1, "EUR"),
        ("Restaurant", 150.0, 0, "EUR"),
        ("Shopping", 50.0, 0, "EUR"),
        ("Sport", 35.0, 0, "EUR"),
        ("Trasport", 140.0, 0, "EUR"),  
        ("Travel", 40.0, 0, "EUR"),
        ("University Payment", 261.0, 1, "EUR"),
        ("Groceries", 150.0, 0, "EUR")  
    ]

    for name, budget, is_fixed, currency in categories_to_add:
        try:
            add_category(name, budget, is_fixed, currency)
        except Exception:
            # silently ignore duplicates or errors (no prints)
            pass
