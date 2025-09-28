# frontend/main.py
import sys
import re
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QStackedWidget, QVBoxLayout,
    QWidget, QHBoxLayout, QFrame, QPushButton, QLabel,
    QGraphicsOpacityEffect, QDialog, QFormLayout, QLineEdit,
    QMessageBox,
)
from PySide6.QtCore import Qt, QSize, QEasingCurve, QPropertyAnimation, QByteArray
from PySide6.QtGui import QIcon, QPixmap, QPainter
from PySide6.QtSvg import QSvgRenderer

from frontend.views.overview import OverviewPage
from frontend.views.insights import InsightsPage
from frontend.views.profile import ProfilePage
from frontend.views.settings import SettingsPage
from frontend.views.login import LoginPage
from frontend.views.manage.manage_expenses import ManageExpensesPage
from frontend.views.manage.manage_wallets import ManageWalletsPage
from frontend.views.manage.manage_categories import ManageCategoriesPage
from frontend.views.manage.manage_goals import ManageGoalsPage

from frontend.theme import BackgroundCanvas, apply_app_theme
from backend.crud.profile import update_last_login
from backend.crud.profile import is_password_set, set_password  # noqa: F401
from backend.db import initialize_database


def _runtime_frontend_dir() -> Path:
    """
    Return the absolute path to the 'frontend' directory at runtime.
    - Dev run:     <repo>/frontend
    - PyInstaller: <dist>/BudgetTracker/_internal/frontend
                   (newer PyInstaller puts datas under _internal and exposes
                    their root via sys._MEIPASS)
    """
    # When running a frozen build, prefer _MEIPASS
    base = Path(getattr(sys, "_MEIPASS", "")) if getattr(sys, "frozen", False) else None
    if base and base.exists():
        return base / "frontend"
    # Fallbacks
    if getattr(sys, "frozen", False):
        # Older/alternate layouts: try alongside the exe
        return Path(sys.executable).resolve().parent / "frontend"
    # Dev path
    return Path(__file__).resolve().parent

initialize_database()

# python -m frontend.main

class PlaceholderPage(QWidget):
    def __init__(self, title: str):
        super().__init__()
        layout = QVBoxLayout(self)
        label = QLabel(title)
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)


class _CreatePasswordDialog(QDialog):
    """
    Minimal modal used on first-run when no password exists.
    Asks for new password + confirmation and validates locally.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create Password")
        self.setModal(True)
        self.resize(380, 160)

        v = QVBoxLayout(self)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.edit_new = QLineEdit()
        self.edit_new.setEchoMode(QLineEdit.Password)
        self.edit_new.setPlaceholderText("New password")

        self.edit_confirm = QLineEdit()
        self.edit_confirm.setEchoMode(QLineEdit.Password)
        self.edit_confirm.setPlaceholderText("Confirm password")

        form.addRow("New:", self.edit_new)
        form.addRow("Confirm:", self.edit_confirm)
        v.addLayout(form)

        row = QHBoxLayout()
        row.addStretch(1)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_ok = QPushButton("Set password")
        row.addWidget(self.btn_cancel)
        row.addWidget(self.btn_ok)
        v.addLayout(row)

        self.btn_cancel.clicked.connect(self.reject)
        self.btn_ok.clicked.connect(self._on_accept)

    def _on_accept(self):
        p1 = (self.edit_new.text() or "")
        p2 = (self.edit_confirm.text() or "")
        if not p1 or not p2:
            QMessageBox.warning(self, "Create Password", "Enter and confirm a password.")
            return
        if p1 != p2:
            QMessageBox.warning(self, "Create Password", "Passwords do not match.")
            return
        if len(p1) < 6:
            QMessageBox.warning(self, "Create Password", "Password must be at least 6 characters.")
            return
        self._new_password = p1
        self.accept()

    def new_password(self) -> str:
        return getattr(self, "_new_password", "")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Finance Tool")
        self.setGeometry(160, 80, 1200, 800)

        # ---------- Root with painted background ----------
        root = BackgroundCanvas(self)
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        self.setCentralWidget(root)

        # Sidebar
        self.sidebar = QFrame()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setFixedWidth(56)

        sb_layout = QVBoxLayout(self.sidebar)
        sb_layout.setContentsMargins(8, 10, 8, 10)
        sb_layout.setSpacing(10)

        # Use runtime-aware path so icons work in both dev and frozen builds
        self._icons_dir = _runtime_frontend_dir() / "assets" / "icons"
        self._icon_cache: dict[tuple[str, int, int], QIcon] = {}
        self._build_sidebar()

        # Content stack
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(16, 16, 16, 16)
        content_layout.setSpacing(0)

        self.stack = QStackedWidget()
        content_layout.addWidget(self.stack)

        root_layout.addWidget(self.sidebar)
        root_layout.addWidget(content, 1)

        # ---------- Create pages ----------
        initial_key = 1 if self.btn_toggle.isChecked() else 0
        self.overview_page        = OverviewPage(initial_toggle_key=initial_key)
        self.profile_page         = ProfilePage(initial_toggle_key=initial_key)
        self.insights_page        = InsightsPage(initial_toggle_key=initial_key)
        self.manage_expenses_page = ManageExpensesPage(initial_toggle_key=initial_key)
        self.manage_wallets_page  = ManageWalletsPage(initial_toggle_key=initial_key)
        self.manage_categories    = ManageCategoriesPage(initial_toggle_key=initial_key)
        self.manage_goals         = ManageGoalsPage(initial_toggle_key=initial_key)
        self.settings_page        = SettingsPage(initial_toggle_key=initial_key)
        self.lock_page            = LoginPage(initial_toggle_key=initial_key)

        for w in (
            self.overview_page,
            self.profile_page,
            self.insights_page,
            self.manage_expenses_page,
            self.manage_wallets_page,
            self.manage_categories,
            self.manage_goals,
            self.settings_page,
            self.lock_page,
        ):
            self.stack.addWidget(w)

        # ---------- Navigation with soft fade ----------
        self.btn_profile_sq.clicked.connect(lambda: self._fade_to(self.profile_page))
        self.btn_overview.clicked.connect(lambda: self._fade_to(self.overview_page))
        self.btn_insights.clicked.connect(lambda: self._fade_to(self.insights_page))
        self.btn_manage.clicked.connect(lambda: self._fade_to(self.manage_expenses_page))
        self.btn_lock_bottom.clicked.connect(self._lock_screen)
        self.btn_settings_bottom.clicked.connect(lambda: self._fade_to(self.settings_page))

        # Manage: Expenses → Wallets/Categories/Goals
        self.manage_expenses_page.navigateWallets.connect(lambda: self._fade_to(self.manage_wallets_page))
        self.manage_expenses_page.navigateCategories.connect(lambda: self._fade_to(self.manage_categories))
        self.manage_expenses_page.navigateGoals.connect(lambda: self._fade_to(self.manage_goals))

        # Manage: Wallets
        self.manage_wallets_page.navigateExpenses.connect(lambda: self._fade_to(self.manage_expenses_page))
        self.manage_wallets_page.navigateWallets.connect(lambda: self._fade_to(self.manage_wallets_page))
        self.manage_wallets_page.navigateCategories.connect(lambda: self._fade_to(self.manage_categories))
        self.manage_wallets_page.navigateGoals.connect(lambda: self._fade_to(self.manage_goals))

        # Manage: Goals
        self.manage_goals.navigateExpenses.connect(lambda: self._fade_to(self.manage_expenses_page))
        self.manage_goals.navigateWallets.connect(lambda: self._fade_to(self.manage_wallets_page))
        self.manage_goals.navigateCategories.connect(lambda: self._fade_to(self.manage_categories))

        # Manage: Categories
        self.manage_categories.navigateExpenses.connect(lambda: self._fade_to(self.manage_expenses_page))
        self.manage_categories.navigateWallets.connect(lambda: self._fade_to(self.manage_wallets_page))
        self.manage_categories.navigateGoals.connect(lambda: self._fade_to(self.manage_goals))

        # Toggle forwarding
        self.btn_toggle.toggled.connect(lambda c: self.overview_page.apply_toggle(1 if c else 0))
        self.btn_toggle.toggled.connect(lambda c: self.insights_page.apply_toggle(1 if c else 0))
        self.btn_toggle.toggled.connect(lambda c: self.profile_page.apply_toggle(1 if c else 0))
        self.btn_toggle.toggled.connect(lambda c: self.manage_expenses_page.apply_toggle(1 if c else 0))
        self.btn_toggle.toggled.connect(lambda c: self.manage_wallets_page.apply_toggle(1 if c else 0))
        self.btn_toggle.toggled.connect(lambda c: self.settings_page.apply_toggle(1 if c else 0))
        self.btn_toggle.toggled.connect(lambda c: self.manage_categories.apply_toggle(1 if c else 0))
        self.btn_toggle.toggled.connect(lambda c: self.manage_goals.apply_toggle(1 if c else 0))

        # ----- Initial state: show Login (no sidebar) -----
        self.stack.setCurrentWidget(self.lock_page)
        self.sidebar.setVisible(False)

        # When login succeeds, open Overview and show sidebar
        self.lock_page.authenticated.connect(self._on_authenticated)

        # Record login moment
        self._mark_last_login()

        # ---------- Auth workflow on startup (first-run create password) ----------
        self._auth_on_startup()

    # ---------- Sidebar builders ----------
    def _build_sidebar(self):
        sb = self.sidebar.layout()

        def center_row(widget):
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.addStretch(1)
            row.addWidget(widget)
            row.addStretch(1)
            return row

        # Top: square profile
        self.btn_profile_sq = self._make_square_button(36, "profile.svg")
        self.btn_profile_sq.setToolTip("Profile")
        sb.addLayout(center_row(self.btn_profile_sq))

        # Round buttons
        self.btn_overview = self._make_circle_button(32, icon_name="overview.svg")
        self.btn_overview.setToolTip("Overview")
        sb.addLayout(center_row(self.btn_overview))

        self.btn_insights = self._make_circle_button(32, icon_name="insights.svg")
        self.btn_insights.setToolTip("Insights")
        sb.addLayout(center_row(self.btn_insights))

        self.btn_manage = self._make_circle_button(32, icon_name="manage.svg")
        self.btn_manage.setToolTip("Manage")
        sb.addLayout(center_row(self.btn_manage))

        # Toggle
        self.btn_toggle = self._make_circle_button(32, checkable=True, icon_name="toggle_on.svg")
        self.btn_toggle.setToolTip("Toggle")
        self._wire_toggle_icon()
        sb.addLayout(center_row(self.btn_toggle))

        sb.addStretch(1)

        # Bottom cluster
        self.btn_lock_bottom = self._make_circle_button(32, icon_name="lock.svg")
        self.btn_lock_bottom.setToolTip("Lock Screen")
        sb.addLayout(center_row(self.btn_lock_bottom))

        self.btn_settings_bottom = self._make_circle_button(32, icon_name="settings.svg")
        self.btn_settings_bottom.setToolTip("Settings")
        sb.addLayout(center_row(self.btn_settings_bottom))

    def _make_circle_button(self, size: int, checkable: bool = False, icon_name: str | None = None):
        btn = QPushButton()
        btn.setCheckable(checkable)
        btn.setFixedSize(size, size)
        btn.setProperty("circle", True)
        if icon_name:
            btn.setIcon(self._icon_for_sidebar(icon_name, QSize(20, 20)))
            btn.setIconSize(QSize(20, 20))
        return btn

    def _make_square_button(self, size: int, icon_name: str | None = None):
        btn = QPushButton()
        btn.setFixedSize(size, size)
        btn.setProperty("square", True)
        if icon_name:
            btn.setIcon(self._icon_for_sidebar(icon_name, QSize(20, 20)))
            btn.setIconSize(QSize(20, 20))
        return btn

    def _wire_toggle_icon(self):
        def update_icon(checked):
            name = "toggle_on.svg" if checked else "toggle.svg"
            self.btn_toggle.setIcon(self._icon_for_sidebar(name, QSize(20, 20)))
        self.btn_toggle.toggled.connect(update_icon)
        self.btn_toggle.setChecked(True)
        update_icon(True)

    # ---------- Icon recolor: force black at runtime ----------
    def _icon_for_sidebar(self, icon_name: str, size: QSize) -> QIcon:
        """Load an SVG, force non-transparent fills/strokes to black, render to QIcon."""
        key = (icon_name, size.width(), size.height())
        if key in self._icon_cache:
            return self._icon_cache[key]

        svg_path = self._icons_dir / icon_name
        try:
            with open(svg_path, "r", encoding="utf-8") as f:
                txt = f.read()
            txt = self._force_black_svg_text(txt)
            icon = self._render_svg_to_icon(txt, size)
        except Exception:
            icon = QIcon(str(svg_path))

        self._icon_cache[key] = icon
        return icon

    @staticmethod
    def _force_black_svg_text(svg_text: str) -> str:
        """
        Force all paints to black while preserving 'none'/'transparent'.
        This covers attributes (fill/stroke), inline style=, and opacities.
        """
        svg_text = re.sub(r'stroke="(?!none|transparent)[^"]+"', 'stroke="#000000"', svg_text, flags=re.IGNORECASE)
        svg_text = re.sub(r'fill="(?!none|transparent)[^"]+"',   'fill="#000000"',   svg_text, flags=re.IGNORECASE)

        def fix_style(m):
            style = m.group(1)
            style = re.sub(r'stroke\s*:\s*(?!none|transparent)[#\w()., -]+', 'stroke:#000000', style, flags=re.IGNORECASE)
            style = re.sub(r'fill\s*:\s*(?!none|transparent)[#\w()., -]+',   'fill:#000000',   style, flags=re.IGNORECASE)
            style = re.sub(r'stroke-opacity\s*:\s*[^;]+', 'stroke-opacity:1', style, flags=re.IGNORECASE)
            style = re.sub(r'fill-opacity\s*:\s*[^;]+',   'fill-opacity:1',   style, flags=re.IGNORECASE)
            return f'style="{style}"'

        svg_text = re.sub(r'style="([^"]*)"', fix_style, svg_text, flags=re.IGNORECASE)
        svg_text = re.sub(r'stroke-opacity="[^"]+"', 'stroke-opacity="1"', svg_text, flags=re.IGNORECASE)
        svg_text = re.sub(r'fill-opacity="[^"]+"',   'fill-opacity="1"',   svg_text, flags=re.IGNORECASE)
        return svg_text

    @staticmethod
    def _render_svg_to_icon(svg_text: str, size: QSize) -> QIcon:
        data = QByteArray(svg_text.encode("utf-8"))
        renderer = QSvgRenderer(data)
        pm = QPixmap(size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        renderer.render(p)
        p.end()
        icon = QIcon()
        icon.addPixmap(pm)
        return icon

    def _mark_last_login(self):
        """Record an app launch / login moment."""
        try:
            update_last_login()
        except Exception as e:
            print("[Main] update_last_login failed:", e)

    def _sync_manage_nav_highlight(self, target_page):
        """
        Ensure the correct nav chip is checked on the *target* manage page.
        Centralized here so we don't duplicate logic across the four pages.
        """
        def set_tab(page, tab_key: str):
            candidates = {
                "expenses": getattr(page, "btn_nav_expenses", None) or getattr(page, "btn_expenses", None),
                "wallets": getattr(page, "btn_nav_wallets", None) or getattr(page, "btn_wallets", None),
                "categories": getattr(page, "btn_nav_categories", None) or getattr(page, "btn_categories", None),
                "goals": getattr(page, "btn_nav_goals", None) or getattr(page, "btn_goals", None),
            }
            for b in candidates.values():
                if b and hasattr(b, "setChecked"):
                    b.setChecked(False)
            btn = candidates.get(tab_key)
            if btn and hasattr(btn, "setChecked"):
                btn.setChecked(True)

        if target_page is self.manage_expenses_page:
            set_tab(self.manage_expenses_page, "expenses")
        elif target_page is self.manage_wallets_page:
            set_tab(self.manage_wallets_page, "wallets")
        elif target_page is self.manage_categories:
            set_tab(self.manage_categories, "categories")
        elif target_page is self.manage_goals:
            set_tab(self.manage_goals, "goals")

    # --------- Soft page fade ----------
    def _fade_to(self, widget):
        if self.stack.currentWidget() is widget:
            return

        self.stack.setCurrentWidget(widget)
        self._sync_manage_nav_highlight(widget)

        eff = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(eff)
        eff.setOpacity(0.0)
        anim = QPropertyAnimation(eff, b"opacity", self)
        anim.setDuration(220)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.InOutCubic)
        anim.finished.connect(lambda: widget.setGraphicsEffect(None))
        anim.start()

    # --------- First-run password creation ----------
    def _auth_on_startup(self):
        """
        If no password is set, prompt the user to create one and persist with set_password().
        Sidebar stays hidden; user still logs in on the Login page afterwards.
        """
        try:
            has_pw = is_password_set()
        except Exception as e:
            print("[Main] is_password_set failed:", e)
            return

        if not has_pw:
            dlg = _CreatePasswordDialog(self)
            if dlg.exec() == QDialog.Accepted:
                new_pw = dlg.new_password()
                try:
                    set_password(new_pw)
                    QMessageBox.information(self, "Password", "Password set successfully.")
                except Exception as e:
                    print("[Main] set_password failed:", e)
                    QMessageBox.warning(self, "Password", "Failed to set password.")

    # --------- Handlers for login/lock ----------
    def _on_authenticated(self):
        """Called when LoginPage emits `authenticated`."""
        self.sidebar.setVisible(True)
        self._fade_to(self.overview_page)

    def _lock_screen(self):
        """Manual lock: go to login and hide sidebar."""
        self.stack.setCurrentWidget(self.lock_page)
        self.sidebar.setVisible(False)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    apply_app_theme()
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
