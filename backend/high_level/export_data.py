from __future__ import annotations

import csv
import io
import os
import json
import sqlite3
from datetime import datetime
from typing import List, Tuple, Optional, Dict, Any
from zipfile import ZipFile, ZIP_DEFLATED

from backend.db import get_connection

_EXPORT_TABLES: Tuple[str, ...] = (
    "category",
    "wallet",
    "expense",
    "goal",
    "profile",
)

def _fetch_table(conn: sqlite3.Connection, table: str) -> Tuple[List[str], List[sqlite3.Row]]:
    cur = conn.cursor()
    # Ensure table exists
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
    if cur.fetchone() is None:
        return [], []

    # Column order
    cur.execute(f"PRAGMA table_info({table})")
    cols = [r[1] for r in cur.fetchall()]  # r[1] = column name

    # Rows (stable order)
    order_clause = " ORDER BY id ASC" if "id" in cols else ""
    cur.execute(f"SELECT * FROM {table}{order_clause}")
    rows = cur.fetchall()
    return cols, rows

def _rows_to_dicts(cols: List[str], rows: List[sqlite3.Row]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in rows:
        # r can be a tuple; map by index to column name
        out.append({c: (r[i] if r[i] is not None else None) for i, c in enumerate(cols)})
    return out

def export_all_to_csv(
    db_path: str = "budget_tracker.db",
    out_path: Optional[str] = None,
    separate_files: bool = False,
) -> str:
    """
    Export all app tables to CSV.

    - If separate_files=False (default): produces ONE CSV file that contains all tables,
      separated by a marker row and followed by headers + data for each table.
      Example section header row: ["__TABLE__", "category"]

    - If separate_files=True: produces a ZIP archive containing one CSV per table
      (category.csv, wallet.csv, expense.csv, goal.csv, profile.csv).

    Returns the path to the created file (CSV or ZIP).
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    if out_path is None:
        out_path = f"export_all_{ts}.csv" if not separate_files else f"export_all_{ts}.zip"

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

    with get_connection(db_path) as conn:
        if not separate_files:
            # Single CSV with sections
            with open(out_path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                # Optional metadata header
                w.writerow(["__EXPORT__", "Finance Tool", "timestamp", ts])
                for table in _EXPORT_TABLES:
                    cols, rows = _fetch_table(conn, table)
                    # Section marker for clarity/tools
                    w.writerow([])
                    w.writerow(["__TABLE__", table])
                    if cols:
                        w.writerow(cols)
                        for row in rows:
                            # row is sequence-like; index by column order
                            w.writerow([row[i] if row[i] is not None else "" for i in range(len(cols))])
                    else:
                        w.writerow(["(no columns)"])
            return out_path
        else:
            # Multiple CSVs packaged into a ZIP
            with ZipFile(out_path, "w", compression=ZIP_DEFLATED) as zf:
                # Optional: include a small manifest
                manifest = f"export_timestamp,{ts}\nsource_db,{os.path.abspath(db_path)}\n"
                zf.writestr("manifest.csv", manifest)

                for table in _EXPORT_TABLES:
                    cols, rows = _fetch_table(conn, table)
                    buf = io.StringIO()
                    w = csv.writer(buf, lineterminator="\n")
                    if cols:
                        w.writerow(cols)
                        for row in rows:
                            w.writerow([row[i] if row[i] is not None else "" for i in range(len(cols))])
                    zf.writestr(f"{table}.csv", buf.getvalue())
            return out_path

def export_all_to_json(
    db_path: str = "budget_tracker.db",
    out_path: Optional[str] = None,
    separate_files: bool = False,
    pretty: bool = True,
) -> str:
    """
    Export all app tables to JSON.

    - If separate_files=False (default): produces ONE JSON file with structure:
        {
          "export": {"app": "Finance Tool", "timestamp": "...", "source_db": "..."},
          "tables": {
            "category": [ {...}, ... ],
            "wallet":   [ {...}, ... ],
            ...
          }
        }

    - If separate_files=True: produces a ZIP archive containing one JSON per table
      (category.json, wallet.json, expense.json, goal.json, profile.json),
      plus a manifest.json with basic metadata.

    Returns the path to the created file (JSON or ZIP).
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    if out_path is None:
        out_path = f"export_all_{ts}.json" if not separate_files else f"export_all_{ts}.zip"

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

    with get_connection(db_path) as conn:
        if not separate_files:
            payload = {
                "export": {
                    "app": "Finance Tool",
                    "timestamp": ts,
                    "source_db": os.path.abspath(db_path),
                    "format": "single-json",
                },
                "tables": {},
            }
            for table in _EXPORT_TABLES:
                cols, rows = _fetch_table(conn, table)
                payload["tables"][table] = _rows_to_dicts(cols, rows) if cols else []

            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2 if pretty else None)
            return out_path
        else:
            # Multiple JSONs packaged into a ZIP
            with ZipFile(out_path, "w", compression=ZIP_DEFLATED) as zf:
                manifest = {
                    "app": "Finance Tool",
                    "timestamp": ts,
                    "source_db": os.path.abspath(db_path),
                    "format": "per-table-json",
                    "tables": list(_EXPORT_TABLES),
                }
                zf.writestr(
                    "manifest.json",
                    json.dumps(manifest, ensure_ascii=False, indent=2 if pretty else None)
                )

                for table in _EXPORT_TABLES:
                    cols, rows = _fetch_table(conn, table)
                    data = _rows_to_dicts(cols, rows) if cols else []
                    zf.writestr(
                        f"{table}.json",
                        json.dumps(data, ensure_ascii=False, indent=2 if pretty else None)
                    )
            return out_path

def export_all_to_db(
    db_path: str = "budget_tracker.db",
    out_path: Optional[str] = None,
    overwrite: bool = False,
    compact: bool = True,
) -> str:
    """
    Export/backup the entire SQLite database to a new `.db` file.

    Strategy:
      1) Prefer `VACUUM INTO` (creates a compact, consistent copy) if supported.
      2) Fallback to sqlite3 backup API (src.backup(dst)) for broader compatibility.

    Args:
        db_path:      Path to the current working database.
        out_path:     Destination path for the exported .db. If None, uses a timestamped name.
        overwrite:    If False and out_path exists, raises FileExistsError.
        compact:      If True, try VACUUM INTO first (more compact). Otherwise go straight to backup.

    Returns:
        The final path of the exported .db.
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    if out_path is None:
        base = os.path.splitext(os.path.basename(db_path))[0] or "budget_tracker"
        out_path = f"{base}_export_{ts}.db"

    # Normalize/prepare directory
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

    # Safety: don't clobber unless allowed
    if os.path.abspath(db_path) == os.path.abspath(out_path):
        raise ValueError("out_path must be different from db_path.")
    if os.path.exists(out_path) and not overwrite:
        raise FileExistsError(f"Destination already exists: {out_path}")

    # Try VACUUM INTO for a compact copy (SQLite 3.27+)
    if compact:
        try:
            with get_connection(db_path) as conn:
                # Need to quote/escape the path for SQL string
                dest = out_path.replace("'", "''")
                conn.execute(f"VACUUM INTO '{dest}'")
                return out_path
        except Exception as e:
            # Fall back to backup below
            print("[export] VACUUM INTO failed; falling back to backup():", e)

    # Fallback: use sqlite3 backup API (works on older SQLite versions)
    src = None
    dst = None
    try:
        src = sqlite3.connect(db_path)
        # Ensure destination is new/empty
        if os.path.exists(out_path) and overwrite:
            os.remove(out_path)
        dst = sqlite3.connect(out_path)
        with dst:
            src.backup(dst)
        return out_path
    finally:
        if src:
            src.close()
        if dst:
            dst.close()
