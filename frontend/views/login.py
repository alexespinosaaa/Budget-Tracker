# frontend/views/login.py
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QSizePolicy,
    QLabel, QLineEdit, QPushButton, QMessageBox
)
from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QColor, QPainter, QRadialGradient, QPixmap, QPainterPath

import os

# Backend: read current profile (name, photo_path, etc.) + password check
from backend.crud.profile import get_current_profile, verify_password

# Theme runtime API (no layout/backend changes, just colors/styles)
from frontend.theme import current_theme, on_theme_changed


class LoginPage(QWidget):
    """
    Simple login screen:
    - 2-6-2 columns with transparent gutters
    - Center glass card with a halo background
    - Avatar above username + password input + Login button
    Emits `authenticated` when the password is verified successfully.
    """
    authenticated = Signal()  # emitted on successful login

    def __init__(self, initial_toggle_key: int = 1):
        super().__init__()
        self.toggle_key = initial_toggle_key

        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setMinimumSize(1000, 700)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # ---- Root layout (2-6-2 split) ----
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.left_section   = QFrame(); self.left_section.setStyleSheet("background: transparent;")
        self.middle_section = _LoginHaloPanel()  # paints theme halo behind content
        self.right_section  = QFrame(); self.right_section.setStyleSheet("background: transparent;")

        self._populate_middle(self.middle_section)

        row = QHBoxLayout()
        row.setContentsMargins(16, 16, 16, 16)
        row.setSpacing(16)
        row.addWidget(self.left_section, 2)
        row.addWidget(self.middle_section, 6)
        row.addWidget(self.right_section, 2)
        main_layout.addLayout(row)

        # ---- Load username + avatar from DB ----
        self._load_profile_into_ui()

        # ---- Apply theme once + subscribe to future changes ----
        self._apply_theme_colors(current_theme())
        on_theme_changed(self._apply_theme_colors)

    def _populate_middle(self, parent: QFrame):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Glass card container (styled by global QSS via theme)
        card = QFrame()
        card.setProperty("kind", "glassDeep")
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 24, 24, 24)
        card_layout.setSpacing(12)
        card_layout.addStretch(1)

        # Centered column with Avatar, Username label, and Password + Login
        column = QVBoxLayout()
        column.setSpacing(10)

        # Avatar placeholder (pixmap set if found)
        self.lbl_avatar = QLabel()
        self.lbl_avatar.setFixedSize(96, 96)
        self.lbl_avatar.setAlignment(Qt.AlignCenter)
        self.lbl_avatar.setScaledContents(True)

        # Username (themed color set in _apply_theme_colors)
        self.lbl_username = QLabel("Username")
        self.lbl_username.setAlignment(Qt.AlignHCenter)

        # Password input (inherits global QSS)
        self.input_password = QLineEdit()
        self.input_password.setEchoMode(QLineEdit.Password)
        self.input_password.setPlaceholderText("Password")
        self.input_password.setFixedWidth(360)
        self.input_password.setAlignment(Qt.AlignLeft)
        self.input_password.returnPressed.connect(self._attempt_login)  # Enter submits

        # Login button
        self.btn_login = QPushButton("Log in")
        self.btn_login.setFixedWidth(360)
        self.btn_login.setCursor(Qt.PointingHandCursor)
        self.btn_login.clicked.connect(self._attempt_login)

        column.addWidget(self.lbl_avatar, 0, Qt.AlignHCenter)
        column.addWidget(self.lbl_username, 0, Qt.AlignHCenter)
        column.addWidget(self.input_password, 0, Qt.AlignHCenter)
        column.addWidget(self.btn_login, 0, Qt.AlignHCenter)

        card_layout.addLayout(column)
        card_layout.addStretch(3)

        layout.addWidget(card, 1)

    # ---- DB → UI wiring (username + avatar only) ----
    def _load_profile_into_ui(self):
        try:
            p = get_current_profile() or {}
        except Exception as e:
            print("[LoginPage] get_current_profile failed:", e)
            p = {}

        # Username
        name = (p.get("name") or "").strip()
        self.lbl_username.setText(name if name else "User")

        # Avatar
        photo_path = p.get("photo_path")
        if isinstance(photo_path, str) and photo_path and os.path.exists(photo_path):
            self._set_avatar_pixmap(photo_path)
        else:
            self.lbl_avatar.setPixmap(QPixmap())

    def _set_avatar_pixmap(self, path: str):
        """Load, scale, and present a circular avatar pixmap in the label."""
        try:
            src = QPixmap(path)
            if src.isNull():
                return
            size = self.lbl_avatar.size()
            # Scale source to label size (cover)
            scaled = src.scaled(size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)

            # Draw into a circular mask
            diameter = min(size.width(), size.height())
            result = QPixmap(diameter, diameter)
            result.fill(Qt.transparent)

            painter = QPainter(result)
            painter.setRenderHint(QPainter.Antialiasing, True)
            path_clip = QPainterPath()
            path_clip.addEllipse(0, 0, diameter, diameter)
            painter.setClipPath(path_clip)
            # center-crop draw
            x = (scaled.width() - diameter) // 2
            y = (scaled.height() - diameter) // 2
            painter.drawPixmap(-x, -y, scaled)
            painter.end()

            self.lbl_avatar.setPixmap(result)
        except Exception as e:
            print("[LoginPage] Failed to set avatar pixmap:", e)
            self.lbl_avatar.setPixmap(QPixmap())

    # Present just to match your other pages’ interface
    def apply_toggle(self, key: int):
        if key == self.toggle_key:
            return
        self.toggle_key = key

    # ---- Login attempt ----
    def _attempt_login(self):
        pw = (self.input_password.text() or "")
        if not pw:
            QMessageBox.warning(self, "Login", "Please enter your password.")
            return
        try:
            ok = verify_password(pw)
        except Exception as e:
            print("[LoginPage] verify_password failed:", e)
            QMessageBox.warning(self, "Login", "Unable to verify password.")
            return

        if ok:
            self.input_password.clear()
            self.authenticated.emit()
        else:
            QMessageBox.warning(self, "Login", "Incorrect password. Try again.")
            self.input_password.selectAll()
            self.input_password.setFocus()

    # ---- Theme plumbing (no layout/backend changes) ----
    def _apply_theme_colors(self, theme):
        """
        Update per-widget inline styles using the active theme.
        Called once at init and again whenever the theme changes.
        """
        # Username color
        try:
            self.lbl_username.setStyleSheet(f"color: {theme.TEXT}; font-weight: 600;")
        except Exception:
            pass

        # Avatar placeholder chrome adapts to light/dark
        try:
            if theme.variant == "light":
                bg = "rgba(0,0,0,0.06)"
                br = "rgba(0,0,0,0.12)"
            else:
                bg = "rgba(255,255,255,0.08)"
                br = "rgba(255,255,255,0.12)"
            self.lbl_avatar.setStyleSheet(
                f"background: {bg}; border: 1px solid {br}; border-radius: 48px;"
            )
        except Exception:
            pass

        # Repaint the halo panel with the new theme’s colors
        try:
            self.middle_section.update()
        except Exception:
            pass


class _LoginHaloPanel(QFrame):
    """Magenta + cool blue radial halo (theme-aware like other pages)."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("background: transparent;")
        # Repaint when theme changes
        on_theme_changed(lambda *_: self.update())

    def paintEvent(self, e):
        # Pull current theme each paint so live changes reflect immediately
        theme = current_theme()

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = self.rect()

        # Left magenta orb (use MAGENTA color + theme alpha)
        g1 = QRadialGradient(r.width() * 0.28, r.height() * 0.38, min(r.width(), r.height()) * 0.65)
        g1.setColorAt(0.0, QColor(theme.MAGENTA.red(), theme.MAGENTA.green(), theme.MAGENTA.blue(), theme.orb_magenta_alpha))
        g1.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.fillRect(r, g1)

        # Right cool blue orb (use ACCENT_BLUE + theme alpha)
        g2 = QRadialGradient(r.width() * 0.80, r.height() * 0.30, min(r.width(), r.height()) * 0.70)
        g2.setColorAt(0.0, QColor(theme.ACCENT_BLUE.red(), theme.ACCENT_BLUE.green(), theme.ACCENT_BLUE.blue(), theme.orb_blue_alpha))
        g2.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.fillRect(r, g2)
