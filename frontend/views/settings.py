# frontend/views/settings.py
from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QSizePolicy,
    QPushButton, QLabel, QStackedWidget, QFormLayout,
    QLineEdit, QDoubleSpinBox, QComboBox, QButtonGroup,
    QFileDialog, QMessageBox
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QRadialGradient

# --- Backend wiring (unchanged) ---
from backend.crud.profile import get_current_profile, upsert_profile
from backend.crud.profile import is_password_set, set_password, change_password  # available
from backend.crud.wallets import get_all_wallets

# --- Theme wiring (live/theme-aware) ---
from frontend.theme import (
    list_theme_options,
    apply_app_theme,
    current_theme_id,
    current_theme,
    on_theme_changed,
)


# ---------- Helper: action button that supports double-click ----------
class ActionButton(QPushButton):
    """Checkable nav button that emits doubleClicked."""
    doubleClicked = Signal()

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.setCheckable(True)

    def mouseDoubleClickEvent(self, e):
        self.doubleClicked.emit()
        super().mouseDoubleClickEvent(e)


class SettingsPage(QWidget):
    """
    Settings window with two panels:
      - Left: navigation (User, Preferences, Security)
      - Right: stacked pages with forms

    Save UX:
      - Click a nav button to open its page.
      - Click the SAME nav button again (while that page is open) to SAVE it.
      - Double-clicking a nav button also saves that page.
    """
    def __init__(self, initial_toggle_key: int = 1):
        super().__init__()
        self.toggle_key = initial_toggle_key

        # Local UI state
        self._pending_photo_path: Optional[str] = None  # None=unchanged, ""=clear, "path"=new
        self._pw_visible = False
        self._last_pw_hash_shown: Optional[str] = None

        # Root scaffold
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setMinimumSize(1000, 700)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Apply theme stylesheet BEFORE building widgets so initial paint is consistent
        self._apply_theme_qss(current_theme())
        on_theme_changed(self._apply_theme_qss)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.left_gutter  = QFrame(); self.left_gutter.setStyleSheet("background: transparent;")
        self.center_panel = _SettingsHaloPanel()
        self.right_gutter = QFrame(); self.right_gutter.setStyleSheet("background: transparent;")

        self._populate_middle(self.center_panel)

        # 20-60-20 split (2-6-2)
        row_layout = QHBoxLayout()
        row_layout.setContentsMargins(16, 16, 16, 16)
        row_layout.setSpacing(16)
        row_layout.addWidget(self.left_gutter, 2)
        row_layout.addWidget(self.center_panel, 6)
        row_layout.addWidget(self.right_gutter, 2)
        main_layout.addLayout(row_layout)

        # ---- Load from DB into UI ----
        self._load_profile_into_ui()

        # ---- Wire handlers ----
        self._wire_field_handlers()

    # ---------- UI scaffold ----------
    def _populate_middle(self, parent: QFrame):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(16)

        container = QFrame()
        container.setStyleSheet("background: transparent; border: none;")
        container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        inner = QHBoxLayout(container)
        inner.setContentsMargins(0, 0, 0, 0)
        inner.setSpacing(0)

        # Left: glass nav
        self.nav_panel = QFrame()
        self.nav_panel.setProperty("kind", "glassNav")
        self.nav_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        left_v = QVBoxLayout(self.nav_panel)
        left_v.setContentsMargins(16, 16, 16, 16)
        left_v.setSpacing(10)

        nav_title = QLabel("General")
        nav_title.setProperty("role", "subtle")
        left_v.addWidget(nav_title)

        # Action buttons
        self.btn_user     = ActionButton("User")
        self.btn_prefs    = ActionButton("Preferences")
        self.btn_security = ActionButton("Security")

        for b in (self.btn_user, self.btn_prefs, self.btn_security):
            b.setCursor(Qt.PointingHandCursor)
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            left_v.addWidget(b)

        left_v.addStretch(1)

        # Exclusive selection
        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)
        for b in (self.btn_user, self.btn_prefs, self.btn_security):
            self._nav_group.addButton(b)

        # Divider between panels (full-height)
        self.divider = QFrame()
        self.divider.setObjectName("SettingsDivider")
        self.divider.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        # Right glass: stacked content
        self.content_panel = QFrame()
        self.content_panel.setProperty("kind", "glassDeep")
        self.content_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        right_v = QVBoxLayout(self.content_panel)
        right_v.setContentsMargins(16, 16, 16, 16)
        right_v.setSpacing(12)

        # Inline save status
        self.lbl_status = QLabel("", self.content_panel)
        self.lbl_status.setObjectName("SaveStatus")
        self.lbl_status.hide()
        right_v.addWidget(self.lbl_status, 0, Qt.AlignRight)

        self.stack = QStackedWidget()
        right_v.addWidget(self.stack, 1)

        # Build pages
        self._build_user_page()
        self._build_preferences_page()
        self._build_security_page()

        inner.addWidget(self.nav_panel, 3)     # 30%
        inner.addWidget(self.divider)          # 1px vertical line
        inner.addWidget(self.content_panel, 7) # 70%
        layout.addWidget(container, 1)

        # Nav behavior: click to open, click again to save
        self.btn_user.clicked.connect(lambda: self._nav_click(0))
        self.btn_prefs.clicked.connect(lambda: self._nav_click(1))
        self.btn_security.clicked.connect(lambda: self._nav_click(2))
        self._select_section(0)

        # Double-click = save
        self.btn_user.doubleClicked.connect(lambda: self._save_section(0))
        self.btn_prefs.doubleClicked.connect(lambda: self._save_section(1))
        self.btn_security.doubleClicked.connect(lambda: self._save_section(2))

    def _nav_click(self, idx: int):
        if self.stack.currentIndex() == idx:
            self._save_section(idx)
        else:
            self._select_section(idx)

    # --------- Form helpers (alignment fix) ---------
    def _configured_form(self, parent: QWidget) -> QFormLayout:
        form = QFormLayout(parent)
        form.setRowWrapPolicy(QFormLayout.DontWrapRows)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setFormAlignment(Qt.AlignTop | Qt.AlignLeft)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(12)
        return form

    def _label_widget(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setProperty("role", "formLabel")
        return lbl

    def _wrap_row(self, left_widget: QWidget, right_widget: QWidget) -> tuple[QWidget, QWidget]:
        """
        Wrap both label and field into fixed-height containers that
        vertically center their contents. This avoids baseline quirks.
        """
        H = 36  # consistent row height

        lw = QWidget()
        lw.setMinimumHeight(H); lw.setMaximumHeight(H)
        lhb = QHBoxLayout(lw)
        lhb.setContentsMargins(0, 0, 0, 0)
        lhb.addWidget(left_widget, 0, Qt.AlignRight | Qt.AlignVCenter)

        rw = QWidget()
        rw.setMinimumHeight(H); rw.setMaximumHeight(H)
        rhb = QHBoxLayout(rw)
        rhb.setContentsMargins(0, 0, 0, 0)
        rhb.addWidget(right_widget, 1, Qt.AlignVCenter)

        return lw, rw

    # --------- Pages ---------
    def _build_user_page(self):
        page = QWidget()
        page.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        form = self._configured_form(page)

        self.input_username = QLineEdit()
        self.input_username.setPlaceholderText("Enter username")

        # Photo row (choose + remove)
        photo_row = QWidget()
        ph = QHBoxLayout(photo_row)
        ph.setContentsMargins(0, 0, 0, 0)
        ph.setSpacing(8)
        ph.setAlignment(Qt.AlignVCenter)

        self.btn_choose_photo = QPushButton("Choose Photo…")
        self.btn_choose_photo.setCursor(Qt.PointingHandCursor)

        self.btn_remove_photo = QPushButton("Remove")
        self.btn_remove_photo.setCursor(Qt.PointingHandCursor)

        ph.addWidget(self.btn_choose_photo, 0, Qt.AlignVCenter)
        ph.addWidget(self.btn_remove_photo, 0, Qt.AlignVCenter)

        # Add rows
        lw, rw = self._wrap_row(self._label_widget("Username:"), self.input_username)
        form.addRow(lw, rw)
        lw, rw = self._wrap_row(self._label_widget("Photo:"), photo_row)
        form.addRow(lw, rw)

        # Full-width subtle photo path label UNDER the settings
        self.lbl_photo_path = QLabel("(no file selected)")
        self.lbl_photo_path.setWordWrap(True)
        self.lbl_photo_path.setProperty("role", "subtle")
        self.lbl_photo_path.setStyleSheet("font-size: 12px; padding-top: 4px;")
        form.addRow(self.lbl_photo_path)

        self.stack.addWidget(page)

    def _build_preferences_page(self):
        page = QWidget()
        page.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        form = self._configured_form(page)

        # Wallet selector (Intended wallet)
        self.combo_main_wallet = QComboBox()
        self.combo_main_wallet.setObjectName("PrefsMainWallet")
        self.combo_main_wallet.addItem("(choose…)", None)

        # Theme selector
        self.combo_theme = QComboBox()
        self.combo_theme.setObjectName("PrefsTheme")
        for tid, label in list_theme_options():
            self.combo_theme.addItem(label, tid)

        # ---- HARD PIN: solid black for these two combos (box + popup) ----
        # Use widget-level stylesheet (overrides any page/app QSS),
        # and give each combo its own QListView with black background.
        from PySide6.QtWidgets import QListView  # local import to avoid touching file header

        combo_qss = """
            QComboBox {
                background: #000000;
                background-color: #000000;
                color: #FFFFFF;
                border: 1px solid rgba(255,255,255,0.25);
                border-radius: 10px;
                padding: 6px 10px;
                min-height: 32px;
                max-height: 32px;
            }
            QComboBox:hover, QComboBox:pressed, QComboBox:disabled {
                background: #000000;
                background-color: #000000;
                color: #FFFFFF;
            }
            QComboBox::drop-down { width: 22px; border: none; background: #000000; }
            QComboBox QAbstractItemView {
                background: #000000;
                color: #FFFFFF;
                selection-background-color: rgba(185,29,115,0.60);
                selection-color: #FFFFFF;
                border: 1px solid rgba(255,255,255,0.25);
                outline: 0;
            }
            QComboBox QAbstractItemView::item { background: #000000; }
        """

        # Apply to wallet combo
        self.combo_main_wallet.setStyleSheet(combo_qss)
        wallet_view = QListView()
        wallet_view.setStyleSheet("background:#000; color:#fff; "
                                "selection-background-color: rgba(185,29,115,0.60); "
                                "selection-color:#fff; border:1px solid rgba(255,255,255,0.25);")
        self.combo_main_wallet.setView(wallet_view)

        # Apply to theme combo
        self.combo_theme.setStyleSheet(combo_qss)
        theme_view = QListView()
        theme_view.setStyleSheet("background:#000; color:#fff; "
                                "selection-background-color: rgba(185,29,115,0.60); "
                                "selection-color:#fff; border:1px solid rgba(255,255,255,0.25);")
        self.combo_theme.setView(theme_view)
        # -----------------------------------------------------------------

        # Monthly budget (in Preferences)
        self.input_budget = QDoubleSpinBox()
        self.input_budget.setRange(0.0, 1_000_000.0)
        self.input_budget.setDecimals(2)
        self.input_budget.setSingleStep(10.0)

        # Skip months as free-text input "YYYY-MM, YYYY-MM, ..."
        self.edit_skip_months = QLineEdit()
        self.edit_skip_months.setPlaceholderText("e.g. 2023-12, 2024-01")

        # ---- Rows in requested order ----
        lw, rw = self._wrap_row(self._label_widget("Intended wallet:"), self.combo_main_wallet)
        form.addRow(lw, rw)

        lw, rw = self._wrap_row(self._label_widget("Theme:"), self.combo_theme)
        form.addRow(lw, rw)

        lw, rw = self._wrap_row(self._label_widget("Monthly budget:"), self.input_budget)
        form.addRow(lw, rw)

        lw, rw = self._wrap_row(self._label_widget("Skip months (net worth):"), self.edit_skip_months)
        form.addRow(lw, rw)

        self.stack.addWidget(page)

    def _build_security_page(self):
        page = QWidget()
        page.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        form = self._configured_form(page)

        # Password + small 'Show' button
        pw_row = QWidget()
        pw_layout = QHBoxLayout(pw_row)
        pw_layout.setContentsMargins(0, 0, 0, 0)
        pw_layout.setSpacing(8)

        self.input_password = QLineEdit()
        self.input_password.setEchoMode(QLineEdit.Password)
        self.input_password.setPlaceholderText("Enter a password")

        self.btn_pw_show = QPushButton("Show")
        self.btn_pw_show.setFixedHeight(32)
        self.btn_pw_show.setCursor(Qt.PointingHandCursor)
        self.btn_pw_show.setToolTip("Show the current stored password hash")

        pw_layout.addWidget(self.input_password, 1)
        pw_layout.addWidget(self.btn_pw_show, 0, Qt.AlignVCenter)

        self.input_password_confirm = QLineEdit()
        self.input_password_confirm.setEchoMode(QLineEdit.Password)
        self.input_password_confirm.setPlaceholderText("Confirm password")

        lw, rw = self._wrap_row(self._label_widget("Password:"), pw_row)
        form.addRow(lw, rw)
        lw, rw = self._wrap_row(self._label_widget("Confirm password:"), self.input_password_confirm)
        form.addRow(lw, rw)

        self.stack.addWidget(page)

    # ---- Helpers ----
    def _select_section(self, idx: int):
        self.stack.setCurrentIndex(idx)
        self.btn_user.setChecked(idx == 0)
        self.btn_prefs.setChecked(idx == 1)
        self.btn_security.setChecked(idx == 2)
        if idx == 2:
            self._update_security_ui_state()

    # ============================================================
    # Load from DB
    # ============================================================
    def _load_profile_into_ui(self):
        """Fetch current profile + wallets and populate inputs."""
        # Load wallets first so selection works when we set it
        self._load_wallets()

        prof = None
        try:
            prof = get_current_profile()
        except Exception as e:
            print("[Settings] get_current_profile failed:", e)
            prof = None

        # User
        self.input_username.setText((prof.get("name") if prof else "") or "")
        photo_path = (prof.get("photo_path") if prof else None) or ""
        self._pending_photo_path = photo_path if photo_path else None
        self.lbl_photo_path.setText(photo_path if photo_path else "(no file selected)")

        # Preferences
        try:
            self.input_budget.setValue(float((prof.get("monthly_budget") if prof else 0.0) or 0.0))
        except Exception:
            self.input_budget.setValue(0.0)

        main_wallet_id = (prof.get("main_wallet_id") if prof else None)
        if main_wallet_id is not None:
            idx = self.combo_main_wallet.findData(int(main_wallet_id))
            if idx >= 0:
                self.combo_main_wallet.setCurrentIndex(idx)

        # Theme: set combobox to profile theme (fallback to current runtime theme)
        theme_id = None
        if prof:
            theme_id = prof.get("theme") if prof.get("theme") is not None else prof.get("theme_id")
        if not isinstance(theme_id, int):
            theme_id = current_theme_id()
        idx = self.combo_theme.findData(theme_id)
        if idx >= 0:
            self.combo_theme.setCurrentIndex(idx)

        skip_val = (prof.get("skip_months") if prof else None)
        if isinstance(skip_val, list):
            self.edit_skip_months.setText(", ".join(skip_val))
        else:
            self.edit_skip_months.setText("")

        # Security placeholders/state
        self._update_security_ui_state()

    # ============================================================
    # Save per section
    # ============================================================
    def _wire_field_handlers(self):
        self.btn_choose_photo.clicked.connect(self._on_choose_photo)
        self.btn_remove_photo.clicked.connect(self._on_remove_photo)
        self.btn_pw_show.clicked.connect(self._on_show_password)  # show stored (hashed) password

    def _save_section(self, idx: int):
        if idx == 0:
            self._save_user_page()
        elif idx == 1:
            self._save_prefs_page()
        elif idx == 2:
            self._save_security_page()

    # -------------------- Photo helpers --------------------
    def _on_choose_photo(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose Photo",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp)"
        )
        if not path:
            return
        if not self._is_supported_image(path):
            self._flash_error("Unsupported image file. Please pick PNG/JPG/BMP/GIF/WebP.")
            return
        self._pending_photo_path = path
        self.lbl_photo_path.setText(path)

    def _on_remove_photo(self):
        self._pending_photo_path = ""
        self.lbl_photo_path.setText("(will be removed)")

    def _is_supported_image(self, path: str) -> bool:
        p = Path(path)
        if not p.exists() or not p.is_file():
            return False
        return p.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}

    def _photos_vault(self) -> Path:
        base = Path.home() / ".finance_tool" / "photos"
        base.mkdir(parents=True, exist_ok=True)
        return base

    def _is_inside_vault(self, path: str) -> bool:
        try:
            return Path(path).resolve().is_relative_to(self._photos_vault().resolve())
        except Exception:
            try:
                rp = Path(path).resolve()
                rv = self._photos_vault().resolve()
                return str(rp).startswith(str(rv))
            except Exception:
                return False

    def _normalize_photo_for_db(self, src_path: str) -> Optional[str]:
        if not self._is_supported_image(src_path):
            return None
        try:
            vault = self._photos_vault()
            src = Path(src_path)
            if self._is_inside_vault(str(src)):
                return str(src)
            dest = vault / src.name
            i = 1
            while dest.exists():
                dest = vault / f"{src.stem}_{i}{src.suffix.lower()}"
                i += 1
            shutil.copy2(str(src), str(dest))
            return str(dest)
        except Exception as e:
            print("[Settings] Failed to copy photo to vault:", e)
            return None

    # -------------------- User page save --------------------
    def _save_user_page(self):
        name = (self.input_username.text() or "").strip()
        photo_marker = self._pending_photo_path  # None=unchanged, ""=remove, path=new/old

        if (not name) and (photo_marker is None):
            self._flash_error("Nothing to save on User tab.")
            return

        kwargs = {}
        if name:
            kwargs["name"] = name

        if photo_marker == "":
            kwargs["photo_path"] = None
        elif isinstance(photo_marker, str):
            normalized = self._normalize_photo_for_db(photo_marker)
            if normalized is None:
                self._flash_error("Could not validate/copy the selected image.")
                return
            kwargs["photo_path"] = normalized

        try:
            ok = upsert_profile(**kwargs)
            if ok:
                self._flash_saved("Saved")
                self._load_profile_into_ui()
            else:
                self._flash_error("Save failed.")
        except Exception as e:
            print("[Settings] upsert_profile (User) failed:", e)
            self._flash_error("Save failed.")

    # -------------------- Preferences page save --------------------
    def _parse_skip_months_text(self) -> list[str]:
        txt = (self.edit_skip_months.text() or "").strip()
        if not txt:
            return []
        tokens = re.split(r"[,\s]+", txt)
        out: list[str] = []
        for t in tokens:
            if re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", t):
                out.append(t)
        seen = set()
        uniq = []
        for m in out:
            if m not in seen:
                seen.add(m)
                uniq.append(m)
        return uniq

    def _save_prefs_page(self):
        idx = self.combo_main_wallet.currentIndex()
        wallet_id = self.combo_main_wallet.itemData(idx)  # may be None
        months = self._parse_skip_months_text()
        budget = float(self.input_budget.value())

        # read theme id from combobox (stored as itemData) and persist/apply
        theme_idx = self.combo_theme.currentIndex()
        selected_theme_id = self.combo_theme.itemData(theme_idx)
        if not isinstance(selected_theme_id, int):
            selected_theme_id = None  # don't write if somehow missing

        try:
            ok = upsert_profile(
                main_wallet_id=int(wallet_id) if wallet_id is not None else None,
                skip_months=months,
                monthly_budget=budget,
                theme=selected_theme_id,   # persists INTEGER profile.theme
            )
            if ok:
                if isinstance(selected_theme_id, int):
                    apply_app_theme(selected_theme_id)
                self._flash_saved("Saved")
                self._load_profile_into_ui()
            else:
                self._flash_error("Save failed.")
        except Exception as e:
            print("[Settings] upsert_profile (Preferences) failed:", e)
            self._flash_error("Save failed.")

    # -------------------- Security page helpers/save --------------------
    def _on_show_password(self):
        """
        Show/hide the CURRENT stored password *hash* in the first field.
        (Plaintext password is not stored; we display the hash for transparency.)
        """
        if not self._pw_visible:
            try:
                prof = get_current_profile() or {}
            except Exception as e:
                print("[Settings] get_current_profile failed:", e)
                self._flash_error("Failed to read current password.")
                return

            pw_hash = prof.get("password_hash") or ""
            if not pw_hash:
                QMessageBox.information(self, "Password", "No password is set.")
                return

            # Show the hash in the password field and switch to visible
            self._last_pw_hash_shown = pw_hash
            self.input_password.setEchoMode(QLineEdit.Normal)
            self.input_password.setText(pw_hash)
            self.btn_pw_show.setText("Hide")
            self._pw_visible = True
        else:
            # Hide: clear the field to avoid accidentally saving the hash as a password
            self.input_password.clear()
            self.input_password.setEchoMode(QLineEdit.Password)
            self.btn_pw_show.setText("Show")
            self._pw_visible = False

    def _update_security_ui_state(self):
        """
        Update placeholders and top-right status chip without changing layout.
        In this flow, adding a new password and confirming will REPLACE any existing one.
        """
        has_pw = False
        try:
            has_pw = is_password_set()
        except Exception:
            has_pw = False

        if has_pw:
            self.input_password.setPlaceholderText("New password (will replace existing)")
            self.input_password_confirm.setPlaceholderText("Confirm new password")
            self._set_status_chip("Password is set")
        else:
            self.input_password.setPlaceholderText("Enter a password")
            self.input_password_confirm.setPlaceholderText("Confirm password")
            self._set_status_chip("No password set")

        # clear fields when entering the page
        self.input_password.clear()
        self.input_password_confirm.clear()
        self._pw_visible = False
        self._last_pw_hash_shown = None
        self.input_password.setEchoMode(QLineEdit.Password)
        self.input_password_confirm.setEchoMode(QLineEdit.Password)
        self.btn_pw_show.setText("Show")

    def _save_security_page(self):
        """
        Replace-on-confirm flow:
        - Regardless of current state, if Password and Confirm match and meet length,
          call set_password(new_password) to overwrite.
        """
        new_pw = (self.input_password.text() or "")
        confirm = (self.input_password_confirm.text() or "")

        if not new_pw or not confirm:
            self._flash_error("Enter password and confirmation.")
            return
        if new_pw != confirm:
            self._flash_error("Passwords do not match.")
            return
        if len(new_pw) < 6:
            self._flash_error("Password must be at least 6 characters.")
            return

        try:
            # Overwrite existing password (if any)
            set_password(new_pw)
            self._flash_saved("Password updated")
            self._update_security_ui_state()
        except Exception as e:
            print("[Settings] set_password failed:", e)
            self._flash_error("Failed to update password.")

    # ============================================================
    # Wallets loader (from DB)
    # ============================================================
    def _load_wallets(self):
        self.combo_main_wallet.clear()
        self.combo_main_wallet.addItem("(choose…)", None)

        try:
            rows = get_all_wallets() or []  # (id, name, amount, currency)
        except Exception as e:
            print("[Settings] get_all_wallets failed:", e)
            rows = []

        try:
            rows.sort(key=lambda r: (str(r[1] or "")).lower())
        except Exception:
            pass

        for r in rows:
            try:
                wid = int(r[0])
                name = "" if r[1] is None else str(r[1])
                self.combo_main_wallet.addItem(name, wid)
            except Exception:
                continue

    # ============================================================
    # Utilities
    # ============================================================
    def _set_status_chip(self, msg: str):
        self.lbl_status.setText(msg)
        self.lbl_status.show()
        # Do not auto-hide for state messages on Security page

    def _flash_saved(self, msg: str = "Saved"):
        self.lbl_status.setText(f"✔ {msg}")
        self.lbl_status.show()
        QTimer.singleShot(1400, self.lbl_status.hide)

    def _flash_error(self, msg: str):
        QMessageBox.warning(self, "Settings", msg)

    def apply_toggle(self, key: int):
        if key == self.toggle_key:
            return
        self.toggle_key = key

    # ===================== THEME QSS (live) =====================
    def _apply_theme_qss(self, theme):
        """
        Build and apply a theme-aware stylesheet for this page.
        HARD-PIN the Preferences QComboBoxes to SOLID black (box + popup).
        """
        text = theme.TEXT
        mag  = theme.MAGENTA
        blue = theme.ACCENT_BLUE

        def rgba(qc, a: float) -> str:
            return f"rgba({qc.red()},{qc.green()},{qc.blue()},{a})"

        if getattr(theme, "variant", "dark") == "light":
            nav_bg     = "rgba(0,0,0,0.06)"
            nav_hover  = "rgba(0,0,0,0.12)"
            nav_border = "rgba(0,0,0,0.10)"
            nav_bhov   = "rgba(0,0,0,0.18)"
            deep_bg    = "rgba(255,255,255,0.75)"
            deep_bord  = "rgba(0,0,0,0.10)"
            subtle_tx  = "rgba(0,0,0,0.60)"
            divider    = "rgba(0,0,0,0.10)"
            input_bg   = deep_bg
            sel_bg     = rgba(mag, 0.20)
            chip_bg    = rgba(blue, 0.20)
            chip_bd    = rgba(blue, 0.45)
        else:
            nav_bg     = "rgba(255,255,255,0.06)"
            nav_hover  = "rgba(255,255,255,0.12)"
            nav_border = "rgba(255,255,255,0.10)"
            nav_bhov   = "rgba(255,255,255,0.18)"
            deep_bg    = "rgba(12,14,22,0.50)"
            deep_bord  = "rgba(255,255,255,0.08)"
            subtle_tx  = "rgba(208,215,234,1.0)"
            divider    = "rgba(255,255,255,0.10)"
            input_bg   = "rgba(6,8,14,0.66)"
            sel_bg     = rgba(mag, 0.35)
            chip_bg    = rgba(blue, 0.35)
            chip_bd    = rgba(blue, 0.50)

        qss = f"""
            /* Glass blocks */
            QFrame[kind="glassDeep"] {{
                background: {deep_bg};
                border: 1px solid {deep_bord};
                border-radius: 14px;
            }}
            QFrame[kind="glassNav"] {{
                background: transparent;
                border: 1px solid {nav_border};
                border-top-left-radius: 14px;
                border-bottom-left-radius: 14px;
                border-top-right-radius: 0px;
                border-bottom-right-radius: 0px;
            }}

            /* Left nav buttons */
            QFrame[kind="glassNav"] QPushButton {{
                background: {nav_bg};
                border: 1px solid {nav_border};
                border-radius: 12px;
                padding: 10px 14px;
                font-size: 13px;
                font-weight: 600;
                color: {text};
                text-align: left;
            }}
            QFrame[kind="glassNav"] QPushButton:hover {{
                background: {nav_hover};
                border-color: {nav_bhov};
            }}
            QFrame[kind="glassNav"] QPushButton:checked {{
                background: {rgba(blue, 0.32 if getattr(theme, "variant", "dark") != "light" else 0.20)};
                border-color: {blue.name()};
            }}

            /* Divider */
            QFrame#SettingsDivider {{
                background: {divider};
                border: none;
                min-width: 1px; max-width: 1px;
            }}

            /* Labels and subtle text */
            QLabel[role="formLabel"] {{
                color: {text};
                font-weight: 600;
                padding-right: 8px;
            }}
            QLabel[role="subtle"] {{ color: {subtle_tx}; }}

            /* Inline status chip */
            QLabel#SaveStatus {{
                color: {text};
                background: {chip_bg};
                border: 1px solid {chip_bd};
                border-radius: 10px;
                padding: 4px 8px;
                font-size: 11px;
            }}

            /* Generic inputs */
            QLineEdit, QDoubleSpinBox {{
                background: {input_bg};
                color: {text};
                border: 1px solid {nav_border};
                border-radius: 10px;
                padding: 6px 10px;
                min-height: 32px;
                max-height: 32px;
                selection-background-color: {sel_bg};
                selection-color: {text};
            }}
            QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus {{
                border: 1px solid {mag.name()};
            }}

            /* ===== HARD PIN: Settings > Preferences combos are ALWAYS solid black ===== */
            QComboBox#PrefsMainWallet, QComboBox#PrefsTheme,
            QFrame[kind="glassDeep"] QComboBox#PrefsMainWallet,
            QFrame[kind="glassDeep"] QComboBox#PrefsTheme {{
                background: #000000;            /* SOLID */
                background-color: #000000;      /* explicitly set background-color */
                color: #FFFFFF;                 /* high contrast text */
                border: 1px solid {nav_border};
                border-radius: 10px;
                padding: 6px 10px;
                min-height: 32px;
                max-height: 32px;
            }}
            /* Ensure states don't revert transparency */
            QComboBox#PrefsMainWallet:hover, QComboBox#PrefsTheme:hover,
            QComboBox#PrefsMainWallet:pressed, QComboBox#PrefsTheme:pressed,
            QComboBox#PrefsMainWallet:!editable, QComboBox#PrefsTheme:!editable,
            QComboBox#PrefsMainWallet:disabled, QComboBox#PrefsTheme:disabled {{
                background: #000000;
                background-color: #000000;
                color: #FFFFFF;
            }}
            /* Drop-down subcontrol keeps the same solid background */
            QComboBox#PrefsMainWallet::drop-down, QComboBox#PrefsTheme::drop-down {{
                background: #000000;
                width: 22px; border: none;
            }}
            /* Popup view: support both generic view and QListView */
            QComboBox#PrefsMainWallet QAbstractItemView,
            QComboBox#PrefsTheme QAbstractItemView,
            QComboBox#PrefsMainWallet QListView,
            QComboBox#PrefsTheme QListView {{
                background: #000000;            /* SOLID popup */
                color: #FFFFFF;
                selection-background-color: {sel_bg};
                border: 1px solid {nav_border};
            }}
        """
        self.setStyleSheet(qss)


class _SettingsHaloPanel(QFrame):
    """
    Magenta + cool blue radial halo painter for the background.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("background: transparent;")
        on_theme_changed(lambda *_: self.update())

    def paintEvent(self, e):
        t = current_theme()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = self.rect()

        # Left magenta orb
        g1 = QRadialGradient(r.width() * 0.28, r.height() * 0.38, min(r.width(), r.height()) * 0.65)
        g1.setColorAt(0.0, QColor(t.MAGENTA.red(), t.MAGENTA.green(), t.MAGENTA.blue(), getattr(t, "orb_magenta_alpha", 160)))
        g1.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.fillRect(r, g1)

        # Right cool blue orb
        g2 = QRadialGradient(r.width() * 0.80, r.height() * 0.30, min(r.width(), r.height()) * 0.70)
        g2.setColorAt(0.0, QColor(t.ACCENT_BLUE.red(), t.ACCENT_BLUE.green(), t.ACCENT_BLUE.blue(), getattr(t, "orb_blue_alpha", 110)))
        g2.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.fillRect(r, g2)
