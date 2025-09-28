from backend.db import get_connection
from typing import List, Optional, Tuple
import sqlite3

DB_PATH = "database/budget_tracker.db"

def add_expense(name: str, cost: float, date_str: str, category_id: Optional[int] = None, wallet_id: Optional[int] = None, description: Optional[str] = None) -> None:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            '''
            INSERT INTO expense (name, category_id, cost, date, description, wallet_id)
            VALUES (?, ?, ?, ?, ?, ?)
            ''',
            (name, category_id, cost, date_str, description, wallet_id)
        )
        conn.commit()

def edit_expense(expense_id: int, new_name: Optional[str] = None, new_category_id: Optional[int] = None, new_cost: Optional[float] = None, new_date_str: Optional[str] = None, new_description: Optional[str] = None, new_wallet_id: Optional[int] = None) -> None:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT name, category_id, cost, date, description, wallet_id FROM expense WHERE id = ?', (expense_id,))
        row = cursor.fetchone()
        if not row:
            print("Expense not found.")
            return

        current_name, current_category_id, current_cost, current_date, current_description, current_wallet_id = row

        name = new_name if new_name is not None else current_name
        category_id = new_category_id if new_category_id is not None else current_category_id
        cost = new_cost if new_cost is not None else current_cost
        date_str = new_date_str if new_date_str is not None else current_date
        description = new_description if new_description is not None else current_description
        wallet_id = new_wallet_id if new_wallet_id is not None else current_wallet_id

        cursor.execute(
            '''
            UPDATE expense
            SET name = ?, category_id = ?, cost = ?, date = ?, description = ?, wallet_id = ?
            WHERE id = ?
            ''',
            (name, category_id, cost, date_str, description, wallet_id, expense_id)
        )
        conn.commit()

def remove_expense(expense_id: int) -> None:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM expense WHERE id = ?', (expense_id,))
        conn.commit()

def get_expense_by_id(expense_id: int) -> Optional[Tuple]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM expense WHERE id = ?', (expense_id,))
        return cursor.fetchone()

def get_expenses_by_category(category_id: int) -> List[int]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM expense WHERE category_id = ?', (category_id,))
        return [row[0] for row in cursor.fetchall()]

def get_expenses_by_date_range(start_date: str, end_date: str) -> List[int]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM expense WHERE date BETWEEN ? AND ?', (start_date, end_date))
        return [row[0] for row in cursor.fetchall()]

def get_all_expenses_ordered_by_id() -> List[Tuple]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM expense ORDER BY id ASC')
        return cursor.fetchall()

def get_all_expenses() -> List[Tuple]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id, name, category_id, cost, date, description, wallet_id FROM expense')
        return cursor.fetchall()

def get_all_expenses4display() -> List[Tuple]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id, name, cost, date FROM expense')
        return cursor.fetchall()

def ordeBy(option: int = 1) -> List[Tuple]:
    '''
    Orders expenses in the database by the selected option.

    Parameters:
        option (int):
            1 - Order by ID
            2 - Order by Category Name (A-Z)
            3 - Order by Amount (High → Low)
            4 - Order by Amount (Low → High)
            5 - Order by Date (Most Recent First)

    Returns:
        List of ordered expense tuples.
    '''
    query_map = {
        1: '''
            SELECT expense.id, expense.name, category.name AS category, cost, date, description, wallet_id
            FROM expense
            LEFT JOIN category ON expense.category_id = category.id
            ORDER BY expense.id ASC
        ''',
        2: '''
            SELECT expense.id, expense.name, category.name AS category, cost, date, description, wallet_id
            FROM expense
            LEFT JOIN category ON expense.category_id = category.id
            ORDER BY category.name ASC
        ''',
        3: '''
            SELECT expense.id, expense.name, category.name AS category, cost, date, description, wallet_id
            FROM expense
            LEFT JOIN category ON expense.category_id = category.id
            ORDER BY cost DESC
        ''',
        4: '''
            SELECT expense.id, expense.name, category.name AS category, cost, date, description, wallet_id
            FROM expense
            LEFT JOIN category ON expense.category_id = category.id
            ORDER BY cost ASC
        ''',
        5: '''
            SELECT expense.id, expense.name, category.name AS category, cost, date, description, wallet_id
            FROM expense
            LEFT JOIN category ON expense.category_id = category.id
            ORDER BY date DESC
        '''
    }

    if option not in query_map:
        raise ValueError("Invalid option. Choose between 1 and 5.")

    query = query_map[option]

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query)
        expenses = cursor.fetchall()

    return expenses

