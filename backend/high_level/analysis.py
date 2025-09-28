# ─── Standard Library ────────────────────────────────────────────────────────
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from statistics import mean, median
from typing import Optional, Union, Dict, List, Tuple

# ─── Third-Party Libraries ──────────────────────────────────────────────────
import requests
import calendar

# ─── Internal Project Imports ───────────────────────────────────────────────
try:
    from util.config import CURRENCY_FREAKS_API_KEY
except Exception:
    CURRENCY_FREAKS_API_KEY = ""

from backend.crud.wallets import get_all_wallets, get_wallet_by_id
from backend.crud.expenses import add_expense, get_all_expenses 
from backend.crud.categories import get_all_categories,get_all_categories_full
from backend.db import get_connection

# ─────────────────────────────
# 💸 EXPENSE FUNCTIONS
# ─────────────────────────────

def redo_expense(expense_id: int) -> None:
    '''
    Undoes a specific expense by:
        1. Retrieving the expense with the given ID
        2. Adding the cost back to the corresponding wallet
        3. Deleting the expense entry
    '''
    with get_connection() as conn:
        cursor = conn.cursor()

        # Get the expense details
        cursor.execute(
            '''
            SELECT cost, wallet_id FROM expense WHERE id = ?
            ''',
            (expense_id,)
        )
        expense = cursor.fetchone()
        if not expense:
            return

        cost, wallet_id = expense

        # Get current wallet balance
        cursor.execute(
            '''
            SELECT amount FROM wallet WHERE id = ?
            ''',
            (wallet_id,)
        )
        wallet = cursor.fetchone()
        if not wallet:
            return

        current_balance = wallet[0]
        new_balance = current_balance + cost

        # Update wallet balance
        cursor.execute(
            '''
            UPDATE wallet SET amount = ? WHERE id = ?
            ''',
            (new_balance, wallet_id)
        )

        # Delete the expense
        cursor.execute(
            '''
            DELETE FROM expense WHERE id = ?
            ''',
            (expense_id,)
        )

        conn.commit()

def record_expense(
    name: str,
    cost: float,
    date_str: str,
    category_id: Optional[int] = None,
    wallet_id: Optional[int] = None,
    description: Optional[str] = None
) -> None:
    '''
    Records a new expense:
        1. Inserts the expense into the database
        2. Deducts the cost from the specified wallet's balance
    '''
    add_expense(
        name=name,
        cost=cost,
        date_str=date_str,
        category_id=category_id,
        wallet_id=wallet_id,
        description=description
    )

    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            '''
            SELECT amount
            FROM wallet
            WHERE id = ?
            ''',
            (wallet_id,)
        )
        wallet = cursor.fetchone()
        if not wallet:
            return

        current_balance = wallet[0]
        new_balance = current_balance - cost

        cursor.execute(
            '''
            UPDATE wallet
            SET amount = ?
            WHERE id = ?
            ''',
            (new_balance, wallet_id)
        )

        conn.commit()

def month_comparasion(reference_date: Optional[str] = None, toggle_state: int = 0, main_wallet: Optional[int] = None) -> Tuple[float, float, float]:
    

    if reference_date is None:
        today = datetime.today()
        current_month = today.strftime("%Y-%m")
    else:
        current_month = reference_date

    year, month = map(int, current_month.split("-"))
    first_day_current = datetime(year, month, 1)
    last_month = first_day_current - timedelta(days=1)
    previous_month = last_month.strftime("%Y-%m")

    expenses = get_all_expenses()
    categories = get_all_categories()
    filtered_expenses = filter_expenses_by_toggle(expenses, categories, toggle_state)

    if isinstance(main_wallet, int):
        _w = get_wallet_by_id(main_wallet)
        filtered_expenses = [e for e in filtered_expenses if len(e) > 6 and e[6] == main_wallet]

    def total_for_month(month_str: str) -> float:
        return sum(
            float(e[3])
            for e in filtered_expenses
            if isinstance(e[4], str) and e[4].startswith(month_str)
        )

    current_total = total_for_month(current_month)
    previous_total = total_for_month(previous_month)
    difference = round(current_total - previous_total, 2)

    return previous_total, current_total, difference

def weekly_expenses(n: int, toggle_state: int = 0) -> Dict[str, float]:
    '''
    Calculates the total expenses for each of the past `n` weeks,

    Parameters:
        n (int): Number of weeks to include.
        toggle_state (int): 0 = include all, 1 = exclude fixed categories.

    Returns:
        Dict[str, float]: Mapping of 'YYYY-WW' → total expenses that week.
    '''
    today = datetime.today().date()
    start_date = today - timedelta(weeks=n)

    expenses = get_all_expenses()
    categories = get_all_categories()
    filtered_expenses = filter_expenses_by_toggle(expenses, categories, toggle_state)

    weekly_totals = defaultdict(float)

    for exp in filtered_expenses:
        date_str = exp[4]       
        cost = float(exp[3])    
        expense_date = datetime.strptime(date_str, "%Y-%m-%d").date()

        if expense_date >= start_date:
            iso_year, iso_week, _ = expense_date.isocalendar()
            week_key = f"{iso_year}-W{iso_week:02d}"
            weekly_totals[week_key] += cost

    sorted_totals = dict(sorted(weekly_totals.items(), reverse=True))
    return dict(list(sorted_totals.items())[:n])

def calc_descriptive_stats_per_month(month: str, toggle_state: int = 0) -> Dict[str, object]:
    '''
    Calculates descriptive statistics (mean, median, mode) for expenses in a given month.

    Parameters:
        month (str): Format 'MM-YYYY' (e.g., '07-2025').
        toggle_state (int): 0 = include all categories, 1 = exclude fixed.

    Returns:
        dict: {
            'mean': float,
            'median': float,
            'mode': str
        }
    '''
    try:
        month_part, year_part = month.split("-")
    except ValueError:
        raise ValueError("Month format should be 'MM-YYYY'")

    expenses = get_all_expenses()
    categories = get_all_categories()
    filtered_expenses = filter_expenses_by_toggle(expenses, categories, toggle_state)

    relevant_expenses = [
        (exp[1], float(exp[3]))  
        for exp in filtered_expenses
        if exp[4].startswith(f"{year_part}-{month_part}")
    ]

    if not relevant_expenses:
        return {
            'mean': 0.0,
            'median': 0.0,
            'mode': 'No expenses in that month'
        }

    names = [e[0] for e in relevant_expenses]
    costs = [e[1] for e in relevant_expenses]

    mean_val = round(mean(costs), 2)
    median_val = round(median(costs), 2)

    name_counts = Counter(names)
    most_common = name_counts.most_common(1)
    if most_common and most_common[0][1] > 1:
        mode_val = most_common[0][0]
    else:
        mode_val = "No expense is repeated"

    return {
        'mean': mean_val,
        'median': median_val,
        'mode': mode_val
    }

# ─────────────────────────────
# 🎯 GOAL FUNCTIONS
# ─────────────────────────────

def ordeBy(option: int):
    '''
    Order goals in db by:
        1. id
        2. uncompleted only
        3. most expensive first (amount_to_reach descending)
        4. most amount reached (amount_reached descending)
        5. alphabetically by name
    '''
    with get_connection() as conn:
        cursor = conn.cursor()

        if option == 1:
            query = "SELECT * FROM goal ORDER BY id ASC"

        elif option == 2:
            query = "SELECT * FROM goal WHERE completed = 0 ORDER BY id ASC"

        elif option == 3:
            query = "SELECT * FROM goal ORDER BY amount_to_reach DESC"

        elif option == 4:
            query = "SELECT * FROM goal ORDER BY amount_reached DESC"

        elif option == 5:
            query = "SELECT * FROM goal ORDER BY name COLLATE NOCASE ASC"

        else:
            raise ValueError("Invalid option. Choose between 1 and 5.")

        cursor.execute(query)
        results = cursor.fetchall()

    return results

# backend/high_level/analysis.py

    """
    Deduct goal amount from wallet, log as an expense ('goal completed'),
    and finally REMOVE the goal from the DB (not just mark completed).
    """
    with get_connection() as conn:
        cursor = conn.cursor()

        # 1) Read goal
        cursor.execute(
            '''
            SELECT name, amount_to_reach, category_id, currency
            FROM goal
            WHERE id = ?
            ''',
            (goal_id,)
        )
        row = cursor.fetchone()
        if not row:
            print("Goal not found.")
            return

        name, amount, category_id, currency = row

        # 2) Read wallet
        cursor.execute(
            '''
            SELECT amount
            FROM wallet
            WHERE id = ?
            ''',
            (wallet_id,)
        )
        w = cursor.fetchone()
        if not w:
            print("Wallet not found.")
            return

        current_amount = float(w[0] or 0.0)
        updated_amount  = current_amount - float(amount or 0.0)

        # 3) Update wallet balance
        cursor.execute(
            '''
            UPDATE wallet
            SET amount = ?
            WHERE id = ?
            ''',
            (updated_amount, wallet_id)
        )

        # 4) Log expense
        today = get_current_time()
        cursor.execute(
            '''
            INSERT INTO expense (name, category_id, cost, date, description, wallet_id)
            VALUES (?, ?, ?, ?, ?, ?)
            ''',
            (name, category_id, amount, today, 'goal completed', wallet_id)
        )

        # 5) Remove the goal (delete the row)
        cursor.execute('DELETE FROM goal WHERE id = ?', (goal_id,))

        conn.commit()

def complete_goal(goal_id: int, wallet_id: int) -> None:
    """
    Deduct goal amount from wallet, log as an expense ('goal completed'),
    and finally REMOVE the goal from the DB (not just mark completed).
    """
    with get_connection() as conn:
        cursor = conn.cursor()

        # 1) Read goal
        cursor.execute(
            '''
            SELECT name, amount_to_reach, category_id, currency
            FROM goal
            WHERE id = ?
            ''',
            (goal_id,)
        )
        row = cursor.fetchone()
        if not row:
            print("Goal not found.")
            return

        name, amount, category_id, currency = row

        # 2) Read wallet
        cursor.execute(
            '''
            SELECT amount
            FROM wallet
            WHERE id = ?
            ''',
            (wallet_id,)
        )
        w = cursor.fetchone()
        if not w:
            print("Wallet not found.")
            return

        current_amount = float(w[0] or 0.0)
        updated_amount  = current_amount - float(amount or 0.0)

        # 3) Update wallet balance
        cursor.execute(
            '''
            UPDATE wallet
            SET amount = ?
            WHERE id = ?
            ''',
            (updated_amount, wallet_id)
        )

        # 4) Log expense
        today = get_current_time()
        cursor.execute(
            '''
            INSERT INTO expense (name, category_id, cost, date, description, wallet_id)
            VALUES (?, ?, ?, ?, ?, ?)
            ''',
            (name, category_id, amount, today, 'goal completed', wallet_id)
        )

        # 5) Remove the goal (delete the row)
        cursor.execute('DELETE FROM goal WHERE id = ?', (goal_id,))

        conn.commit()


# ─────────────────────────────
# 🧰 HELPER FUNCTIONS
# ─────────────────────────────

def format_currency(amount: float, symbol: str = '') -> str:
    try:
        return f"{symbol}{amount:,.2f}"
    except:
        return str(amount)

def format_networth_dict(networth_dict: Dict[str, float]) -> str:
    formatted_entries = [
        format_currency(amount, symbol=f"{currency} ")
        for currency, amount in networth_dict.items()
    ]
    return ", ".join(formatted_entries)

def get_current_time():
    return datetime.today().strftime('%Y-%m-%d')

def get_MM_YYYY():
    return datetime.today().strftime('%m-%Y')

def filter_expenses_by_toggle(expenses, categories, toggle_state):
    if toggle_state == 0:
        return expenses
    valid_category_ids = {cat[0] for cat in categories if cat[3] == 0}
    return [expense for expense in expenses if expense[2] in valid_category_ids]  # ✅ expense[2] = category_id

def generate_month_options(num_months_back=24):
    now = datetime.now()
    return [
        (now.year - ((now.month - i - 1) // 12), (now.month - i - 1) % 12 + 1)
        for i in range(num_months_back)
    ]

def format_month_tuple(ym_tuple):
    year, month = ym_tuple
    return f"{calendar.month_name[month]} {year}"

# ─────────────────────────────
# 💰 WALLET FUNCTIONS
# ─────────────────────────────

def order_by(mode: int = 1) -> List[Tuple]:
    '''
    Orders wallets in DB by:
        1. ID (default)
        2. Currency (alphabetical)
        3. Amount (highest to lowest)
    
    Parameters:
        mode (int): The ordering mode (1 = ID, 2 = Currency, 3 = Amount descending)

    Returns:
        List of tuples representing wallets, sorted accordingly.
    '''
    wallets = get_all_wallets()  

    if mode == 2:
        sorted_wallets = sorted(wallets, key=lambda x: x[3])  
    elif mode == 3:
        sorted_wallets = sorted(wallets, key=lambda x: x[2], reverse=True)  
    else:
        sorted_wallets = sorted(wallets, key=lambda x: x[0])  

    return sorted_wallets

def calc_networth(mode: int = 1, target_currency: str = None) -> Union[Dict[str, float], float]:
    '''
    Calculates net worth based on wallet balances.

    Parameters:
        mode (int):
            1 - Return net worth per currency (e.g. {'EUR': 200.0, 'USD': 150.0})
            2 - Return total net worth converted into a single currency using `currency_conversion`

    Returns:
        If mode == 1: dict of {currency: total_amount}
        If mode == 2: float representing total net worth in the target currency
    '''
    wallets = get_all_wallets()

    if mode == 1:
        currency_totals = {}
        for wallet in wallets:
            amount = wallet[2]
            currency = wallet[3]
            currency_totals[currency] = currency_totals.get(currency, 0) + amount
        return currency_totals


    else:
        raise ValueError("Invalid mode. Use 1 for raw by currency, 2 for converted net worth.")

def transfer_money(giver_wallet_id: int, receiver_wallet_id: int, amount: float) -> None:
    '''
    Transfers money from one wallet to another.
    If the currencies differ, performs automatic conversion using currency_conversion().
    
    Parameters:
        giver_wallet_id (int): ID of the wallet giving the money
        receiver_wallet_id (int): ID of the wallet receiving the money
        amount (float): Amount to transfer from giver
    '''
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT amount, currency FROM wallet WHERE id = ?", (giver_wallet_id,))
        giver = cursor.fetchone()
        if not giver:
            return
        giver_amount, giver_currency = giver

        if amount <= 0 or giver_amount < amount:
            return

        cursor.execute("SELECT amount, currency FROM wallet WHERE id = ?", (receiver_wallet_id,))
        receiver = cursor.fetchone()
        if not receiver:
            return
        receiver_amount, receiver_currency = receiver

        if giver_currency != receiver_currency:
            return

        new_giver_amount = round(giver_amount - amount, 2)
        new_receiver_amount = round(receiver_amount + amount, 2)

        cursor.execute("UPDATE wallet SET amount = ? WHERE id = ?", (new_giver_amount, giver_wallet_id))
        cursor.execute("UPDATE wallet SET amount = ? WHERE id = ?", (new_receiver_amount, receiver_wallet_id))
        conn.commit()

def get_avg_monthly_expense(exclude_months: list = [], only_non_fixed: bool = False) -> float:
    expenses = get_all_expenses()
    categories = get_all_categories_full()
    fixed_ids = {cat[0] for cat in categories if cat[3] == 1}

    monthly_totals = defaultdict(float)

    for exp in expenses:
        try:
            category_id = exp[2]
            amount = float(exp[3])
            date_obj = datetime.strptime(exp[4], "%Y-%m-%d")
            year_month = (date_obj.year, date_obj.month)

            if year_month in exclude_months:
                continue
            if only_non_fixed and category_id in fixed_ids:
                continue

            monthly_totals[year_month] += amount
        except Exception:
            continue

    if not monthly_totals:
        return 0.0

    avg = round(sum(monthly_totals.values()) / len(monthly_totals), 2)
    return avg

def display_selected_wallet(wallet_id: int):
    """
    Return [name, amount, currency] for the given wallet_id.
    Never returns None; falls back to a safe default when not found.
    """
    try:
        from backend.crud.wallets import get_wallet_by_id, get_all_wallets
    except Exception:
        # If imports fail for any reason, keep the app alive with a default
        return ["Wallet", 0.0, "EUR"]

    row = None
    try:
        row = get_wallet_by_id(int(wallet_id))
    except Exception:
        row = None

    # If the specific wallet isn't found, try to fall back to the first wallet
    if not row:
        try:
            all_w = get_all_wallets() or []
            if all_w:
                # expected wallet row shape: (id, name, amount, currency)
                row = all_w[0]
        except Exception:
            row = None

    if not row:
        # Final safe default
        return ["Wallet", 0.0, "EUR"]

    # Normalize and return
    try:
        name = row[1] if len(row) > 1 and row[1] is not None else "Wallet"
        amount = float(row[2]) if len(row) > 2 and row[2] is not None else 0.0
        currency = row[3] if len(row) > 3 and row[3] is not None else "EUR"
        return [name, amount, currency]
    except Exception:
        return ["Wallet", 0.0, "EUR"]


def networth_by_currency_table_qt():
    """
    Qt widget showing net worth grouped by currency (no conversion).
    Uses backend.high_level.analysis.calc_networth(mode=1).
    """
    from PySide6.QtWidgets import QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem, QSizePolicy
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QLabel, QHeaderView
    from backend.high_level.analysis import calc_networth

    # Get {currency: total_amount}
    try:
        totals = calc_networth(mode=1) or {}
    except Exception as e:
        # Graceful fallback
        wrap = QWidget()
        wrap.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        lay = QVBoxLayout(wrap); lay.setContentsMargins(0, 0, 0, 0)
        msg = QLabel(f"Failed to load net worth: {e}")
        msg.setAlignment(Qt.AlignCenter); msg.setStyleSheet("color:#a00;")
        lay.addWidget(msg, 1)
        return wrap

    container = QWidget()
    container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)

    if not totals:
        msg = QLabel("No wallets found.")
        msg.setAlignment(Qt.AlignCenter)
        msg.setStyleSheet("color:#666; font-size:12px;")
        layout.addWidget(msg, 1)
        return container

    # Sort biggest first
    items = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)

    table = QTableWidget(len(items), 2, container)
    table.setHorizontalHeaderLabels(["Amount", "Currency"])
    table.setEditTriggers(QTableWidget.NoEditTriggers)
    table.setSelectionBehavior(QTableWidget.SelectRows)
    table.setAlternatingRowColors(True)
    table.verticalHeader().setVisible(False)

    for r, (cur, amt) in enumerate(items):
        amt_item = QTableWidgetItem(f"{amt:.2f}")
        amt_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        table.setItem(r, 0, amt_item)
        table.setItem(r, 1, QTableWidgetItem(cur))

    hdr = table.horizontalHeader()
    hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # Amount
    hdr.setSectionResizeMode(1, QHeaderView.Stretch)           # Currency

    layout.addWidget(table, 1)
    return container


