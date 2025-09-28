# frontend/views/overview.py

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QSizePolicy,
    QLabel, QGraphicsOpacityEffect, QStackedLayout
)
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QColor, QPainter, QRadialGradient

from backend.high_level.analysis import display_selected_wallet, month_comparasion
from backend.high_level.graphs import expenses_in_calendar_qt
from backend.crud.profile import get_current_profile

# Theme hooks: repaint halo + allow charts to rebuild with active theme
from frontend.theme import on_theme_changed, current_theme

class OverviewPage(QWidget):
    """
    Overview page with glass UI. Backend/data calls are unchanged.
    Adds: refresh-from-DB on showEvent so new expenses are reflected.
    """
    def __init__(self, initial_toggle_key: int = 1):
        super().__init__()
        self.toggle_key = initial_toggle_key
        self.graph_layout = None
        self.graph_widget = None
        self.wallet_value_label = None
        self.spent_value_label = None
        self.change_value_label = None
        self._fade_anim = None
        self._fade_widget = None

        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setMinimumSize(1000, 700)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # ---- Root layout (keep 2-6-2 split) ----
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.left_section = QFrame();  self.left_section.setStyleSheet("background: transparent;")
        self.middle_section = HaloPanel()  # paints soft halo behind content (theme-aware)
        self.right_section = QFrame(); self.right_section.setStyleSheet("background: transparent;")

        self._populate_middle(self.middle_section)

        row_layout = QHBoxLayout()
        row_layout.setContentsMargins(16, 16, 16, 16)
        row_layout.setSpacing(16)
        row_layout.addWidget(self.left_section, 2)
        row_layout.addWidget(self.middle_section, 6)
        row_layout.addWidget(self.right_section, 2)
        main_layout.addLayout(row_layout)

        # Theme changes: rebuild the graph and repaint halo
        on_theme_changed(lambda _t: self._refresh_for_theme())

    # ---------- helpers ----------
    def _selected_wallet_id(self) -> int:
        """
        Pull the user's preferred wallet from profile (main_wallet_id).
        Fallback to 1 if not set so the app continues to work.
        """
        try:
            prof = get_current_profile() or {}
            wid = prof.get("main_wallet_id")
            if isinstance(wid, int) and wid > 0:
                return wid
        except Exception:
            pass
        return 1  # sensible fallback

    def _fmt2(self, value) -> str:
        """Format to 2 decimal places safely."""
        try:
            return f"{float(value):.2f}"
        except Exception:
            return str(value)

    def _kpi_card(self, title_text: str, value_text: str) -> QFrame:
        card = QFrame()
        card.setProperty("kind", "glass")
        card.setFixedHeight(140)
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        v = QVBoxLayout(card)
        v.setContentsMargins(16, 12, 16, 12)
        v.setSpacing(6)

        title = QLabel(title_text)
        title.setProperty("kpi", True)
        title.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        title.setStyleSheet("color: #FFFFFF;")  # force white label

        value = QLabel(value_text)
        value.setProperty("value", True)
        value.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)

        # Top-centered label, value centered vertically/horizontally
        v.addWidget(title, 0, Qt.AlignHCenter | Qt.AlignTop)
        v.addStretch(1)
        v.addWidget(value, 0, Qt.AlignHCenter)
        v.addStretch(1)
        return card

    def _populate_middle(self, parent: QFrame):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(16)

        # ----- Wallet + KPI data (use profile's preferred wallet) -----
        wallet_id = self._selected_wallet_id()
        wallet_info = display_selected_wallet(wallet_id)  # expected: [name, amount, currency]
        wallet_name = wallet_info[0] if len(wallet_info) > 0 else "Wallet"
        wallet_amount = wallet_info[1] if len(wallet_info) > 1 else 0.0
        wallet_currency = wallet_info[2] if len(wallet_info) > 2 else "EUR"
        wallet_value = f"{self._fmt2(wallet_amount)} {wallet_currency}"

        mc = month_comparasion(toggle_state=self.toggle_key, main_wallet=wallet_id)  # expected: [?, spent, pct_change]
        spent_amount = mc[1] if len(mc) > 1 else 0.0
        spent_value = f"{self._fmt2(spent_amount)} {wallet_currency}"

        # ---- KPI row ----
        summary_row = QHBoxLayout()
        summary_row.setSpacing(16)

        first_box  = self._kpi_card(wallet_name, wallet_value)
        second_box = self._kpi_card("Spent this month", spent_value)

        try:
            change_pct = float(mc[2])
            change_text = f"{change_pct:.2f}%"
        except Exception:
            change_text = f"{mc[2]}%" if len(mc) > 2 else "0.00%"
        third_box  = self._kpi_card("Month comparison", change_text)

        # keep handles to update on toggle / refresh
        self.wallet_value_label = None
        for w in first_box.findChildren(QLabel):
            if w.property("value") is True:
                self.wallet_value_label = w
                break

        self.spent_value_label = None
        for w in second_box.findChildren(QLabel):
            if w.property("value") is True:
                self.spent_value_label = w
                break

        self.change_value_label = None
        for w in third_box.findChildren(QLabel):
            if w.property("value") is True:
                self.change_value_label = w
                break

        summary_row.addWidget(first_box)
        summary_row.addWidget(second_box)
        summary_row.addWidget(third_box)
        layout.addLayout(summary_row)

        # ---- Calendar graph ----
        graph_card = QFrame()
        graph_card.setProperty("kind", "glassDeep")
        graph_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.graph_layout = QVBoxLayout(graph_card)
        self.graph_layout.setContentsMargins(12, 12, 12, 12)

        # matte plot area frame so charts pop
        plot_area = QFrame()
        plot_area.setProperty("kind", "plot")

        # Use a stacked layout so only one canvas is visible at a time
        self._stack = QStackedLayout(plot_area)
        self._stack.setContentsMargins(0, 0, 0, 0)
        self._stack.setStackingMode(QStackedLayout.StackOne)

        self.graph_widget = expenses_in_calendar_qt(toggle_state=self.toggle_key, main_wallet=wallet_id)
        if hasattr(self.graph_widget, "setSizePolicy"):
            self.graph_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self._stack.addWidget(self.graph_widget)
        self._stack.setCurrentWidget(self.graph_widget)

        self.graph_layout.addWidget(plot_area)
        layout.addWidget(graph_card, 6)

        parent.setLayout(layout)

    # ---- DB refresh hook (called on showEvent) ----
    def _refresh_from_db(self):
        """
        Re-read DB-backed values and update KPI labels + calendar graph.
        Called when the page becomes visible to reflect latest changes.
        """
        # Current preferred wallet
        wallet_id = self._selected_wallet_id()
        w = display_selected_wallet(wallet_id)  # [name, amount, currency]
        wallet_amount = w[1] if len(w) > 1 else 0.0
        currency = w[2] if len(w) > 2 else "EUR"

        # KPIs from DB
        mc = month_comparasion(toggle_state=self.toggle_key, main_wallet=wallet_id)
        spent_amount = mc[1] if len(mc) > 1 else 0.0

        # Update labels if we have them
        if self.wallet_value_label is not None:
            self.wallet_value_label.setText(f"{self._fmt2(wallet_amount)} {currency}")

        if self.spent_value_label is not None:
            self.spent_value_label.setText(f"{self._fmt2(spent_amount)} {currency}")

        if self.change_value_label is not None:
            try:
                change_pct = float(mc[2])
                change_text = f"{change_pct:.2f}%"
            except Exception:
                change_text = f"{mc[2]}%" if len(mc) > 2 else "0.00%"
            self.change_value_label.setText(change_text)

        # Rebuild graph (reads fresh data)
        new_canvas = expenses_in_calendar_qt(toggle_state=self.toggle_key, main_wallet=wallet_id)
        if hasattr(new_canvas, "setSizePolicy"):
            new_canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # subtle fade
        self._fade_in_over_current(new_canvas, duration=160)

    # ---- Toggle updates ----
    def apply_toggle(self, key: int):
        if key == self.toggle_key:
            return
        self.toggle_key = key

        # Recompute KPIs with two-decimal formatting and current preferred wallet's currency
        wallet_id = self._selected_wallet_id()
        w = display_selected_wallet(wallet_id)
        currency = w[2] if len(w) > 2 else "EUR"

        mc = month_comparasion(toggle_state=self.toggle_key, main_wallet=wallet_id)
        if self.spent_value_label is not None:
            spent_amount = mc[1] if len(mc) > 1 else 0.0
            self.spent_value_label.setText(f"{self._fmt2(spent_amount)} {currency}")

        if self.change_value_label is not None:
            try:
                change_pct = float(mc[2])
                change_text = f"{change_pct:.2f}%"
            except Exception:
                change_text = f"{mc[2]}%" if len(mc) > 2 else "0.00%"
            self.change_value_label.setText(change_text)

        # Graph refresh with soft fade
        new_canvas = expenses_in_calendar_qt(toggle_state=self.toggle_key, main_wallet=wallet_id)
        if hasattr(new_canvas, "setSizePolicy"):
            new_canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._fade_in_over_current(new_canvas, duration=220)

    # Theme change: rebuild the graph and repaint halo
    def _refresh_for_theme(self):
        wallet_id = self._selected_wallet_id()
        new_canvas = expenses_in_calendar_qt(toggle_state=self.toggle_key, main_wallet=wallet_id)
        if hasattr(new_canvas, "setSizePolicy"):
            new_canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._fade_in_over_current(new_canvas, duration=160)

        try:
            self.middle_section.update()
        except Exception:
            pass

    def _fade_in_over_current(self, new_widget, duration: int = 220):
        """Swap the canvas via a QStackedLayout so only one is ever visible; fade the new in."""
        old = self.graph_widget

        # Ensure new widget is in the stacked layout but not yet visible
        if hasattr(new_widget, "setSizePolicy"):
            new_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._stack.addWidget(new_widget)

        # Prepare fade-in on the new widget while it is the ONLY visible one
        eff = QGraphicsOpacityEffect(new_widget)
        eff.setOpacity(0.0)
        new_widget.setGraphicsEffect(eff)

        # Make the new widget current (old becomes hidden by the stack)
        self._stack.setCurrentWidget(new_widget)

        anim = QPropertyAnimation(eff, b"opacity", self)
        anim.setDuration(duration)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.InOutCubic)

        def finalize():
            # Remove and delete the old widget (no flicker, it was never visible once we switched)
            if old is not None:
                try:
                    idx = self._stack.indexOf(old)
                    if idx != -1:
                        self._stack.removeWidget(old)
                except Exception:
                    pass
                old.setParent(None)
                old.deleteLater()
            new_widget.setGraphicsEffect(None)
            self.graph_widget = new_widget
            self._fade_anim = None

        anim.finished.connect(finalize)
        self._fade_anim = anim
        anim.start()

    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._fade_widget is not None:
            container = self.graph_layout.parentWidget()
            self._fade_widget.setGeometry(container.rect())

    def showEvent(self, e):
        super().showEvent(e)
        # Defer the DB/Matplotlib build slightly so the first paint is smooth.
        from PySide6.QtCore import QTimer
        QTimer.singleShot(35, self._refresh_from_db)  # ~2 frames delay @60Hz


class HaloPanel(QFrame):
    """Panel that paints a soft theme-aware halo behind its children."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("background: transparent;")

    def paintEvent(self, e):
        # Use active theme colors instead of hard-coded ones
        T = current_theme()

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = self.rect()

        # Left magenta orb (from theme.MAGENTA with themed alpha)
        g1 = QRadialGradient(r.width()*0.35, r.height()*0.42, min(r.width(), r.height())*0.55)
        g1.setColorAt(0.0, QColor(T.MAGENTA.red(), T.MAGENTA.green(), T.MAGENTA.blue(), T.orb_magenta_alpha))
        g1.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.fillRect(r, g1)

        # Right cool blue orb (from theme.ACCENT_BLUE with themed alpha)
        g2 = QRadialGradient(r.width()*0.80, r.height()*0.30, min(r.width(), r.height())*0.70)
        g2.setColorAt(0.0, QColor(T.ACCENT_BLUE.red(), T.ACCENT_BLUE.green(), T.ACCENT_BLUE.blue(), T.orb_blue_alpha))
        g2.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.fillRect(r, g2)
