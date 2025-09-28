# reset_profile.py
import sqlite3, json

DB_PATH = r"budget_tracker.db"  # <-- change if your DB lives elsewhere
PHOTO_PATH = r"C:\Users\Alejandro\.finance_tool\photos\IMG_20210211_212545_504_1075x.jpg"

with sqlite3.connect(DB_PATH) as conn:
    cur = conn.cursor()
    cur.execute("PRAGMA foreign_keys = ON")

    # 1) Drop and recreate table
    cur.execute("DROP TABLE IF EXISTS profile;")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS profile (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            name           TEXT NOT NULL,
            photo_path     TEXT,
            monthly_budget REAL DEFAULT 0.0,
            main_wallet_id INTEGER,
            skip_months    TEXT DEFAULT '[]',
            theme          INTEGER,
            password_hash  TEXT,
            created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login     TIMESTAMP
        );
    """)

    # 2) Insert your single row
    cur.execute("""
        INSERT INTO profile (
            name, photo_path, monthly_budget,
            main_wallet_id, skip_months, theme,
            password_hash, last_login
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        "Alejandro",
        PHOTO_PATH,
        1750.0,
        1,
        json.dumps(["2025-07", "2025-08"]),
        1,          # theme id
        None,       # password_hash
        None        # last_login
    ))

    conn.commit()

    # 3) Verify
    cur.execute("PRAGMA database_list;")
    dblist = cur.fetchall()
    if dblist:
        print("[DB]", dblist[0][2] or "(memory)")

    cur.execute("SELECT * FROM profile;")
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()

print(f"[OK] Inserted {len(rows)} row(s).")
for i, r in enumerate(rows, 1):
    print(f"--- Row {i} ---")
    for k, v in zip(cols, r):
        print(f"{k}: {v}")
