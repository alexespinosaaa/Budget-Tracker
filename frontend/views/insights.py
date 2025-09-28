# frontend/views/insights.py
from datetime import datetime
from typing import Callable, List, Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFrame, QSizePolicy,
    QLabel, QComboBox, QDialog, QPushButton, QSpacerItem,
    QStackedLayout, QGraphicsOpacityEffect
)
from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve, QTimer
from PySide6.QtGui import QColor, QPainter, QRadialGradient
from shiboken6 import isValid as _is_valid  # guard against double-deletion

# charts (Qt versions)
from backend.high_level.graphs import (
    weekly_exp_trend_qt,
    plot_category_distribution_qt,
    simulate_networth_projection_qt,
    bar_graph_qt,
    over_under_qt,
    cat_volatility_qt,
    budget_flow_qt,
    cat_sum_table_qt,
    cumulative_expenditure_qt,   # <-- replaced goals plot with cumulative expenditure
)
from backend.high_level.analysis import networth_by_currency_table_qt
from backend.crud.profile import get_current_profile

# THEME hooks
from frontend.theme import current_theme, on_theme_changed


# -------------------------
# Soft halo painter (theme-aware)
# -------------------------
class InsightsHaloPanel(QFrame):
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
        g1 = QRadialGradient(r.width() * 0.25, r.height() * 0.35, min(r.width(), r.height()) * 0.65)
        g1.setColorAt(0.0, QColor(t.MAGENTA.red(), t.MAGENTA.green(), t.MAGENTA.blue(),
                                  getattr(t, "orb_magenta_alpha", 160)))
        g1.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.fillRect(r, g1)

        # Right cool orb
        g2 = QRadialGradient(r.width() * 0.80, r.height() * 0.30, min(r.width(), r.height()) * 0.70)
        g2.setColorAt(0.0, QColor(t.ACCENT_BLUE.red(), t.ACCENT_BLUE.green(), t.ACCENT_BLUE.blue(),
                                  getattr(t, "orb_blue_alpha", 110)))
        g2.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.fillRect(r, g2)


# -------------------------
# Tile with stacked body + fade-in swap + instant skeleton
# -------------------------
class ChartTile(QFrame):
    def __init__(
        self,
        title: str,
        mini_factory: Callable[[], QWidget],
        full_factory: Optional[Callable[[], QWidget]] = None,
        min_height: int = 228,
    ):
        super().__init__()
        self.setObjectName("InsightsTile")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        if min_height:
            self.setMinimumHeight(min_height)

        self._mini_factory = mini_factory
        self._full_factory = full_factory if full_factory else mini_factory
        self._current_body: QWidget | None = None
        self._last_key: Optional[str] = None  # to avoid redundant rebuilds
        self._anim: Optional[QPropertyAnimation] = None  # hold ref to avoid GC / allow cancellation

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 12)
        root.setSpacing(8)

        header = QFrame()
        hl = QHBoxLayout(header)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(6)

        title_lbl = QLabel(title)
        title_lbl.setObjectName("TileTitle")
        hl.addWidget(title_lbl)
        hl.addStretch(1)

        open_btn = QPushButton("Open")
        open_btn.setObjectName("OpenBtn")
        open_btn.clicked.connect(self.open_modal)
        hl.addWidget(open_btn)

        root.addWidget(header)

        # Body: stacked to ensure only one child is visible (no flicker)
        self._body_container = QFrame()
        self._stack = QStackedLayout(self._body_container)
        self._stack.setContentsMargins(0, 0, 0, 0)
        self._stack.setStackingMode(QStackedLayout.StackOne)
        root.addWidget(self._body_container, 1)

        # Theme QSS now + keep in sync
        self._apply_theme_qss(current_theme())
        on_theme_changed(self._apply_theme_qss)

        # Put a very light skeleton immediately (no heavy work)
        self._install_skeleton()

    # ---------- visual/theming ----------
    def _apply_theme_qss(self, theme):
        text = theme.TEXT
        mag  = theme.MAGENTA

        if getattr(theme, "variant", "dark") == "light":
            card_bg   = "rgba(255,255,255,0.75)"
            card_bd   = "rgba(0,0,0,0.10)"
            btn_bg    = "rgba(0,0,0,0.06)"
            btn_bg_h  = "rgba(0,0,0,0.12)"
            gridline  = "rgba(0,0,0,0.10)"
            hdr_bg    = "rgba(0,0,0,0.06)"
            sel_bg    = f"rgba({mag.red()},{mag.green()},{mag.blue()},0.20)"
            alt_bg    = "rgba(0,0,0,0.02)"
            sk_bg1    = "rgba(0,0,0,0.06)"
            sk_bg2    = "rgba(0,0,0,0.10)"
        else:
            card_bg   = "rgba(12,14,22,0.50)"
            card_bd   = "rgba(255,255,255,0.08)"
            btn_bg    = "rgba(255,255,255,0.06)"
            btn_bg_h  = "rgba(255,255,255,0.12)"
            gridline  = "rgba(255,255,255,0.06)"
            hdr_bg    = "rgba(255,255,255,0.06)"
            sel_bg    = f"rgba({mag.red()},{mag.green()},{mag.blue()},0.35)"
            alt_bg    = "rgba(255,255,255,0.02)"
            sk_bg1    = "rgba(255,255,255,0.06)"
            sk_bg2    = "rgba(255,255,255,0.10)"

        qss = f"""
            QFrame#InsightsTile {{
                background: {card_bg};
                border: 1px solid {card_bd};
                border-radius: 14px;
            }}
            QFrame#InsightsTile QLabel#TileTitle {{
                font-size: 13px; font-weight: 700; color: {text};
                letter-spacing: 0.2px;
            }}
            QFrame#InsightsTile QPushButton#OpenBtn {{
                border: 1px solid {card_bd};
                background: {btn_bg};
                color: {text}; font-size: 11px; padding: 4px 10px; border-radius: 8px;
            }}
            QFrame#InsightsTile QPushButton#OpenBtn:hover {{
                background: {btn_bg_h};
            }}

            /* Tables rendered inside tiles (kept functionally identical) */
            QFrame#InsightsTile QTableWidget {{
                background: rgba(12,14,22,0.40);
                color: {text};
                gridline-color: {gridline};
                border: 1px solid {gridline};
                selection-background-color: {sel_bg};
                selection-color: {text};
                alternate-background-color: {alt_bg};
            }}
            QFrame#InsightsTile QHeaderView::section {{
                background: {hdr_bg};
                color: {text};
                border: none;
                padding: 6px 8px;
                font-weight: 600;
            }}
            QFrame#InsightsTile QTableCornerButton::section {{ background: transparent; border: none; }}

            /* skeleton look */
            QFrame[skeleton="true"] {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {sk_bg1}, stop:0.5 {sk_bg2}, stop:1 {sk_bg1});
                border-radius: 10px;
                min-height: 160px;
            }}
        """
        self.setStyleSheet(qss)

    # ---------- skeleton / lightweight placeholder ----------
    def _install_skeleton(self):
        sk = QFrame()
        sk.setProperty("skeleton", True)
        sk.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # no layout/children -> zero cost
        self._stack.addWidget(sk)
        self._stack.setCurrentWidget(sk)
        self._current_body = sk

        # quick pulse so it feels alive without work
        eff = QGraphicsOpacityEffect(sk)
        eff.setOpacity(0.85)
        sk.setGraphicsEffect(eff)
        anim = QPropertyAnimation(eff, b"opacity", sk)
        anim.setDuration(800)
        anim.setStartValue(0.65)
        anim.setEndValue(0.95)
        anim.setEasingCurve(QEasingCurve.InOutSine)
        anim.setLoopCount(-1)
        anim.start()

    # ---------- WebEngine transparency ----------
    def _glassify_webviews(self, root_widget: QWidget | None):
        if root_widget is None:
            return
        try:
            from PySide6.QtWebEngineWidgets import QWebEngineView
        except Exception:
            QWebEngineView = None  # type: ignore
        if not QWebEngineView:
            return

        def patch(view):
            try:
                view.setAttribute(Qt.WA_TranslucentBackground, True)
                view.setStyleSheet("background: transparent;")
                if hasattr(view, "page"):
                    page = view.page()
                    try:
                        page.setBackgroundColor(Qt.transparent)
                    except Exception:
                        pass
                    try:
                        page.runJavaScript("""
                            try {
                                document.documentElement.style.background='transparent';
                                document.body.style.background='transparent';
                                const s=document.createElement('style');
                                s.innerHTML = `
                                  .plotly .main-svg{ background: transparent !important; }
                                  .plot-container, .svg-container{ background: transparent !important; }
                                `;
                                document.head.appendChild(s);
                            } catch(e){}
                        """)
                    except Exception:
                        pass
            except Exception:
                pass

        try:
            for v in root_widget.findChildren(QWebEngineView):
                patch(v)
                try:
                    v.loadFinished.connect(lambda _ok, vv=v: patch(vv))
                except Exception:
                    pass
        except Exception:
            pass

    # ---------- swap helpers ----------
    def _swap_body_fade(self, new_widget: QWidget, duration: int = 120):
        """
        Swap the tile body with a fade-in animation, guarding against
        overlapping animations and double-deletion of the old widget.
        """
        old = self._current_body

        # Install new widget and mark it current *before* the animation.
        self._stack.addWidget(new_widget)
        self._stack.setCurrentWidget(new_widget)
        self._current_body = new_widget

        # Prepare fade-in on the new widget
        eff = QGraphicsOpacityEffect(new_widget)
        eff.setOpacity(0.0)
        new_widget.setGraphicsEffect(eff)

        # Cancel any previous in-flight animation to avoid multiple finalizers
        try:
            if self._anim:
                self._anim.stop()
        except Exception:
            pass

        anim = QPropertyAnimation(eff, b"opacity", self)
        anim.setDuration(duration)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.InOutCubic)
        self._anim = anim  # keep a reference

        def finalize():
            # Safely remove and delete the previous widget if it's still valid
            if old is not None and _is_valid(old):
                try:
                    idx = self._stack.indexOf(old)
                    if idx != -1:
                        self._stack.removeWidget(old)
                except Exception:
                    pass
                try:
                    if _is_valid(old):
                        old.deleteLater()
                except Exception:
                    pass

            # Drop the effect from the new widget if it's still alive
            try:
                if _is_valid(new_widget):
                    new_widget.setGraphicsEffect(None)
            except Exception:
                pass

        anim.finished.connect(finalize)
        anim.start()

    # ---------- public build API ----------
    def refresh(self, state_key: Optional[str] = None):
        """Build mini widget and swap with a smooth fade, unless state is unchanged."""
        if state_key is not None and self._last_key == state_key and self._current_body is not None:
            return

        try:
            w = self._mini_factory()
        except Exception as e:
            w = QLabel(f"Failed to render: {e}")
            w.setStyleSheet("color:#ffbbbb;")
            w.setWordWrap(True)

        self._glassify_webviews(w)

        if self._current_body is None:
            self._stack.addWidget(w)
            self._stack.setCurrentWidget(w)
            self._current_body = w
        else:
            self._swap_body_fade(w, duration=120)

        self._last_key = state_key or self._last_key

    def open_modal(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Preview")
        dlg.resize(980, 640)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        try:
            big = self._full_factory()
        except Exception as e:
            big = QLabel(f"Failed to render: {e}")
            big.setStyleSheet("color:#a00;")
            big.setWordWrap(True)

        lay.addWidget(big, 1)
        self._glassify_webviews(big)

        close_row = QHBoxLayout()
        close_row.addStretch(1)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dlg.accept)
        close_row.addWidget(close_btn)
        lay.addLayout(close_row)

        dlg.exec()


# -------------------------
# Insights Page
# -------------------------
class InsightsPage(QWidget):
    timeframeChanged = Signal(str)
    currencyChanged = Signal(str)  # kept for compatibility (no UI control now)

    def __init__(self, initial_toggle_key: int = 1):
        super().__init__()
        self.toggle_key = initial_toggle_key
        self._tiles: List[ChartTile] = []

        # NEW: nonce that forces rebuilds for data/theme/show events
        self._refresh_nonce = 0

        # Refresh queue state (non-blocking)
        self._refresh_pending = False
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(False)
        self._refresh_timer.timeout.connect(self._refresh_tick)
        self._refresh_batch_size = 3   # tiles per tick (fast but smooth)
        self._refresh_idx = 0

        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setMinimumSize(1000, 700)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Root layout (transparent gutters + halo center)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.left_section = QFrame();  self.left_section.setStyleSheet("background: transparent;")
        self.middle_section = InsightsHaloPanel()
        self.right_section = QFrame(); self.right_section.setStyleSheet("background: transparent;")

        self._populate_middle(self.middle_section)

        row_layout = QHBoxLayout()
        row_layout.setContentsMargins(16, 16, 16, 16)
        row_layout.setSpacing(16)
        row_layout.addWidget(self.left_section, 2)
        row_layout.addWidget(self.middle_section, 6)
        row_layout.addWidget(self.right_section, 2)
        main_layout.addLayout(row_layout)

        # Apply page-level theme QSS now + keep in sync
        self._apply_theme_qss(current_theme())
        on_theme_changed(self._apply_theme_qss)
        on_theme_changed(lambda *_: self.request_refresh("theme"))

        self._build_tiles()

    # ---------- Middle scaffold ----------
    def _populate_middle(self, parent: QFrame):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(24, 84, 24, 24)
        layout.setSpacing(12)

        # Controls row (only timeframe; right-aligned)
        controls_row = QHBoxLayout()
        controls_row.setContentsMargins(0, 0, 0, 0)
        controls_row.setSpacing(12)
        layout.addLayout(controls_row)
        controls_row.addStretch(1)

        def make_combo(items: list[str]) -> QComboBox:
            combo = QComboBox()
            combo.setObjectName("InsightsTimeframe")
            combo.setEditable(True)
            combo.lineEdit().setReadOnly(True)
            combo.lineEdit().setAlignment(Qt.AlignCenter)
            combo.addItems(items)
            combo.setCurrentIndex(0)
            combo.setFixedWidth(144)
            combo.setFixedHeight(32)
            combo.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            return combo

        self.timeframe_control = QWidget()
        tf_v = QVBoxLayout(self.timeframe_control)
        tf_v.setContentsMargins(0, 0, 0, 0)
        tf_v.setSpacing(6)
        tf_combo = make_combo(["This month", "6 months", "This year"])
        self.timeframe_control.setFixedWidth(144)

        tf_label = QLabel("Timeframe")
        tf_label.setObjectName("InsightsTFLabel")
        tf_label.setAlignment(Qt.AlignCenter)

        tf_v.addWidget(tf_label, 0, Qt.AlignHCenter)
        tf_v.addWidget(tf_combo, 0, Qt.AlignHCenter)

        self.timeframe_control.combo = tf_combo
        self.timeframe_control.combo.currentTextChanged.connect(self._on_timeframe_changed)

        controls_row.addWidget(self.timeframe_control, 0, Qt.AlignRight)

        # Tiles grid (glass cards)
        self.grid = QGridLayout()
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(12)
        self.grid.setVerticalSpacing(12)
        layout.addLayout(self.grid, 1)

    # ---------- Profile helpers ----------
    def _profile_monthly_budget(self) -> float:
        try:
            prof = get_current_profile() or {}
            val = prof.get("monthly_budget", 0.0)
            return float(val) if val is not None else 0.0
        except Exception:
            return 0.0

    def _profile_skip_months(self) -> list[str]:
        try:
            prof = get_current_profile() or {}
            sm = prof.get("skip_months")
            if isinstance(sm, list):
                return [str(x) for x in sm]
            return []
        except Exception:
            return []

    # ---------- Build & refresh ----------
    def _build_tiles(self):
        self._tiles.clear()

        def mini(canvas: QWidget, w=4.2, h=3.0, spine_color="#D0D7EA"):
            try:
                fig = getattr(canvas, "figure", None)
                if fig is None:
                    return canvas
                fig.set_size_inches(w, h)
                fig.patch.set_alpha(0.0)
                for ax in fig.get_axes():
                    ax.set_title("")
                    leg = ax.get_legend()
                    if leg:
                        leg.remove()
                    for s in ax.spines.values():
                        s.set_visible(True)
                        s.set_linewidth(0.8)
                        s.set_color(spine_color)
                    ax.grid(False)
                    ax.set_xlabel("")
                    ax.set_ylabel("")
                    ax.tick_params(axis="x", which="both", labelbottom=False, length=3, width=0.8, color=spine_color)
                    ax.tick_params(axis="y", which="both", labelleft=False,  length=3, width=0.8, color=spine_color)
                    for t in list(ax.texts):
                        t.set_visible(False)
                    try:
                        if ax.name != "polar":
                            ax.set_aspect("auto")
                    except Exception:
                        pass
                fig.subplots_adjust(left=0.06, right=0.94, top=0.90, bottom=0.10)
            except Exception:
                pass
            return canvas

        # Row 1
        t1 = ChartTile(
            "Spending Distribution",
            mini_factory=lambda: mini(self._plot_distribution_for_timeframe())),
        t1 = t1[0]
        t1._full_factory = lambda: self._plot_distribution_for_timeframe()

        t2 = ChartTile(
            "Expenses by Category",
            mini_factory=lambda: self._cat_sum_table_for_timeframe(),
            full_factory=lambda: self._cat_sum_table_for_timeframe(),
        )
        t3 = ChartTile(
            "Weekly Expenses",
            mini_factory=lambda: mini(weekly_exp_trend_qt(
                n=self._weeks_for_timeframe(), toggle_state=self.toggle_key)),
            full_factory=lambda: weekly_exp_trend_qt(
                n=self._weeks_for_timeframe(), toggle_state=self.toggle_key),
        )

        # Networth Projection (uses profile budget & skipped months)
        def networth_proj_mini():
            return mini(simulate_networth_projection_qt(
                n_months=self._months_for_timeframe(),
                avg_income_per_month=self._profile_monthly_budget(),
                exclude_months=self._profile_skip_months(),
                target_currency=self.current_currency(),
            ))

        def networth_proj_full():
            return simulate_networth_projection_qt(
                n_months=self._months_for_timeframe(),
                avg_income_per_month=self._profile_monthly_budget(),
                exclude_months=self._profile_skip_months(),
                target_currency=self.current_currency(),
            )
        t4 = ChartTile("Networth Projection", mini_factory=networth_proj_mini, full_factory=networth_proj_full)

        # Budget Flow
        def budget_flow_mini():
            try:
                return budget_flow_qt(
                    toggle_state=self.toggle_key,
                    timeframe=self._map_timeframe_for_budgetflow(),
                    show_title=False,
                    monthly_budget=self._profile_monthly_budget(),
                )
            except TypeError:
                return budget_flow_qt(
                    toggle_state=self.toggle_key,
                    timeframe=self._map_timeframe_for_budgetflow(),
                    show_title=False,
                )

        def budget_flow_full():
            try:
                return budget_flow_qt(
                    toggle_state=self.toggle_key,
                    timeframe=self._map_timeframe_for_budgetflow(),
                    show_title=True,
                    monthly_budget=self._profile_monthly_budget(),
                )
            except TypeError:
                return budget_flow_qt(
                    toggle_state=self.toggle_key,
                    timeframe=self._map_timeframe_for_budgetflow(),
                    show_title=True,
                )
        t5 = ChartTile("Budget Flow", mini_factory=budget_flow_mini, full_factory=budget_flow_full)

        t6 = ChartTile(
            "Total Networth",
            mini_factory=lambda: networth_by_currency_table_qt(),
            full_factory=lambda: networth_by_currency_table_qt(),
        )
        t7 = ChartTile(
            "Limit vs Spent",
            mini_factory=lambda: mini(bar_graph_qt(
                toggle_state=self.toggle_key, month_key=self._month_key_for_timeframe())),
            full_factory=lambda: bar_graph_qt(
                toggle_state=self.toggle_key, month_key=self._month_key_for_timeframe()),
        )
        t8 = ChartTile(
            "Times Over Limit",
            mini_factory=lambda: mini(over_under_qt(toggle_state=self.toggle_key)),
            full_factory=lambda: over_under_qt(toggle_state=self.toggle_key),
        )
        t9 = ChartTile(
            "Category Volatility",
            mini_factory=lambda: mini(cat_volatility_qt(toggle_state=self.toggle_key)),
            full_factory=lambda: cat_volatility_qt(toggle_state=self.toggle_key),
        )

        # Cumulative Expenditure (overview minimal vs full)
        def cumexp_mini():
            return cumulative_expenditure_qt(
                timeframe=self._map_timeframe_for_cumulative(),
                toggle_state=self.toggle_key,
                skip_months=self._profile_skip_months(),
                target_currency=self.current_currency(),
                minimal=True,
            )

        def cumexp_full():
            return cumulative_expenditure_qt(
                timeframe=self._map_timeframe_for_cumulative(),
                toggle_state=self.toggle_key,
                skip_months=self._profile_skip_months(),
                target_currency=self.current_currency(),
                minimal=False,
            )
        t10 = ChartTile("Cumulative Expenditure", mini_factory=cumexp_mini, full_factory=cumexp_full)

        tiles = [t1, t2, t3, t4, t5, t6, t7, t8, t9, t10]
        self._tiles.extend(tiles)

        for idx, tile in enumerate(tiles):
            r = 0 if idx < 5 else 1
            c = idx if idx < 5 else idx - 5
            self.grid.addWidget(tile, r, c)

        self.grid.addItem(QSpacerItem(0, 0, QSizePolicy.Minimum, QSizePolicy.Expanding), 2, 0, 1, 5)

    def _plot_distribution_for_timeframe(self) -> QWidget:
        tf_key = self._map_timeframe_for_distribution()
        month_str = self._current_month_str()
        try:
            return plot_category_distribution_qt(
                month=month_str,
                timeframe=tf_key,
                toggle_state=self.toggle_key
            )
        except TypeError:
            return plot_category_distribution_qt(
                month=month_str,
                toggle_state=self.toggle_key
            )

    def _cat_sum_table_for_timeframe(self) -> QWidget:
        tf_key = self._map_timeframe_for_distribution()
        try:
            return cat_sum_table_qt(timeframe=tf_key, toggle_state=self.toggle_key)
        except TypeError:
            return cat_sum_table_qt()

    # ---------- State key & refresh queue ----------
    def _state_key(self) -> str:
        tf = self.current_timeframe()
        bud = f"{self._profile_monthly_budget():.2f}"
        skn = f"{len(self._profile_skip_months())}"
        togg = str(self.toggle_key)
        mstr = self._current_month_str()
        # UPDATED: include nonce so data/theme/show triggers force rebuilds
        nonce = str(self._refresh_nonce)
        return "|".join([togg, tf, bud, skn, mstr, nonce])

    # In class InsightsPage
    def request_refresh(self, reason: str = ""):
        """
        Coalesce triggers; schedule staggered build.
        UPDATED: bump nonce for reasons that imply data/theme changes or page (re)show.
        """
        if reason in ("data", "theme", "show"):
            self._refresh_nonce += 1  # force new state_key so tiles rebuild

        if not self._refresh_pending:
            self._refresh_pending = True
            QTimer.singleShot(16, self._start_refresh_queue)

    def _start_refresh_queue(self):
        self._refresh_pending = False
        if not self.isVisible():
            return
        self._refresh_idx = 0
        self._refresh_timer.setInterval(10)
        self._refresh_timer.start()

    def _refresh_tick(self):
        n = len(self._tiles)
        if self._refresh_idx >= n:
            self._refresh_timer.stop()
            return

        key = self._state_key()
        end = min(self._refresh_idx + self._refresh_batch_size, n)
        for i in range(self._refresh_idx, end):
            self._tiles[i].refresh(state_key=key)
        self._refresh_idx = end

    # ---------- Public API ----------
    def apply_toggle(self, key: int):
        if key == self.toggle_key:
            return
        self.toggle_key = key
        self.request_refresh("toggle")

    def current_timeframe(self) -> str:
        return self.timeframe_control.combo.currentText()

    def current_currency(self) -> str:
        # Currency selector removed; keep method for compatibility
        return "EUR"

    # ---------- Internal helpers ----------
    def _on_timeframe_changed(self, text: str):
        self.timeframeChanged.emit(text)
        self.request_refresh("timeframe")

    def _current_month_str(self) -> str:
        now = datetime.today()
        return f"{now.month:02d}-{now.year}"

    def _weeks_for_timeframe(self) -> int:
        tf = self.current_timeframe().lower()
        if "year" in tf: return 52
        if "6"    in tf: return 26
        return 12

    def _months_for_timeframe(self) -> int:
        tf = self.current_timeframe().lower()
        if "year" in tf: return 12
        if "6"    in tf: return 6
        return 3

    def _map_timeframe_for_budgetflow(self) -> str:
        tf = self.current_timeframe().lower()
        if "year" in tf:
            return "year"
        if "6" in tf:
            return "6m"
        return "month"

    def _map_timeframe_for_distribution(self) -> str:
        tf = self.current_timeframe().lower()
        if "year" in tf:
            return "year"
        if "6" in tf:
            return "6m"
        return "month"

    def _map_timeframe_for_cumulative(self) -> str:
        """Map UI text to cumulative_expenditure_qt timeframe keys."""
        tf = self.current_timeframe().lower()
        if "year" in tf:
            return "this_year"
        if "6" in tf:
            return "six_months"
        return "this_month"

    def _month_key_for_timeframe(self) -> int:
        return 0  # current month for now

    def _placeholder_box(self, text: str) -> QWidget:
        box = QFrame()
        box.setStyleSheet("background:#fafafa; border:1px dashed #ddd; border-radius:8px;")
        v = QVBoxLayout(box)
        v.setContentsMargins(10, 10, 10, 10)
        lbl = QLabel(text)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("color:#666; font-size:12px;")
        v.addWidget(lbl, 1)
        return box

    # ===================== THEME QSS (page-level) =====================
    def _apply_theme_qss(self, theme):
        text = theme.TEXT
        mag  = theme.MAGENTA

        def rgba(qc, a: float) -> str:
            return f"rgba({qc.red()},{qc.green()},{qc.blue()},{a})"

        if getattr(theme, "variant", "dark") == "light":
            label_tx = text
            input_bg = "rgba(255,255,255,0.75)"
            border   = "rgba(0,0,0,0.10)"
            popup_bg = "rgba(255,255,255,0.95)"
            sel_bg   = rgba(mag, 0.20)
        else:
            label_tx = text
            input_bg = "rgba(6,8,14,0.66)"
            border   = "rgba(255,255,255,0.10)"
            popup_bg = "rgba(12,14,22,0.95)"
            sel_bg   = rgba(mag, 0.35)

        qss = f"""
            QLabel#InsightsTFLabel {{
                font-size:12px; font-weight:600; color:{label_tx};
            }}

            /* Timeframe selector */
            QComboBox#InsightsTimeframe {{
                background: {input_bg};
                color: {label_tx};
                border: 1px solid {border};
                border-radius: 10px;
                padding: 2px 8px;
                min-height: 32px;
                max-height: 32px;
            }}
            QComboBox#InsightsTimeframe:focus {{
                border: 1px solid {theme.MAGENTA.name()};
            }}
            QComboBox#InsightsTimeframe::drop-down {{ width: 22px; border: none; }}
            QComboBox#InsightsTimeframe QAbstractItemView {{
                background: {popup_bg};
                color: {label_tx};
                selection-background-color: {sel_bg};
                border: 1px solid {border};
            }}
        """
        self.setStyleSheet(qss)

    # ===================== LIFECYCLE =====================
    def showEvent(self, e):
        super().showEvent(e)
        # Like Overview: defer heavy work so the window paints first
        QTimer.singleShot(35, lambda: self.request_refresh("show"))

    def hideEvent(self, e):
        # Stop in-flight staggered work to keep navigation snappy
        try:
            self._refresh_timer.stop()
        except Exception:
            pass
        super().hideEvent(e)
