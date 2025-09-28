from helper_fx import (
    add_expense,
    edit_expense,
    remove_expense,
    get_expense_by_id,
    get_expenses_by_category,
    get_expenses_by_date_range,
    get_all_expenses_ordered_by_id,
    add_wallet,
    edit_wallet,
    remove_wallet,
    get_wallet_by_id,
    get_wallets_by_currency,
    add_category,
    edit_category,
    remove_category,
    get_category_by_id,
    add_goal,
    edit_goal,
    remove_goal,
    get_goal_by_id,
    get_goals_by_category

)
from backend.db import get_connection  # Ensures same DB path is used
from pprint import pprint

# expenses

def insert_dummy_wallet_and_category():
    """Ensures wallet_id=1 and category_id=1 exist for testing."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR IGNORE INTO wallet (id, name, amount, currency)
            VALUES (1, 'Test Wallet', 1000, 'EUR')
        """)
        cursor.execute("""
            INSERT OR IGNORE INTO category (id, name, limit_amount)
            VALUES (1, 'Groceries', 300)
        """)
        conn.commit()

def print_all_expenses():
    print("\n📋 All Expenses (Ordered by ID):")
    expenses = get_all_expenses_ordered_by_id()
    for exp in expenses:
        pprint(exp)
    print("-" * 50)

def test_add_expense():
    print("\n✅ Testing: Add Expense")
    add_expense(
        name="Groceries Test",
        cost=42.5,
        date_str="2025-07-07",
        category_id=1,
        wallet_id=1,
        description="Weekly food shopping"
    )
    print_all_expenses()

def test_edit_expense(expense_id):
    print("\n✏️ Testing: Edit Expense")
    edit_expense(
        expense_id=expense_id,
        new_name="Groceries - Edited",
        new_cost=50.0,
        new_description="Updated description"
    )
    print_all_expenses()

def test_get_expense_by_id(expense_id):
    print("\n🔍 Testing: Get Expense by ID")
    result = get_expense_by_id(expense_id)
    pprint(result)

def test_get_expenses_by_category(category_id):
    print(f"\n🔍 Testing: Get Expenses by Category ({category_id})")
    ids = get_expenses_by_category(category_id)
    print("Expense IDs:", ids)

def test_get_expenses_by_date_range(start, end):
    print(f"\n📅 Testing: Get Expenses from {start} to {end}")
    ids = get_expenses_by_date_range(start, end)
    print("Expense IDs:", ids)

def test_remove_expense(expense_id):
    print("\n❌ Testing: Remove Expense")
    remove_expense(expense_id)
    print_all_expenses()

def expenses_test():
    insert_dummy_wallet_and_category()  # Ensure valid foreign keys
    test_add_expense()
    
    latest = get_all_expenses_ordered_by_id()[-1]
    expense_id = latest[0]

    test_edit_expense(expense_id)
    test_get_expense_by_id(expense_id)
    test_get_expenses_by_category(category_id=1)
    test_get_expenses_by_date_range("2025-07-01", "2025-07-31")
    test_remove_expense(expense_id)

# wallets

def print_all_wallets():
    print("\n💼 All Wallets in DB:")
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM wallet ORDER BY id ASC")
        rows = cursor.fetchall()
        for row in rows:
            pprint(row)
    print("-" * 50)

def test_add_wallets():
    print("\n✅ Testing: Add Wallets")
    add_wallet(name="Main EUR Wallet", amount=1000.0, currency="EUR")
    add_wallet(name="Travel USD Wallet", amount=500.0, currency="USD")
    add_wallet(name="Savings EUR Wallet", amount=2000.0, currency="EUR")
    print_all_wallets()

def test_edit_wallet(wallet_id):
    print("\n✏️ Testing: Edit Wallet")
    edit_wallet(wallet_id, new_name="Edited Wallet", new_amount=1500.0)
    print_all_wallets()

def test_get_wallet_by_id(wallet_id):
    print("\n🔍 Testing: Get Wallet by ID")
    result = get_wallet_by_id(wallet_id)
    pprint(result)

def test_get_wallets_by_currency(currency):
    print(f"\n💱 Testing: Get Wallets by Currency ({currency})")
    ids = get_wallets_by_currency(currency)
    print("Wallet IDs:", ids)

def test_remove_wallet(wallet_id):
    print("\n❌ Testing: Remove Wallet")
    remove_wallet(wallet_id)
    print_all_wallets()

def wallets_test():
    test_add_wallets()
    
    # Get all wallet IDs (they were added in order)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM wallet ORDER BY id ASC")
        wallet_ids = [row[0] for row in cursor.fetchall()]
    
    if not wallet_ids:
        print("❗ No wallets found. Exiting test.")
        return

    test_edit_wallet(wallet_ids[0])
    test_get_wallet_by_id(wallet_ids[1])
    test_get_wallets_by_currency("EUR")
    test_get_wallets_by_currency("USD")
    test_remove_wallet(wallet_ids[2])

# categories

def print_all_categories():
    print("\n📂 All Categories in DB:")
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM category ORDER BY id ASC")
        rows = cursor.fetchall()
        for row in rows:
            pprint(row)
    print("-" * 50)

def test_add_category():
    print("\n✅ Testing: Add Category")
    add_category(name="Travel", limit_amount=500)
    print_all_categories()

def test_edit_category(category_id):
    print("\n✏️ Testing: Edit Category")
    edit_category(category_id, new_name="Vacation", new_limit_amount=800)
    print_all_categories()

def test_get_category_by_id(category_id):
    print("\n🔍 Testing: Get Category by ID")
    result = get_category_by_id(category_id)
    pprint(result)

def test_remove_category(category_id):
    print("\n❌ Testing: Remove Category")
    remove_category(category_id)
    print_all_categories()

def category_test():
    test_add_category()

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM category ORDER BY id DESC LIMIT 1")
        category_id = cursor.fetchone()[0]

    test_edit_category(category_id)
    test_get_category_by_id(category_id)
    test_remove_category(category_id)

# goals

def print_all_goals():
    print("\n🎯 All Goals in DB:")
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM goal ORDER BY id ASC")
        rows = cursor.fetchall()
        for row in rows:
            pprint(row)
    print("-" * 50)

def test_add_goal():
    print("\n✅ Testing: Add Goal")
    add_goal(
        name="Emergency Fund",
        amount_to_reach=1000.0,
        amount_reached=100.0,
        category_id=None,
        currency="EUR",
        completed=False,
        start_date="2025-07-01",
        end_date="2025-12-31"
    )
    print_all_goals()

def test_edit_goal(goal_id):
    print("\n✏️ Testing: Edit Goal")
    edit_goal(
        goal_id=goal_id,
        new_name="Emergency Fund Updated",
        new_amount_reached=500.0,
        new_completed=True,
        new_currency="USD"
    )
    print_all_goals()

def test_get_goal_by_id(goal_id):
    print("\n🔍 Testing: Get Goal by ID")
    result = get_goal_by_id(goal_id)
    pprint(result)

def test_get_goals_by_category(category_id):
    print(f"\n📂 Testing: Get Goals by Category ({category_id})")
    ids = get_goals_by_category(category_id)
    print("Goal IDs:", ids)

def test_remove_goal(goal_id):
    print("\n❌ Testing: Remove Goal")
    remove_goal(goal_id)
    print_all_goals()

def goal_test():
    test_add_goal()

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM goal ORDER BY id DESC LIMIT 1")
        goal_id = cursor.fetchone()[0]

    test_edit_goal(goal_id)
    test_get_goal_by_id(goal_id)
    test_get_goals_by_category(category_id=None)  # Should return empty since no category
    test_remove_goal(goal_id)

if __name__ == "__main__":
    expenses_test()
    wallets_test()
    category_test()
    goal_test()