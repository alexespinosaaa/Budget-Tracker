from backend.db import get_connection
from typing import List, Optional, Tuple
import sqlite3

DB_PATH = "database/budget_tracker.db"

def add_goal(name: str, amount_to_reach: float, amount_reached: float = 0.0, category_id: Optional[int] = None, currency: str = "EUR", start_date: Optional[str] = None) -> None:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            '''
            INSERT INTO goal (name, amount_to_reach, amount_reached, category_id, currency, start_date)
            VALUES (?, ?, ?, ?, ?, ?)
            ''',
            (name, amount_to_reach, amount_reached, category_id, currency, start_date)
        )
        conn.commit()

def edit_goal(
    goal_id: int,
    new_name: Optional[str] = None,
    new_amount_to_reach: Optional[float] = None,
    new_amount_reached: Optional[float] = None,
    new_category_id: Optional[int] = None,
    new_currency: Optional[str] = None
) -> None:
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            '''
            SELECT name, amount_to_reach, amount_reached, category_id, currency
            FROM goal
            WHERE id = ?
            ''',
            (goal_id,)
        )
        row = cursor.fetchone()
        if not row:
            return

        current_name, current_to_reach, current_reached, current_cat, current_curr = row

        name            = new_name if new_name is not None else current_name
        amount_to_reach = new_amount_to_reach if new_amount_to_reach is not None else current_to_reach
        amount_reached  = new_amount_reached  if new_amount_reached  is not None else current_reached
        category_id     = new_category_id     if new_category_id     is not None else current_cat
        currency        = new_currency        if new_currency        is not None else current_curr

        cursor.execute(
            '''
            UPDATE goal
            SET name = ?, amount_to_reach = ?, amount_reached = ?, category_id = ?, currency = ?
            WHERE id = ?
            ''',
            (name, amount_to_reach, amount_reached, category_id, currency, goal_id)
        )

        conn.commit()

def remove_goal(goal_id: int) -> None:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM goal WHERE id = ?', (goal_id,))
        conn.commit()

def get_goal_by_id(goal_id: int) -> Optional[Tuple]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM goal WHERE id = ?', (goal_id,))
        return cursor.fetchone()

def get_goals_by_category(category_id: int) -> List[int]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM goal WHERE category_id = ?', (category_id,))
        return [row[0] for row in cursor.fetchall()]

def get_all_goals() -> List[int]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id, name, amount_to_reach, amount_reached, category_id, currency, completed, start_date, end_date FROM goal')
        return cursor.fetchall()

def get_goals_4table() -> List[int]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT name, amount_to_reach, amount_reached, currency, start_date FROM goal')
        return cursor.fetchall()
