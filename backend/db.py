# backend/db.py
import sys
import os
import sqlite3
from pathlib import Path
from contextlib import closing

# ---------- Paths ----------
def _app_root() -> Path:
    """
    App root:
    - Dev: repo root (parent of 'backend')
    - Frozen: folder containing the EXE (dist/BudgetTracker)
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]

def _db_path_default() -> Path:
    return _app_root() / "budget_tracker.db"

def _schema_candidates() -> list[Path]:
    root = _app_root()
    return [
        root / "backend" / "schema.sql",            # dev run
        root / "_internal" / "backend" / "schema.sql",  # PyInstaller onedir
    ]

def _load_schema_text() -> str:
    for p in _schema_candidates():
        if p.exists():
            return p.read_text(encoding="utf-8")
    raise FileNotFoundError("Could not locate backend/schema.sql (checked backend/schema.sql and _internal/backend/schema.sql)")

# ---------- DB ----------
def get_connection(db_path: str | None = None):
    path = Path(db_path) if db_path else _db_path_default()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def _has_core_tables(conn: sqlite3.Connection) -> bool:
    cur = conn.cursor()
    try:
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='expense'")
        ok1 = cur.fetchone() is not None
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='wallet'")
        ok2 = cur.fetchone() is not None
        return bool(ok1 and ok2)
    except Exception:
        return False

def initialize_database(db_path: str | None = None):
    """
    Idempotent: runs schema only when tables are missing.
    """
    with closing(get_connection(db_path)) as conn:
        if not _has_core_tables(conn):
            schema = _load_schema_text()
            conn.executescript(schema)  # your schema uses IF NOT EXISTS
            try:
                migrate_profile_schema(conn)  # keep your migrations
            except Exception:
                pass
            conn.commit()

def migrate_profile_schema(conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(profile)")
    existing_cols = {row[1] for row in cur.fetchall()}

    def add(sql: str): cur.execute(sql)

    # --- User ---
    if "photo_path" not in existing_cols:
        add("ALTER TABLE profile ADD COLUMN photo_path TEXT")
    if "monthly_budget" not in existing_cols:
        add("ALTER TABLE profile ADD COLUMN monthly_budget REAL DEFAULT 0.0")

    # --- Preferences ---
    if "main_wallet_id" not in existing_cols:
        add("ALTER TABLE profile ADD COLUMN main_wallet_id INTEGER")
    if "skip_months" not in existing_cols:
        add("ALTER TABLE profile ADD COLUMN skip_months TEXT DEFAULT '[]'")

    # --- Security ---
    if "password_hash" not in existing_cols:
        add("ALTER TABLE profile ADD COLUMN password_hash TEXT")
        existing_cols.add("password_hash")
        if "backup_password" in existing_cols:
            cur.execute("""
                UPDATE profile
                   SET password_hash = COALESCE(password_hash, backup_password)
                 WHERE (password_hash IS NULL OR password_hash = '')
                   AND backup_password IS NOT NULL AND backup_password <> ''
            """)

    # --- Export ---
    if "export_format" not in existing_cols:
        add("ALTER TABLE profile ADD COLUMN export_format TEXT DEFAULT 'CSV'")

    # --- Bookkeeping ---
    if "updated_at" not in existing_cols:
        add("ALTER TABLE profile ADD COLUMN updated_at TIMESTAMP")

    conn.commit()

if __name__ == "__main__":
    initialize_database()
