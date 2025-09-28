from __future__ import annotations

from typing import Optional, Dict, Any
import json
from datetime import datetime

from backend.db import get_connection


def _profile_columns(cur) -> set[str]:
    cur.execute("PRAGMA table_info(profile);")
    return {row[1] for row in cur.fetchall()}

def upsert_profile(
    *,
    name: Optional[str] = None,
    photo_path: Optional[str] = None,
    monthly_budget: Optional[float] = None,
    main_wallet_id: Optional[int] = None,
    skip_months: Optional[list[str]] = None,
    password_hash: Optional[str] = None,
    theme: Optional[int] = None,           # integer theme id
) -> bool:
    """
    Insert the single profile row if none exists; otherwise update only the
    provided fields (None fields are ignored).
    """
    fields: dict[str, Any] = {}
    if name is not None:
        fields["name"] = name
    if photo_path is not None:
        fields["photo_path"] = photo_path
    if monthly_budget is not None:
        fields["monthly_budget"] = float(monthly_budget)
    if main_wallet_id is not None or main_wallet_id is None:
        fields["main_wallet_id"] = main_wallet_id
    if skip_months is not None:
        fields["skip_months"] = json.dumps(list(skip_months))
    if password_hash is not None:
        fields["password_hash"] = password_hash
    if theme is not None or theme is None:
        fields["theme"] = theme

    if not fields:
        return True  # nothing to do

    with get_connection() as conn:
        cur = conn.cursor()
        cols = _profile_columns(cur)

        # Only keep keys that actually exist in the table
        fields = {k: v for k, v in fields.items() if k in cols}

        cur.execute("SELECT id FROM profile ORDER BY id LIMIT 1")
        row = cur.fetchone()

        if row is None:
            # Insert new row – name is required by schema; default if not provided
            name_val = fields.pop("name", None) or "User"
            insert_cols = ["name"] + list(fields.keys())
            insert_vals = [name_val] + list(fields.values())
            placeholders = ", ".join(["?"] * len(insert_cols))
            sql = f"INSERT INTO profile ({', '.join(insert_cols)}) VALUES ({placeholders})"
            cur.execute(sql, insert_vals)
        else:
            # Update existing row
            set_parts = [f"{k} = ?" for k in fields.keys()]
            params = list(fields.values())

            # Only add updated_at if the column exists
            if "updated_at" in cols:
                set_parts.append("updated_at = ?")
                params.append(datetime.utcnow().isoformat(timespec="seconds"))

            sql = (
                "UPDATE profile "
                f"SET {', '.join(set_parts)} "
                "WHERE id = (SELECT id FROM profile ORDER BY id LIMIT 1)"
            )
            cur.execute(sql, params)

        conn.commit()
        return True

def get_current_profile() -> Dict[str, Any] | None:
    """
    Return the single profile row as a dict (or None if missing).
    Keys returned: id, name, photo_path, monthly_budget, main_wallet_id,
    skip_months (decoded if JSON), password_hash, created_at, last_login,
    theme, theme_id (alias).
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                id, name, photo_path, monthly_budget,
                main_wallet_id, skip_months, password_hash,
                created_at, last_login, theme
            FROM profile
            ORDER BY id
            LIMIT 1
            """
        )
        row = cur.fetchone()
        if not row:
            return None

        (pid, name, photo_path, monthly_budget,
         main_wallet_id, skip_months, password_hash,
         created_at, last_login, theme_val) = row

        parsed_skip: Any = skip_months
        if isinstance(skip_months, str) and skip_months.strip().startswith("["):
            try:
                parsed_skip = json.loads(skip_months)
            except Exception:
                parsed_skip = skip_months

        return {
            "id": pid,
            "name": name,
            "photo_path": photo_path,
            "monthly_budget": monthly_budget,
            "main_wallet_id": main_wallet_id,
            "skip_months": parsed_skip,
            "password_hash": password_hash,
            "created_at": created_at,
            "last_login": last_login,
            "theme": theme_val,
            "theme_id": theme_val,
        }

def update_last_login(when: datetime | None = None) -> bool:
    """Set profile.last_login to the given datetime (UTC ISO) or now (and updated_at if that column exists)."""
    ts = (when or datetime.utcnow()).isoformat(timespec="seconds")
    with get_connection() as conn:
        cur = conn.cursor()
        cols = _profile_columns(cur)

        cur.execute("SELECT id FROM profile ORDER BY id LIMIT 1")
        row = cur.fetchone()
        if row is None:
            cur.execute("INSERT INTO profile (name, last_login) VALUES (?, ?)", ("User", ts))
        else:
            if "updated_at" in cols:
                cur.execute("""
                    UPDATE profile
                       SET last_login = ?, updated_at = ?
                     WHERE id = (SELECT id FROM profile ORDER BY id LIMIT 1)
                """, (ts, ts))
            else:
                cur.execute("""
                    UPDATE profile
                       SET last_login = ?
                     WHERE id = (SELECT id FROM profile ORDER BY id LIMIT 1)
                """, (ts,))
        conn.commit()
        return True
    
def get_all_profiles():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM profile')
        return cursor.fetchall()
    
##### Password

def _get_or_create_profile_id():
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM profile ORDER BY id LIMIT 1")
        row = cur.fetchone()
        if row:
            return int(row[0])
        cur.execute("INSERT INTO profile (name) VALUES (?)", ("User",))
        conn.commit()
        cur.execute("SELECT id FROM profile ORDER BY id LIMIT 1")
        row = cur.fetchone()
        return int(row[0]) if row else None

def is_password_set() -> bool:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT password_hash FROM profile ORDER BY id LIMIT 1")
        row = cur.fetchone()
        if not row:
            return False
        return bool(row[0])

def set_password(password: str) -> None:
    if not isinstance(password, str) or password == "":
        raise ValueError("Password must be a non-empty string.")
    import os, hashlib, base64
    iterations = 200_000
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    salt_b64 = base64.b64encode(salt).decode("ascii")
    dk_b64 = base64.b64encode(dk).decode("ascii")
    stored = f"pbkdf2_sha256${iterations}${salt_b64}${dk_b64}"
    pid = _get_or_create_profile_id()
    if pid is None:
        raise RuntimeError("Failed to ensure profile row exists.")
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE profile SET password_hash = ? WHERE id = ?", (stored, pid))
        conn.commit()

def verify_password(password: str) -> bool:
    if not isinstance(password, str):
        return False
    import hashlib, base64, hmac
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT password_hash FROM profile ORDER BY id LIMIT 1")
        row = cur.fetchone()
        if not row or not row[0]:
            return False
        stored = str(row[0])
    try:
        algo, iter_s, salt_b64, dk_b64 = stored.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        iterations = int(iter_s)
        salt = base64.b64decode(salt_b64)
        dk_stored = base64.b64decode(dk_b64)
        dk_check = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(dk_stored, dk_check)
    except Exception:
        return False

def change_password(old_password: str, new_password: str) -> bool:
    if not new_password:
        return False
    if not verify_password(old_password):
        return False
    set_password(new_password)
    return True
