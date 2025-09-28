from backend.db import get_connection
from typing import List, Optional, Tuple
import sqlite3

DB_PATH = "database/budget_tracker.db"

def add_wallet(name: str, amount: float = 0.0, currency: str = "EUR") -> None:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            '''
            INSERT INTO wallet (name, amount, currency)
            VALUES (?, ?, ?)
            ''',
            (name, amount, currency)
        )
        conn.commit()

def edit_wallet(wallet_id: int, new_name: Optional[str] = None, new_amount: Optional[float] = None, new_currency: Optional[str] = None) -> None:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT name, amount, currency FROM wallet WHERE id = ?', (wallet_id,))
        row = cursor.fetchone()
        if not row:
            return  # silently exit if wallet not found

        current_name, current_amount, current_currency = row

        name = new_name if new_name is not None else current_name
        amount = new_amount if new_amount is not None else current_amount
        currency = new_currency if new_currency is not None else current_currency

        cursor.execute(
            '''
            UPDATE wallet
            SET name = ?, amount = ?, currency = ?
            WHERE id = ?
            ''',
            (name, amount, currency, wallet_id)
        )
        conn.commit()

def remove_wallet(wallet_id: int) -> None:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM wallet WHERE id = ?', (wallet_id,))
        conn.commit()

def get_wallet_by_id(wallet_id: int) -> Optional[Tuple]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM wallet WHERE id = ?', (wallet_id,))
        return cursor.fetchone()

def get_wallets_by_currency(currency: str) -> List[int]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM wallet WHERE currency = ?', (currency,))
        return [row[0] for row in cursor.fetchall()]

def get_all_wallets() -> List[int]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id, name, amount, currency FROM wallet')
        return cursor.fetchall()
