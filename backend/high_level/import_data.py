# backend/high_level/import_data.py
from __future__ import annotations

import csv
import io
import os
import json
import sqlite3
from datetime import datetime, date
from typing import Dict, List, Tuple, Any, Optional, Callable
from zipfile import ZipFile, is_zipfile

# We'll use the CRUD layer to perform inserts, and get_connection for simple lookups.
from backend.db import get_connection
from backend.crud.categories import add_category
from backend.crud.wallets import add_wallet
from backend.crud.expenses import add_expense
from backend.crud.goals import add_goal
from backend.crud.profile import upsert_profile

# Keep table list aligned with exporter
_IMPORT_TABLES: Tuple[str, ...] = (
    "category",
    "wallet",
    "expense",
    "goal",
    "profile",
)

# ---------- Schema-aware normalization ----------
# Coercers
def _to_int(v: Any) -> Optional[int]:
    if v is None or v == "":
        return None
    try:
        if isinstance(v, bool):
            return int(v)
        return int(str(v).strip())
    except Exception:
        try:
            # sometimes floats like "1.0"
            return int(float(str(v).strip()))
        except Exception:
            return None

def _to_float(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(str(v).strip())
    except Exception:
        return None

def _to_str(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v)
    return s

def _to_bool(v: Any) -> Optional[bool]:
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in ("1", "true", "yes", "y", "t"):
        return True
    if s in ("0", "false", "no", "n", "f"):
        return False
    return None

def _to_date_str(v: Any) -> Optional[str]:
    """
    Best-effort: return 'YYYY-MM-DD' (compatible with DATE columns) or None.
    Accepts date/datetime, or strings like 'YYYY-MM-DD' or ISO timestamps.
    """
    if v is None or v == "":
        return None
    if isinstance(v, (date, datetime)):
        return (v.date() if isinstance(v, datetime) else v).strftime("%Y-%m-%d")
    s = str(v).strip()
    # already date-like
    try:
        # try strict date/datetime ISO
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt.date().strftime("%Y-%m-%d")
    except Exception:
        # try basic 'YYYY-MM-DD'
        try:
            return datetime.strptime(s, "%Y-%m-%d").date().strftime("%Y-%m-%d")
        except Exception:
            return None

def _to_timestamp_str(v: Any) -> Optional[str]:
    """
    Store as text; exporter uses strings. Accept ISO-ish or datetime.
    """
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    s = str(v).strip()
    # pass-through — DB column is TEXT/TIMESTAMP; we don't enforce here
    return s

def _to_json_text(v: Any) -> Optional[str]:
    """
    For columns like profile.skip_months which are TEXT but logically JSON.
    If given a list/dict, serialize to JSON; if string, keep as-is.
    """
    if v is None:
        return None
    if isinstance(v, (list, dict)):
        try:
            return json.dumps(v, ensure_ascii=False)
        except Exception:
            return None
    return str(v)

# Per-table schema with desired columns and coercers
# NOTE: Order here is irrelevant at import-time; we just project and coerce.
_SCHEMA: Dict[str, List[Tuple[str, Callable[[Any], Any]]]] = {
    "category": [
        ("id", _to_int),
        ("name", _to_str),
        ("limit_amount", _to_float),
        ("type", _to_int),            # 0 normal, 1 fixed
        ("currency", _to_str),
    ],
    "wallet": [
        ("id", _to_int),
        ("name", _to_str),
        ("amount", _to_float),
        ("currency", _to_str),
        ("created_at", _to_timestamp_str),
    ],
    "expense": [
        ("id", _to_int),
        ("name", _to_str),
        ("category_id", _to_int),
        ("cost", _to_float),
        ("date", _to_date_str),
        ("description", _to_str),
        ("wallet_id", _to_int),
    ],
    "goal": [
        ("id", _to_int),
        ("name", _to_str),
        ("amount_to_reach", _to_float),
        ("amount_reached", _to_float),
        ("category_id", _to_int),
        ("currency", _to_str),
        ("completed", _to_bool),
        ("start_date", _to_date_str),
        ("end_date", _to_date_str),
    ],
    "profile": [
        ("id", _to_int),
        ("name", _to_str),
        ("photo_path", _to_str),
        ("monthly_budget", _to_float),
        ("main_wallet_id", _to_int),
        ("skip_months", _to_json_text),   # stored as TEXT; logical JSON
        ("theme", _to_int),
        ("password_hash", _to_str),
        ("created_at", _to_timestamp_str),
        ("last_login", _to_timestamp_str),
    ],
}

def _canonical_key(table: str, key: str) -> Optional[str]:
    """
    Map an incoming key (case-insensitive) to the exact column name in the schema.
    Unknown columns return None (and will be dropped).
    """
    cols = _SCHEMA.get(table, [])
    lookup = {c.lower(): c for c, _ in cols}
    return lookup.get((key or "").lower())

def _project_and_coerce(table: str, record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Keep only columns defined in the schema for `table`, coerce types, and
    ensure all schema columns exist (missing ones set to None).
    """
    out: Dict[str, Any] = {}
    # First, map keys case-insensitively to canonical names
    temp: Dict[str, Any] = {}
    for k, v in (record or {}).items():
        canon = _canonical_key(table, k)
        if canon:
            temp[canon] = v

    # Now coerce each expected column in schema order
    for col, coerce in _SCHEMA.get(table, []):
        raw_val = temp.get(col)
        try:
            out[col] = coerce(raw_val)
        except Exception:
            out[col] = None
    return out

def _normalize_tables_for_schema(rows_by_table: Dict[str, List[Dict[str, Any]]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Apply schema projection + coercion to all tables.
    Unknown tables are ignored; missing tables get [].
    """
    result: Dict[str, List[Dict[str, Any]]] = {}
    for table in _IMPORT_TABLES:
        items = rows_by_table.get(table, []) or []
        norm = [_project_and_coerce(table, r if isinstance(r, dict) else {}) for r in items]
        result[table] = norm
    return result

# ---------- Public entry point ----------

def import_all_from_path(path: str, *, dry_run: bool = True) -> Dict[str, Any]:
    """
    Detect the file kind (csv/json/db/zip) and parse all tables into memory.
    Returns a normalized dict with source metadata and per-table rows as dicts.

    If `dry_run` is False, this will additionally call `apply_import(...)`
    to write rows using the CRUD layer (with basic de-duplication and FK mapping).
    """
    if not path or not os.path.exists(path):
        raise FileNotFoundError(f"File not found: {path}")

    lower = path.lower()

    if lower.endswith(".db"):
        rows_raw = _read_db_copy(path)
        kind = "db"

    elif is_zipfile(path):
        # Peek into ZIP to decide CSV-vs-JSON
        with ZipFile(path, "r") as zf:
            names = {n.lower() for n in zf.namelist()}
        if any(n.endswith(".csv") for n in names):
            rows_raw = _read_csv_zip(path)
            kind = "zip-csv"
        elif any(n.endswith(".json") for n in names):
            rows_raw = _read_json_zip(path)
            kind = "zip-json"
        else:
            raise ValueError("ZIP does not contain expected .csv or .json files.")

    elif lower.endswith(".csv"):
        rows_raw = _read_csv_single_file(path)
        kind = "csv"

    elif lower.endswith(".json"):
        rows_raw = _read_json_single_file(path)
        kind = "json"

    else:
        # Fallback: try to sniff JSON, else CSV sectioned
        try:
            rows_raw = _read_json_single_file(path)
            kind = "json"
        except Exception:
            rows_raw = _read_csv_single_file(path)
            kind = "csv"

    # Ensure compatibility with the current schema (project + coerce)
    rows = _normalize_tables_for_schema(rows_raw)

    result = {
        "source": {"path": os.path.abspath(path), "kind": kind},
        "tables": rows,
    }

    if not dry_run:
        result["apply_result"] = apply_import(rows)

    return result

# ---------- CSV readers ----------

def _read_csv_single_file(path: str) -> Dict[str, List[Dict[str, Any]]]:
    """
    Parse the single "sectioned" CSV produced by export_all_to_csv(separate_files=False).

    Layout example:
      ["__EXPORT__", "Finance Tool", "timestamp", "..."]
      ...
      ["__TABLE__", "<table>"]
      ["col1","col2",...]
      [row1...]
      ...
    """
    tables: Dict[str, List[Dict[str, Any]]] = {t: [] for t in _IMPORT_TABLES}

    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        current_table: Optional[str] = None
        headers: Optional[List[str]] = None

        for raw in reader:
            row = [c.strip() for c in raw]
            if not any(row):
                # blank separator line
                continue

            # Section markers:
            if len(row) >= 2 and row[0] == "__EXPORT__":
                # Metadata row; can be stored if needed
                continue

            if len(row) >= 2 and row[0] == "__TABLE__":
                current_table = row[1].strip().lower()
                headers = None
                continue

            # Expect header or data if we have a current table
            if current_table:
                if headers is None:
                    headers = row
                    continue
                # Data row
                record = _row_to_dict(headers, row)
                tables.setdefault(current_table, []).append(record)

    # Ensure only known tables (ignore any stray sections)
    return {t: tables.get(t, []) for t in _IMPORT_TABLES}

def _read_csv_zip(path: str) -> Dict[str, List[Dict[str, Any]]]:
    """
    Parse ZIP containing per-table CSV files (from export_all_to_csv(separate_files=True)).
    Expected filenames: category.csv, wallet.csv, expense.csv, goal.csv, profile.csv
    """
    tables: Dict[str, List[Dict[str, Any]]] = {t: [] for t in _IMPORT_TABLES}

    with ZipFile(path, "r") as zf:
        for table in _IMPORT_TABLES:
            name = f"{table}.csv"
            if name not in zf.namelist():
                continue
            with zf.open(name) as fp:
                data = fp.read().decode("utf-8", errors="replace")
                f = io.StringIO(data)
                reader = csv.reader(f)
                headers: Optional[List[str]] = None
                for raw in reader:
                    row = [c.strip() for c in raw]
                    if not any(row):
                        continue
                    if headers is None:
                        headers = row
                        continue
                    record = _row_to_dict(headers, row)
                    tables[table].append(record)

    return tables

# ---------- JSON readers ----------

def _read_json_single_file(path: str) -> Dict[str, List[Dict[str, Any]]]:
    """
    Parse the single JSON produced by export_all_to_json(separate_files=False).
    """
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    # Expect structure: {"tables": {...}}
    tables_src = payload.get("tables", {})
    tables: Dict[str, List[Dict[str, Any]]] = {}
    for table in _IMPORT_TABLES:
        val = tables_src.get(table, [])
        if isinstance(val, list):
            # Already a list of dicts (exporter uses dict-per-row)
            tables[table] = [_normalize_dict(d) for d in val if isinstance(d, dict)]
        else:
            tables[table] = []
    return tables

def _read_json_zip(path: str) -> Dict[str, List[Dict[str, Any]]]:
    """
    Parse ZIP containing per-table JSON files (from export_all_to_json(separate_files=True)).
    Expected filenames: category.json, wallet.json, expense.json, goal.json, profile.json
    """
    tables: Dict[str, List[Dict[str, Any]]] = {t: [] for t in _IMPORT_TABLES}

    with ZipFile(path, "r") as zf:
        for table in _IMPORT_TABLES:
            name = f"{table}.json"
            if name not in zf.namelist():
                continue
            with zf.open(name) as fp:
                data = json.loads(fp.read().decode("utf-8", errors="replace"))
                if isinstance(data, list):
                    tables[table] = [_normalize_dict(d) for d in data if isinstance(d, dict)]
    return tables

# ---------- DB reader ----------

def _read_db_copy(db_path: str) -> Dict[str, List[Dict[str, Any]]]:
    """
    Read rows directly from a standalone SQLite database file.
    We DO NOT attach or write—just read and normalize to dicts.
    """
    tables: Dict[str, List[Dict[str, Any]]] = {t: [] for t in _IMPORT_TABLES}

    # Use a raw connection so we don't interfere with app's working DB
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        for table in _IMPORT_TABLES:
            cols, rows = _fetch_table(conn, table)
            if not cols:
                continue
            for r in rows:
                d = {c: r[c] for c in cols}
                tables[table].append(_normalize_dict(d))
    finally:
        conn.close()

    return tables

def _fetch_table(conn: sqlite3.Connection, table: str) -> Tuple[List[str], List[sqlite3.Row]]:
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
    if cur.fetchone() is None:
        return [], []
    cur.execute(f"PRAGMA table_info({table})")
    cols = [r[1] for r in cur.fetchall()]
    order_clause = " ORDER BY id ASC" if "id" in cols else ""
    cur.execute(f"SELECT * FROM {table}{order_clause}")
    rows = cur.fetchall()
    return cols, rows

# ---------- Helpers / normalization ----------

def _row_to_dict(headers: List[str], row: List[str]) -> Dict[str, Any]:
    """
    Map a CSV row list to a dict by headers, with basic type coercion:
    - "" → None
    - "true"/"false" (case-insensitive) → bool
    - try int, then float (if possible)
    """
    record: Dict[str, Any] = {}
    for i, h in enumerate(headers):
        val = row[i] if i < len(row) else ""
        record[h] = _coerce_value(val)
    return _normalize_dict(record)

def _coerce_value(val: str) -> Any:
    if val == "" or val is None:
        return None
    s = str(val).strip()
    if s.lower() in ("true", "false"):
        return s.lower() == "true"
    # Try int → float
    try:
        if s.isdigit() or (s.startswith("-") and s[1:].isdigit()):
            return int(s)
        # floats like "12.34" or "-0.5"
        return float(s)
    except Exception:
        return val

def _normalize_dict(d: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generic pass-through for raw parsed rows.
    Schema-specific cleanup is applied later by _normalize_tables_for_schema.
    """
    return dict(d)

# ---------- APPLY IMPORT (now implemented using CRUD) ----------

def apply_import(rows_by_table: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    """
    Write the parsed rows into the *current* DB using the CRUD layer.
    - De-duplicates categories (by unique name) and wallets (by name+currency) where possible.
    - Preserves referential integrity by re-mapping foreign keys for expenses/goals.
    - Uses upsert_profile for profile data.

    Returns a summary with inserted counts and basic diagnostics.
    """
    inserted = {t: 0 for t in _IMPORT_TABLES}
    errors: List[str] = []

    # --- Build ID maps from old -> new to maintain FKs ---
    category_map: Dict[Optional[int], Optional[int]] = {}
    wallet_map: Dict[Optional[int], Optional[int]] = {}

    # 1) Categories (unique name enforced by schema)
    for r in rows_by_table.get("category", []):
        name = (r.get("name") or "").strip()
        if not name:
            continue
        limit_amount = r.get("limit_amount")
        type_ = r.get("type") if r.get("type") is not None else 0
        currency = r.get("currency") or "EUR"

        # If category with same name exists, reuse it; otherwise add.
        try:
            with get_connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT id FROM category WHERE name = ?", (name,))
                row = cur.fetchone()
                if row is None:
                    try:
                        add_category(name=name, limit_amount=limit_amount, category_type=int(type_), currency=str(currency))
                        inserted["category"] += 1
                    except Exception as e:
                        # Might be a race/constraint; try to fetch again
                        errors.append(f"category add '{name}': {e}")
                    cur.execute("SELECT id FROM category WHERE name = ?", (name,))
                    row = cur.fetchone()
                new_id = int(row[0]) if row else None
        except Exception as e:
            errors.append(f"category lookup '{name}': {e}")
            new_id = None

        category_map[r.get("id")] = new_id

    # 2) Wallets (no unique constraint; use name+currency to match best-effort)
    for r in rows_by_table.get("wallet", []):
        name = (r.get("name") or "").strip()
        if not name:
            continue
        amount = r.get("amount") or 0.0
        currency = r.get("currency") or "EUR"

        try:
            with get_connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT id FROM wallet WHERE name = ? AND currency = ? ORDER BY id DESC LIMIT 1",
                    (name, currency),
                )
                row = cur.fetchone()
                if row is None:
                    try:
                        add_wallet(name=name, amount=float(amount or 0.0), currency=str(currency))
                        inserted["wallet"] += 1
                    except Exception as e:
                        errors.append(f"wallet add '{name}': {e}")
                    # fetch id after insert (or failure)
                    cur.execute(
                        "SELECT id FROM wallet WHERE name = ? AND currency = ? ORDER BY id DESC LIMIT 1",
                        (name, currency),
                    )
                    row = cur.fetchone()
                new_id = int(row[0]) if row else None
        except Exception as e:
            errors.append(f"wallet lookup '{name}': {e}")
            new_id = None

        wallet_map[r.get("id")] = new_id

    # 3) Goals (use category_map for FK remap; note: API does not accept completed/end_date)
    for r in rows_by_table.get("goal", []):
        name = (r.get("name") or "").strip()
        if not name:
            continue
        amount_to_reach = r.get("amount_to_reach") or 0.0
        amount_reached  = r.get("amount_reached") or 0.0
        src_cat_id = r.get("category_id")
        new_cat_id = category_map.get(src_cat_id)
        currency = r.get("currency") or "EUR"
        start_date = r.get("start_date")

        try:
            add_goal(
                name=name,
                amount_to_reach=float(amount_to_reach or 0.0),
                amount_reached=float(amount_reached or 0.0),
                category_id=new_cat_id,
                currency=str(currency),
                start_date=start_date,
            )
            inserted["goal"] += 1
        except Exception as e:
            errors.append(f"goal add '{name}': {e}")

    # 4) Expenses (remap category_id and wallet_id)
    for r in rows_by_table.get("expense", []):
        name = (r.get("name") or "").strip()
        cost = r.get("cost")
        date_str = r.get("date")
        if not name or cost is None or not date_str:
            # skip invalid rows
            continue
        src_cat_id = r.get("category_id")
        src_wal_id = r.get("wallet_id")
        new_cat_id = category_map.get(src_cat_id)
        new_wal_id = wallet_map.get(src_wal_id)
        description = r.get("description")

        try:
            add_expense(
                name=name,
                cost=float(cost),
                date_str=str(date_str),
                category_id=new_cat_id,
                wallet_id=new_wal_id,
                description=description if description is not None else None,
            )
            inserted["expense"] += 1
        except Exception as e:
            errors.append(f"expense add '{name}': {e}")

    # 5) Profile (use the first row if provided; upsert selectively)
    prof_rows = rows_by_table.get("profile", [])
    if prof_rows:
        r = prof_rows[0] or {}
        # upsert_profile expects native types; parse skip_months JSON text to list[str]
        skip_months_raw = r.get("skip_months")
        skip_months_list: Optional[List[str]] = None
        if isinstance(skip_months_raw, str):
            try:
                parsed = json.loads(skip_months_raw)
                if isinstance(parsed, list):
                    skip_months_list = [str(x) for x in parsed]
            except Exception:
                skip_months_list = None
        elif isinstance(skip_months_raw, list):
            skip_months_list = [str(x) for x in skip_months_raw]
        else:
            skip_months_list = None

        try:
            upsert_profile(
                name=r.get("name"),
                photo_path=r.get("photo_path"),
                monthly_budget=r.get("monthly_budget"),
                main_wallet_id=wallet_map.get(r.get("main_wallet_id"), r.get("main_wallet_id")),
                skip_months=skip_months_list,
                password_hash=r.get("password_hash"),
                theme=r.get("theme"),
            )
            # We consider this an "upsert", count as 1 change.
            inserted["profile"] = 1
        except Exception as e:
            pass