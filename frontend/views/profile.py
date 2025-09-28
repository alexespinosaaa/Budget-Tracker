# frontend/views/profile.py
from __future__ import annotations

import os
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QSizePolicy,
    QLabel, QPushButton, QComboBox, QFileDialog, QMessageBox
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor, QPainter, QRadialGradient, QPixmap, QPainterPath

# Backend: read current profile (name, photo_path, created_at, last_login)
from backend.crud.profile import get_current_profile
# Backend: export functions
from backend.high_level.export_data import (
    export_all_to_csv,
    export_all_to_json,
    export_all_to_db,
)
# NEW: Import functions (wired to backend high-level importer)
from backend.high_level.import_data import import_all_from_path

# Theme API (for live theme updates without layout/backend changes)
from frontend.theme import current_theme, on_theme_changed


class ProfilePage(QWidget):
    """
    User Profile window (same visual language as Login):
      - 2-6-2 layout with transparent gutters
      - Center glass card inside a halo background
      - Circular avatar (from photo_path), Name
      - Two small labels: Created at, Last login
      - Export controls: format combobox + Export button (wired to backend exporters)
      - Import controls: format combobox (CSV, JSON, .db) + Import button (wired to backend importer)
    """
    def __init__(self, initial_toggle_key: int = 1):
        super().__init__()
        self.toggle_key = initial_toggle_key

        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setMinimumSize(1000, 700)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # ---- Root: 2-6-2 columns with halo middle ----
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.left_section   = QFrame(); self.left_section.setStyleSheet("background: transparent;")
        self.middle_section = _ProfileHaloPanel()
        self.right_section  = QFrame(); self.right_section.setStyleSheet("background: transparent;")

        self._populate_middle(self.middle_section)

        row = QHBoxLayout()
        row.setContentsMargins(16, 16, 16, 16)
        row.setSpacing(16)
        row.addWidget(self.left_section, 2)
        row.addWidget(self.middle_section, 6)
        row.addWidget(self.right_section, 2)
        main_layout.addLayout(row)

        # Populate with DB values
        self._load_profile_into_ui()

        # Apply theme now and subscribe to changes
        self._apply_theme_colors(current_theme())
        on_theme_changed(self._apply_theme_colors)

    # ---------------- UI scaffold ----------------
    def _populate_middle(self, parent: QFrame):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Glass card container (styled by global theme)
        card = QFrame()
        card.setProperty("kind", "glassDeep")
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 24, 24, 24)
        card_layout.setSpacing(16)
        card_layout.addStretch(1)

        # Center column
        column = QVBoxLayout()
        column.setSpacing(10)

        # Avatar (circular)
        self.lbl_avatar = QLabel()
        self.lbl_avatar.setFixedSize(120, 120)
        self.lbl_avatar.setAlignment(Qt.AlignCenter)
        self.lbl_avatar.setScaledContents(True)
        # Avatar chrome styled in _apply_theme_colors

        # Name
        self.lbl_name = QLabel("User")
        self.lbl_name.setAlignment(Qt.AlignHCenter)
        # Color set in _apply_theme_colors

        # Created at / Last login (subtle)
        self.lbl_created = QLabel("Created: —")
        self.lbl_last    = QLabel("Last login: —")
        for w in (self.lbl_created, self.lbl_last):
            w.setAlignment(Qt.AlignHCenter)
            w.setProperty("role", "subtle")
            # Color set in _apply_theme_colors

        # Export controls
        export_row = QHBoxLayout()
        export_row.setSpacing(8)
        export_row.setAlignment(Qt.AlignHCenter)

        self.combo_export = QComboBox()
        self.combo_export.addItems(["CSV", "JSON", "SQLite backup (.db)"])
        self.combo_export.setFixedWidth(220)
        # High-contrast dropdown styling (works for dark/light)
        self.combo_export.setStyleSheet("""
            QComboBox {
                background: rgba(6,8,14,0.66);
                color: #FFFFFF;
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 10px;
                padding: 6px 10px;
                min-height: 32px; max-height: 32px;
            }
            QComboBox::drop-down { width: 22px; border: none; }
            QComboBox QAbstractItemView {
                background: #000000;                 /* solid black for popup */
                color: #FFFFFF;
                selection-background-color: rgba(185,29,115,0.60);
                selection-color: #FFFFFF;
                border: 1px solid rgba(255,255,255,0.25);
            }
        """)
        try:
            self.combo_export.view().setStyleSheet("""
                background: #000000;
                color: #FFFFFF;
                selection-background-color: rgba(185,29,115,0.60);
                selection-color: #FFFFFF;
                border: 1px solid rgba(255,255,255,0.25);
            """)
        except Exception:
            pass

        self.btn_export = QPushButton("Export")
        self.btn_export.setCursor(Qt.PointingHandCursor)
        self.btn_export.setToolTip("Export data")
        self.btn_export.setFixedHeight(32)
        self.btn_export.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,0.06);
                border: 1px solid rgba(255,255,255,0.10);
                color: #FFFFFF; border-radius: 10px; padding: 6px 14px;
                min-width: 100px;
            }
            QPushButton:hover {
                background: rgba(255,255,255,0.12);
                border-color: rgba(255,255,255,0.18);
            }
        """)
        self.btn_export.clicked.connect(self._on_export_clicked)

        export_row.addWidget(self.combo_export, 0, Qt.AlignVCenter)
        export_row.addWidget(self.btn_export, 0, Qt.AlignVCenter)

        # --- Import controls (same dimensions, format, and position — directly underneath) ---
        import_row = QHBoxLayout()
        import_row.setSpacing(8)
        import_row.setAlignment(Qt.AlignHCenter)

        self.combo_import = QComboBox()
        # exactly as requested: 'CSV, JSON and .db'
        self.combo_import.addItems(["CSV", "JSON", ".db"])
        self.combo_import.setFixedWidth(220)
        self.combo_import.setStyleSheet("""
            QComboBox {
                background: rgba(6,8,14,0.66);
                color: #FFFFFF;
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 10px;
                padding: 6px 10px;
                min-height: 32px; max-height: 32px;
            }
            QComboBox::drop-down { width: 22px; border: none; }
            QComboBox QAbstractItemView {
                background: #000000;
                color: #FFFFFF;
                selection-background-color: rgba(185,29,115,0.60);
                selection-color: #FFFFFF;
                border: 1px solid rgba(255,255,255,0.25);
            }
        """)
        try:
            self.combo_import.view().setStyleSheet("""
                background: #000000;
                color: #FFFFFF;
                selection-background-color: rgba(185,29,115,0.60);
                selection-color: #FFFFFF;
                border: 1px solid rgba(255,255,255,0.25);
            """)
        except Exception:
            pass

        self.btn_import = QPushButton("Import")
        self.btn_import.setCursor(Qt.PointingHandCursor)
        self.btn_import.setToolTip("Import data")
        self.btn_import.setFixedHeight(32)
        self.btn_import.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,0.06);
                border: 1px solid rgba(255,255,255,0.10);
                color: #FFFFFF; border-radius: 10px; padding: 6px 14px;
                min-width: 100px;
            }
            QPushButton:hover {
                background: rgba(255,255,255,0.12);
                border-color: rgba(255,255,255,0.18);
            }
        """)
        self.btn_import.clicked.connect(self._on_import_clicked)

        import_row.addWidget(self.combo_import, 0, Qt.AlignVCenter)
        import_row.addWidget(self.btn_import, 0, Qt.AlignVCenter)

        # Assemble column
        column.addWidget(self.lbl_avatar, 0, Qt.AlignHCenter)
        column.addWidget(self.lbl_name,   0, Qt.AlignHCenter)
        column.addWidget(self.lbl_created, 0, Qt.AlignHCenter)
        column.addWidget(self.lbl_last,    0, Qt.AlignHCenter)
        column.addSpacing(8)
        column.addLayout(export_row)
        column.addLayout(import_row)  # directly underneath, same alignment and sizing
        column.addSpacing(12)

        card_layout.addLayout(column)
        card_layout.addStretch(3)

        layout.addWidget(card, 1)

    # --------------- DB → UI wiring ---------------
    def _load_profile_into_ui(self):
        try:
            p = get_current_profile() or {}
        except Exception as e:
            print("[ProfilePage] get_current_profile failed:", e)
            p = {}

        # Name
        name = (p.get("name") or "").strip()
        self.lbl_name.setText(name if name else "User")

        # Avatar
        photo_path = p.get("photo_path")
        if isinstance(photo_path, str) and photo_path and os.path.exists(photo_path):
            self._set_avatar_pixmap(photo_path)
        else:
            self.lbl_avatar.setPixmap(QPixmap())

        # Timestamps
        created_at = p.get("created_at")
        last_login = p.get("last_login")

        self.lbl_created.setText(f"Created: {self._fmt_ts(created_at)}")
        self.lbl_last.setText(f"Last login: {self._fmt_ts(last_login)}")

    def _fmt_ts(self, value) -> str:
        """
        Render timestamps nicely. Accepts SQLite-style strings like 'YYYY-MM-DD HH:MM:SS'
        or Python datetime; falls back to raw/—.
        """
        if value in (None, "", "null"):
            return "—"
        if isinstance(value, datetime):
            return value.strftime("%Y-%m-%d %H:%M")
        if isinstance(value, str):
            # Try parsing common ISO/SQLite formats
            try:
                v = value.replace("T", " ")
                dt = datetime.fromisoformat(v)
                return dt.strftime("%Y-%m-%d %H:%M")
            except Exception:
                return value  # show as-is
        return str(value)

    def _set_avatar_pixmap(self, path: str):
        """Load, scale, and present a circular avatar pixmap in the label."""
        try:
            src = QPixmap(path)
            if src.isNull():
                return
            size = self.lbl_avatar.size()
            scaled = src.scaled(size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            diameter = min(size.width(), size.height())
            result = QPixmap(diameter, diameter)
            result.fill(Qt.transparent)

            painter = QPainter(result)
            painter.setRenderHint(QPainter.Antialiasing, True)
            clip = QPainterPath()
            clip.addEllipse(0, 0, diameter, diameter)
            painter.setClipPath(clip)

            x = (scaled.width() - diameter) // 2
            y = (scaled.height() - diameter) // 2
            painter.drawPixmap(-x, -y, scaled)
            painter.end()

            self.lbl_avatar.setPixmap(result)
        except Exception as e:
            print("[ProfilePage] Failed to set avatar pixmap:", e)
            self.lbl_avatar.setPixmap(QPixmap())

    # -------- Export wiring --------
    def _on_export_clicked(self):
        fmt = (self.combo_export.currentText() or "").strip().upper()
        # Choose default filename & extension
        if "JSON" in fmt:
            default_name = "export_all.json"
            filt = "JSON files (*.json);;All files (*.*)"
        elif "DB" in fmt:
            default_name = "export_all.db"
            filt = "SQLite DB (*.db);;All files (*.*)"
        else:
            default_name = "export_all.csv"
            filt = "CSV files (*.csv);;All files (*.*)"

        out_path, _ = QFileDialog.getSaveFileName(self, "Export data", default_name, filt)
        if not out_path:
            return  # user canceled

        try:
            if "JSON" in fmt:
                final_path = export_all_to_json(out_path=out_path, separate_files=False, pretty=True)
            elif "DB" in fmt:
                final_path = export_all_to_db(out_path=out_path, overwrite=True, compact=True)
            else:
                final_path = export_all_to_csv(out_path=out_path, separate_files=False)

            QMessageBox.information(self, "Export", f"Exported successfully to:\n{os.path.abspath(final_path)}")
        except Exception as e:
            print("[ProfilePage] Export failed:", e)
            QMessageBox.critical(self, "Export", f"Export failed.\n{e}")

    # -------- Import wiring --------
    def _on_import_clicked(self):
        fmt = (self.combo_import.currentText() or "").strip().upper()
        if "JSON" in fmt:
            filt = "JSON files (*.json);;All files (*.*)"
        elif ".DB" in fmt or "DB" in fmt:
            filt = "SQLite DB (*.db);;All files (*.*)"
        else:
            filt = "CSV files (*.csv);;All files (*.*)"

        in_path, _ = QFileDialog.getOpenFileName(self, "Import data", "", filt)
        if not in_path:
            return  # user canceled

        # 1) Dry run – parse & summarize without touching the DB
        try:
            preview = import_all_from_path(in_path, dry_run=True)
        except Exception as e:
            print("[ProfilePage] Import dry-run failed:", e)
            QMessageBox.critical(self, "Import", f"Couldn't parse the file.\n\n{e}")
            return

        src = preview.get("source", {})
        tables = preview.get("tables", {})
        counts = {k: len(v or []) for k, v in tables.items()}

        # Build a friendly summary string
        lines = [f"Detected source: {src.get('kind', '?')}"]
        for t in ("category", "wallet", "expense", "goal", "profile"):
            lines.append(f"  • {t}: {counts.get(t, 0)} rows")
        lines.append("")
        lines.append("Do you want to import this data into the current database?")

        # 2) Ask for confirmation
        resp = QMessageBox.question(
            self,
            "Confirm import",
            "\n".join(lines),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if resp != QMessageBox.Yes:
            return

        # 3) Apply import – this will write to DB according to backend placeholders/logic
        try:
            result = import_all_from_path(in_path, dry_run=False)
        except Exception as e:
            print("[ProfilePage] Import apply failed:", e)
            QMessageBox.critical(self, "Import", f"Import failed.\n\n{e}")
            return

        apply_res = result.get("apply_result") or {}
        status = apply_res.get("status", "ok")
        inserted = apply_res.get("inserted") or {}
        available = apply_res.get("available_to_import") or {}

        # Compose result message
        msg_lines = [f"Status: {status}"]
        if inserted:
            msg_lines.append("Inserted rows:")
            for t in ("category", "wallet", "expense", "goal", "profile"):
                if t in inserted:
                    msg_lines.append(f"  • {t}: {inserted.get(t, 0)}")
        if available and status == "placeholder":
            msg_lines.append("")
            msg_lines.append("Parsed rows available (no DB writes performed yet):")
            for t in ("category", "wallet", "expense", "goal", "profile"):
                if t in available:
                    msg_lines.append(f"  • {t}: {available.get(t, 0)}")

        QMessageBox.information(self, "Import", "\n".join(msg_lines))

        # 4) Refresh profile view in case profile row changed
        try:
            self._load_profile_into_ui()
        except Exception:
            pass

    # Toggle hook for consistency with other pages
    def apply_toggle(self, key: int):
        if key == self.toggle_key:
            return
        self.toggle_key = key

    # ---- Theme plumbing (no layout/backend changes) ----
    def _apply_theme_colors(self, theme):
        """Update inline colors to match the active theme."""
        try:
            # Text colors
            self.lbl_name.setStyleSheet(f"color: {theme.TEXT}; font-size: 18px; font-weight: 700;")
            sub = theme.TEXT_SECONDARY
            for w in (self.lbl_created, self.lbl_last):
                w.setStyleSheet(f"color: {sub}; font-size: 12px;")
        except Exception:
            pass

        try:
            # Avatar chrome adapts to light/dark variant
            if theme.variant == "light":
                bg = "rgba(0,0,0,0.06)"
                br = "rgba(0,0,0,0.12)"
            else:
                bg = "rgba(255,255,255,0.08)"
                br = "rgba(255,255,255,0.12)"
            self.lbl_avatar.setStyleSheet(
                f"background: {bg}; border: 1px solid {br}; border-radius: 60px;"
            )
        except Exception:
            pass

        # Repaint halo with new theme colors
        try:
            self.middle_section.update()
        except Exception:
            pass


class _ProfileHaloPanel(QFrame):
    """Magenta + cool blue radial halo painter for the background (theme-aware)."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("background: transparent;")
        # Repaint on theme change
        on_theme_changed(lambda _: self.update())

    def paintEvent(self, e):
        theme = current_theme()

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = self.rect()

        # Left magenta orb (theme.MAGENTA)
        g1 = QRadialGradient(r.width() * 0.28, r.height() * 0.38, min(r.width(), r.height()) * 0.65)
        g1.setColorAt(0.0, QColor(theme.MAGENTA.red(), theme.MAGENTA.green(), theme.MAGENTA.blue(), theme.orb_magenta_alpha))
        g1.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.fillRect(r, g1)

        # Right cool blue orb (theme.ACCENT_BLUE)
        g2 = QRadialGradient(r.width() * 0.80, r.height() * 0.30, min(r.width(), r.height()) * 0.70)
        g2.setColorAt(0.0, QColor(theme.ACCENT_BLUE.red(), theme.ACCENT_BLUE.green(), theme.ACCENT_BLUE.blue(), theme.orb_blue_alpha))
        g2.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.fillRect(r, g2)
