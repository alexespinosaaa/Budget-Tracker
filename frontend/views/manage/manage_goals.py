# frontend/views/manage/manage_goals.py
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QSizePolicy,
    QPushButton, QLabel, QButtonGroup,
    QTableWidget, QTableWidgetItem, QHeaderView, QDialog, QStackedWidget,
    QLineEdit, QDoubleSpinBox, QComboBox, QDateEdit, QMessageBox,
    QStackedLayout, QGraphicsOpacityEffect
)
from PySide6.QtCore import Qt, Signal, QDate, QEvent, QLocale, QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QColor, QPainter, QRadialGradient

# Data (do not modify backend; keep the original import spelling)
from backend.high_level.analysis import ordeBy as goals_order_by  # returns rows from goal table

# Theme API
from frontend.theme import current_theme, on_theme_changed


# ---------- Helper: action button that supports double-click ----------
class ActionButton(QPushButton):
    """Checkable button that emits doubleClicked."""
    doubleClicked = Signal()

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.setCheckable(True)

    def mouseDoubleClickEvent(self, e):
        self.doubleClicked.emit()
        super().mouseDoubleClickEvent(e)


class ManageGoalsPage(QWidget):
    # Navigate to sibling manage pages
    navigateExpenses   = Signal()
    navigateWallets    = Signal()
    navigateCategories = Signal()

    def __init__(self, initial_toggle_key: int = 1):
        super().__init__()
        self.toggle_key = initial_toggle_key
        self._boxes_by_page: dict[int, list[QFrame]] = {}  # page-id -> boxes
        self._armed_action = None  # "add" | "complete" | "edit" | "remove"
        self._add_goal_name_cleared = False

        # labels to recolor on theme change
        self._themed_labels: list[QLabel] = []

        # Panel A summary (smooth swaps, like wallets)
        self._summary_stack: QStackedLayout | None = None
        self._summary_table: QTableWidget | None = None
        self._fade_anim = None

        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setMinimumSize(1000, 700)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # ---------- Root layout (transparent gutters + halo center) ----------
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.left_section   = QFrame(); self.left_section.setStyleSheet("background: transparent;")
        self.middle_section = GoalsHaloPanel()   # paints soft magenta/blue orbs
        self.right_section  = QFrame(); self.right_section.setStyleSheet("background: transparent;")

        self._populate_middle(self.middle_section)

        row_layout = QHBoxLayout()
        row_layout.setContentsMargins(16, 16, 16, 16)
        row_layout.setSpacing(16)
        row_layout.addWidget(self.left_section, 2)
        row_layout.addWidget(self.middle_section, 6)
        row_layout.addWidget(self.right_section, 2)
        main_layout.addLayout(row_layout)

        # Build the pages’ inputs now that boxes exist
        self._build_add_goal_inputs()
        self._build_complete_goal_inputs()
        self._build_edit_goal_inputs()
        self._build_remove_goal_inputs()

        # Initial theme pass + subscribe
        self._apply_theme_colors(current_theme())
        on_theme_changed(self._apply_theme_colors)

    # ---------- Middle content ----------
    def _populate_middle(self, parent: QFrame):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(24, 84, 24, 24)  # tighter rhythm like other pages
        layout.setSpacing(12)

        # === TOP: big nav chips (glass lozenges) ===
        top_buttons_row = QHBoxLayout()
        top_buttons_row.setContentsMargins(0, 0, 0, 0)
        top_buttons_row.setSpacing(12)
        layout.addLayout(top_buttons_row)

        def make_primary_btn(text: str) -> QPushButton:
            b = QPushButton(text)
            b.setCheckable(True)
            b.setMinimumHeight(40)  # compact
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            return b  # styled by _apply_theme_colors
        self.btn_nav_expenses   = make_primary_btn("Expenses")
        self.btn_nav_wallets    = make_primary_btn("Wallets")
        self.btn_nav_categories = make_primary_btn("Categories")
        self.btn_nav_goals      = make_primary_btn("Goals")

        nav_group = QButtonGroup(self)
        nav_group.setExclusive(True)
        for b in (self.btn_nav_expenses, self.btn_nav_wallets, self.btn_nav_categories, self.btn_nav_goals):
            nav_group.addButton(b)
        self.btn_nav_goals.setChecked(True)

        self.btn_nav_expenses.clicked.connect(lambda *_: self.navigateExpenses.emit())
        self.btn_nav_wallets.clicked.connect(lambda *_: self.navigateWallets.emit())
        self.btn_nav_categories.clicked.connect(lambda *_: self.navigateCategories.emit())

        top_buttons_row.addWidget(self.btn_nav_expenses,   1)
        top_buttons_row.addWidget(self.btn_nav_wallets,    1)
        top_buttons_row.addWidget(self.btn_nav_categories, 1)
        top_buttons_row.addWidget(self.btn_nav_goals,      1)

        # === SECOND: goal action toggles (glass) ===
        actions_row = QHBoxLayout()
        actions_row.setContentsMargins(0, 0, 0, 0)
        actions_row.setSpacing(12)
        layout.addLayout(actions_row)
        actions_row.addStretch(1)

        def make_toggle(text: str) -> ActionButton:
            t = ActionButton(text)
            t.setMinimumHeight(30)
            return t  # styled by _apply_theme_colors
        # Order: Add → Complete → Edit → Remove
        self.btn_add_goal      = make_toggle("Add goal")
        self.btn_complete_goal = make_toggle("Complete goal")
        self.btn_edit_goal     = make_toggle("Edit goal")
        self.btn_remove_goal   = make_toggle("Remove goal")

        actions_row.addWidget(self.btn_add_goal,      0, Qt.AlignRight)
        actions_row.addWidget(self.btn_complete_goal, 0, Qt.AlignRight)
        actions_row.addWidget(self.btn_edit_goal,     0, Qt.AlignRight)
        actions_row.addWidget(self.btn_remove_goal,   0, Qt.AlignRight)

        self.actions_group = QButtonGroup(self)
        self.actions_group.setExclusive(True)
        for b in (self.btn_add_goal, self.btn_complete_goal, self.btn_edit_goal, self.btn_remove_goal):
            self.actions_group.addButton(b)

        # === THIRD: two glass panels ===
        panels_row = QHBoxLayout()
        panels_row.setContentsMargins(0, 0, 0, 0)
        panels_row.setSpacing(16)
        layout.addLayout(panels_row, 1)

        # Panel A — Goals summary (stacked for smooth swaps like wallets)
        self.panelA = QFrame()
        self.panelA.setProperty("kind", "glassDeep")
        self.panelA.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        vA = QVBoxLayout(self.panelA)
        vA.setContentsMargins(16, 12, 16, 12)
        vA.setSpacing(8)

        lblA = QLabel("Goals")
        self._themed_labels.append(lblA)
        vA.addWidget(lblA)

        summary_area = QFrame()
        self._summary_stack = QStackedLayout(summary_area)
        self._summary_stack.setContentsMargins(0, 0, 0, 0)

        # First mount: empty table, then fade in real data on showEvent
        self._summary_table = self._make_goals_table_widget([])
        self._summary_stack.addWidget(self._summary_table)

        vA.addWidget(summary_area, 1)

        # Panel B — stacked pages with compact, top-aligned mini boxes
        self.panelB = QFrame()
        self.panelB.setProperty("kind", "glassDeep")
        self.panelB.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        vB = QVBoxLayout(self.panelB)
        vB.setContentsMargins(12, 12, 12, 12)
        vB.setSpacing(0)

        self.panelBStack = QStackedWidget(self.panelB)
        self.panelBStack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        vB.addWidget(self.panelBStack)

        # Build per-action pages (top-aligned boxes; no absolute geometry)
        self.page_add_goal      = self._build_action_page(6)
        self.page_complete_goal = self._build_action_page(2)
        self.page_edit_goal     = self._build_action_page(6)
        self.page_remove_goal   = self._build_action_page(1)

        self.panelBStack.addWidget(self.page_add_goal)       # 0
        self.panelBStack.addWidget(self.page_complete_goal)  # 1
        self.panelBStack.addWidget(self.page_edit_goal)      # 2
        self.panelBStack.addWidget(self.page_remove_goal)    # 3

        # Default selection (armed)
        self.panelBStack.setCurrentIndex(0)
        self.btn_add_goal.setChecked(True)
        self._armed_action = "add"

        # Arm-or-fire wiring
        self.btn_add_goal.clicked.connect(     lambda *_: self._arm_or_fire("add",      0))
        self.btn_complete_goal.clicked.connect(lambda *_: self._arm_or_fire("complete", 1))
        self.btn_edit_goal.clicked.connect(    lambda *_: self._arm_or_fire("edit",     2))
        self.btn_remove_goal.clicked.connect(  lambda *_: self._arm_or_fire("remove",   3))

        self.btn_add_goal.doubleClicked.connect(     lambda *_: self._execute_action("add"))
        self.btn_complete_goal.doubleClicked.connect(lambda *_: self._execute_action("complete"))
        self.btn_edit_goal.doubleClicked.connect(    lambda *_: self._execute_action("edit"))
        self.btn_remove_goal.doubleClicked.connect(  lambda *_: self._execute_action("remove"))

        panels_row.addWidget(self.panelA, 1)
        panels_row.addWidget(self.panelB, 1)

    # ---------- Compact glass mini boxes (TOP-ALIGNED) ----------
    def _build_action_page(self, box_count: int) -> QWidget:
        """
        Create a stacked page holding `box_count` compact glass boxes.
        Boxes are top-aligned with 12px gaps; leftover space sits at the bottom.
        """
        page = QWidget()
        page.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(12)

        boxes: list[QFrame] = []
        for _ in range(box_count):
            b = QFrame()
            b.setObjectName("MiniBox")
            b.setProperty("kind", "glass")
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            b.setMinimumHeight(72)  # compact height
            v.addWidget(b, 0)       # do NOT stretch; keeps content at the top
            boxes.append(b)
        v.addStretch(1)              # leftover space at the bottom
        self._boxes_by_page[id(page)] = boxes
        return page

    def _box_layout(self, box: QFrame) -> QVBoxLayout:
        lay = QVBoxLayout(box)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(6)
        return lay

    def _labeled(self, parent_lay: QVBoxLayout, title: str, widget: QWidget):
        lbl = QLabel(title)
        self._themed_labels.append(lbl)
        parent_lay.addWidget(lbl)

        # Sizing for inputs (styling applied in _apply_theme_colors):
        if isinstance(widget, (QLineEdit, QComboBox, QDateEdit, QDoubleSpinBox)):
            widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            widget.setMinimumHeight(32)
            widget.setMaximumHeight(36)

        parent_lay.addWidget(widget, 0)

    # ---------- Arm & Fire ----------
    def _arm_or_fire(self, action_key: str, stack_index: int):
        """First click arms (switches stack); second click/double-click executes."""
        if self._armed_action != action_key:
            self.panelBStack.setCurrentIndex(stack_index)
            self._armed_action = action_key
        else:
            self._execute_action(action_key)

    def _execute_action(self, action_key: str):
        if action_key == "add":
            # ---- Collect & validate inputs ----
            name = (self.add_goal_name.text() or "").strip() if hasattr(self, "add_goal_name") else ""
            if not name or name == "e.g. shoes":
                QMessageBox.warning(self, "Missing name", "Please enter a goal name.")
                return

            to_reach = float(self.add_goal_to_reach.value()) if hasattr(self, "add_goal_to_reach") else 0.0
            if to_reach <= 0.0:
                QMessageBox.warning(self, "Invalid amount", "Amount to reach must be greater than 0.")
                return

            reached = float(self.add_goal_reached.value()) if hasattr(self, "add_goal_reached") else 0.0

            category_id = (
                self.add_goal_category.currentData(Qt.UserRole)
                if hasattr(self, "add_goal_category") else None
            )
            category_id = int(category_id) if category_id is not None else None

            currency = (
                self.add_goal_currency.currentData(Qt.UserRole)
                if hasattr(self, "add_goal_currency") else "EUR"
            )
            currency = "EUR" if not currency else str(currency)

            start_qdate = self.add_goal_start_date.date() if hasattr(self, "add_goal_start_date") else None
            start_date = start_qdate.toString("yyyy-MM-dd") if start_qdate else None

            # ---- Call backend and refresh UI ----
            self._add_goal_backend(name, to_reach, reached, category_id, currency, start_date)

        elif action_key == "complete":
            if not hasattr(self, "complete_goal_select") or not hasattr(self, "complete_goal_wallet"):
                QMessageBox.warning(self, "Missing inputs", "Goal/Wallet selectors are not available.")
                return

            goal_id = self.complete_goal_select.currentData(Qt.UserRole)
            wallet_id = self.complete_goal_wallet.currentData(Qt.UserRole)

            if goal_id is None:
                QMessageBox.warning(self, "No goal selected", "Please choose a goal to complete.")
                return
            if wallet_id is None:
                QMessageBox.warning(self, "No wallet selected", "Please choose a wallet.")
                return

            goal_id = int(goal_id)
            wallet_id = int(wallet_id)

            # For messaging
            goal_name = self.complete_goal_select.currentText().strip()
            wallet_name = self.complete_goal_wallet.currentText().strip()

            wallet_currency = ""
            try:
                rows = self._fetch_wallets()  # (id, name, amount, currency, ...)
                for r in rows:
                    if r[0] == wallet_id:
                        wallet_currency = "" if r[3] is None else str(r[3])
                        break
            except Exception:
                pass

            self._complete_goal_backend(goal_id, wallet_id, goal_name, wallet_name, wallet_currency)

        elif action_key == "edit":
            needed = (
                "edit_goal_select", "edit_goal_name",
                "edit_goal_amount_to_reach", "edit_goal_amount_reached",
                "edit_goal_category", "edit_goal_currency"
            )
            missing = [n for n in needed if not hasattr(self, n)]
            if missing:
                QMessageBox.warning(self, "Missing inputs", f"Some edit inputs are not available: {', '.join(missing)}")
                return

            goal_id = self.edit_goal_select.currentData(Qt.UserRole)
            if goal_id is None:
                QMessageBox.warning(self, "No goal selected", "Please choose a goal to edit.")
                return
            goal_id = int(goal_id)

            new_name = (self.edit_goal_name.text() or "").strip()
            if not new_name:
                QMessageBox.warning(self, "Missing name", "Please enter a new name.")
                return

            try:
                new_amount_to_reach = float(self.edit_goal_amount_to_reach.value())
                new_amount_reached  = float(self.edit_goal_amount_reached.value())
            except Exception:
                QMessageBox.warning(self, "Invalid amounts", "Please enter valid numbers.")
                return

            new_category_id = self.edit_goal_category.currentData(Qt.UserRole)
            new_category_id = int(new_category_id) if new_category_id is not None else None

            new_currency = self.edit_goal_currency.currentData(Qt.UserRole) or self.edit_goal_currency.currentText()
            new_currency = str(new_currency)

            self._edit_goal_backend(
                goal_id=goal_id,
                new_name=new_name,
                new_amount_to_reach=new_amount_to_reach,
                new_amount_reached=new_amount_reached,
                new_category_id=new_category_id,
                new_currency=new_currency,
            )

        elif action_key == "remove":
            if not hasattr(self, "remove_goal_select"):
                QMessageBox.warning(self, "Missing selector", "Goal selector is not available.")
                return

            goal_id = self.remove_goal_select.currentData(Qt.UserRole)
            if goal_id is None:
                QMessageBox.warning(self, "No goal selected", "Please choose a goal to remove.")
                return

            goal_id = int(goal_id)
            goal_name = self.remove_goal_select.currentText().strip()

            self._remove_goal_backend(goal_id, goal_name)

    # ---------- UI builders for each page ----------
    def _build_add_goal_inputs(self):
        boxes = self._boxes_by_page.get(id(self.page_add_goal), [])
        if len(boxes) < 6:
            return

        # 1) Name — default text clears on first focus
        self.add_goal_name = QLineEdit()
        self.add_goal_name.setText("e.g. shoes")
        self.add_goal_name.installEventFilter(self)
        lay1 = self._box_layout(boxes[0])
        self._labeled(lay1, "Name", self.add_goal_name)

        # 2) Amount to reach
        self.add_goal_to_reach = QDoubleSpinBox()
        self.add_goal_to_reach.setDecimals(2)
        self.add_goal_to_reach.setRange(0.00, 1_000_000_000.00)
        self.add_goal_to_reach.setSingleStep(1.00)
        self.add_goal_to_reach.setLocale(QLocale.c())        # ← force decimal point
        self.add_goal_to_reach.setGroupSeparatorShown(False)
        lay2 = self._box_layout(boxes[1])
        self._labeled(lay2, "Amount to reach", self.add_goal_to_reach)

        # 3) Amount reached
        self.add_goal_reached = QDoubleSpinBox()
        self.add_goal_reached.setDecimals(2)
        self.add_goal_reached.setRange(0.00, 1_000_000_000.00)
        self.add_goal_reached.setSingleStep(1.00)
        self.add_goal_reached.setLocale(QLocale.c())         # ← force decimal point
        self.add_goal_reached.setGroupSeparatorShown(False)
        lay3 = self._box_layout(boxes[2])
        self._labeled(lay3, "Amount reached", self.add_goal_reached)

        # 4) Category
        self.add_goal_category = QComboBox()
        self._load_categories_into_combo(self.add_goal_category)
        lay4 = self._box_layout(boxes[3])
        self._labeled(lay4, "Category", self.add_goal_category)

        # 5) Currency
        self.add_goal_currency = QComboBox()
        for c in ("EUR", "MXN", "USD"):
            self.add_goal_currency.addItem(c, c)
        lay5 = self._box_layout(boxes[4])
        self._labeled(lay5, "Currency", self.add_goal_currency)

        # 6) Start date
        self.add_goal_start_date = QDateEdit()
        self.add_goal_start_date.setCalendarPopup(True)
        self.add_goal_start_date.setDate(QDate.currentDate())
        lay6 = self._box_layout(boxes[5])
        self._labeled(lay6, "Start date", self.add_goal_start_date)

    def _build_complete_goal_inputs(self):
        boxes = self._boxes_by_page.get(id(self.page_complete_goal), [])
        if len(boxes) < 2:
            return

        # 1) Goal
        self.complete_goal_select = QComboBox()
        self._load_goals_into_combo(self.complete_goal_select)
        lay1 = self._box_layout(boxes[0])
        self._labeled(lay1, "Goal", self.complete_goal_select)

        # 2) Wallet
        self.complete_goal_wallet = QComboBox()
        self._load_wallets_into_combo(self.complete_goal_wallet)
        lay2 = self._box_layout(boxes[1])
        self._labeled(lay2, "Wallet", self.complete_goal_wallet)

    def _build_edit_goal_inputs(self):
        boxes = self._boxes_by_page.get(id(self.page_edit_goal), [])
        if len(boxes) < 6:
            return

        # 1) Goal (select existing)
        self.edit_goal_select = QComboBox()
        self._load_goals_into_combo(self.edit_goal_select)
        lay1 = self._box_layout(boxes[0])
        self._labeled(lay1, "Goal", self.edit_goal_select)

        # 2) New name
        self.edit_goal_name = QLineEdit()
        lay2 = self._box_layout(boxes[1])
        self._labeled(lay2, "New name", self.edit_goal_name)

        # 3) New amount to reach
        self.edit_goal_amount_to_reach = QDoubleSpinBox()
        self.edit_goal_amount_to_reach.setDecimals(2)
        self.edit_goal_amount_to_reach.setRange(0.00, 1_000_000_000.00)
        self.edit_goal_amount_to_reach.setSingleStep(1.00)
        self.edit_goal_amount_to_reach.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.edit_goal_amount_to_reach.setLocale(QLocale.c())     # ← force decimal point
        self.edit_goal_amount_to_reach.setGroupSeparatorShown(False)
        lay3 = self._box_layout(boxes[2])
        self._labeled(lay3, "New amount to reach", self.edit_goal_amount_to_reach)

        # 4) New amount reached
        self.edit_goal_amount_reached = QDoubleSpinBox()
        self.edit_goal_amount_reached.setDecimals(2)
        self.edit_goal_amount_reached.setRange(0.00, 1_000_000_000.00)
        self.edit_goal_amount_reached.setSingleStep(1.00)
        self.edit_goal_amount_reached.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.edit_goal_amount_reached.setLocale(QLocale.c())      # ← force decimal point
        self.edit_goal_amount_reached.setGroupSeparatorShown(False)
        lay4 = self._box_layout(boxes[3])
        self._labeled(lay4, "New amount reached", self.edit_goal_amount_reached)

        # 5) New category (names)
        self.edit_goal_category = QComboBox()
        self._load_categories_into_combo(self.edit_goal_category)
        lay5 = self._box_layout(boxes[4])
        self._labeled(lay5, "New category", self.edit_goal_category)

        # 6) New currency
        self.edit_goal_currency = QComboBox()
        for c in ("EUR", "MXN", "USD"):
            self.edit_goal_currency.addItem(c, c)
        lay6 = self._box_layout(boxes[5])
        self._labeled(lay6, "New currency", self.edit_goal_currency)

        # Prefill on selection change
        self.edit_goal_select.currentIndexChanged.connect(self._on_edit_goal_changed)
        self._on_edit_goal_changed(self.edit_goal_select.currentIndex())

    def _on_edit_goal_changed(self, _idx: int):
        if not hasattr(self, "edit_goal_select"):
            return
        gid = self.edit_goal_select.currentData(Qt.UserRole)
        if gid is None:
            return

        rows = self._fetch_goals()
        row = next((r for r in rows if r[0] == gid), None)
        if not row:
            return

        # row = (id, name, to_reach, reached, category_id, currency, completed, start_date, end_date)
        _, name, to_reach, reached, category_id, currency, *_ = row

        self.edit_goal_name.setText("" if name is None else str(name))

        try:
            self.edit_goal_amount_to_reach.setValue(0.0 if to_reach is None else float(to_reach))
        except Exception:
            self.edit_goal_amount_to_reach.setValue(0.0)

        try:
            self.edit_goal_amount_reached.setValue(0.0 if reached is None else float(reached))
        except Exception:
            self.edit_goal_amount_reached.setValue(0.0)

        if category_id is not None:
            idx = self.edit_goal_category.findData(category_id, role=Qt.UserRole)
            if idx >= 0:
                self.edit_goal_category.setCurrentIndex(idx)

        cur = "" if currency is None else str(currency)
        idx = self.edit_goal_currency.findText(cur, Qt.MatchExactly)
        self.edit_goal_currency.setCurrentIndex(idx if idx >= 0 else 0)

    def _build_remove_goal_inputs(self):
        boxes = self._boxes_by_page.get(id(self.page_remove_goal), [])
        if len(boxes) < 1:
            return

        self.remove_goal_select = QComboBox()
        self._load_goals_into_combo(self.remove_goal_select)
        lay = self._box_layout(boxes[0])
        self._labeled(lay, "Goal", self.remove_goal_select)

    # ---------- Data helpers ----------
    def _load_goals_into_combo(self, combo: QComboBox):
        combo.clear()
        rows = self._fetch_goals()
        rows.sort(key=lambda r: (r[1] or "").lower())
        for r in rows:
            combo.addItem("" if r[1] is None else str(r[1]), r[0])

    def _fetch_wallets(self):
        try:
            from backend.high_level.analysis import order_by as _order_by
            return _order_by(1) or []  # expected: (id, name, amount, currency, ...)
        except Exception:
            return []

    def _fetch_categories(self):
        try:
            from backend.crud.categories import get_all_categories
        except Exception:
            return []
        try:
            return get_all_categories() or []
        except Exception:
            return []

    def _load_wallets_into_combo(self, combo: QComboBox):
        combo.clear()
        rows = self._fetch_wallets()
        rows.sort(key=lambda r: (r[1] or "").lower())
        for r in rows:
            combo.addItem("" if r[1] is None else str(r[1]), r[0])

    def _load_categories_into_combo(self, combo: QComboBox):
        combo.clear()
        rows = self._fetch_categories()
        rows.sort(key=lambda r: (r[1] or "").lower())
        for r in rows:
            combo.addItem("" if r[1] is None else str(r[1]), r[0])

    # ---------- Tables ----------
    def _style_table(self, table: QTableWidget):
        """Theme-aware table styling."""
        t = current_theme()
        sel_rgba = f"rgba({t.MAGENTA.red()},{t.MAGENTA.green()},{t.MAGENTA.blue()},0.35)"
        if t.variant == "light":
            base_bg      = "rgba(255,255,255,0.75)"
            text_color   = t.TEXT
            grid_color   = "rgba(0,0,0,0.08)"
            border_color = "rgba(0,0,0,0.10)"
            alt_bg       = "rgba(0,0,0,0.03)"
            header_bg    = "rgba(0,0,0,0.06)"
            header_text  = t.TEXT
        else:
            base_bg      = "rgba(12,14,22,0.40)"
            text_color   = t.TEXT
            grid_color   = "rgba(255,255,255,0.06)"
            border_color = "rgba(255,255,255,0.06)"
            alt_bg       = "rgba(255,255,255,0.02)"
            header_bg    = "rgba(255,255,255,0.06)"
            header_text  = t.TEXT

        table.setStyleSheet(f"""
            QTableWidget {{
                background: {base_bg};
                color: {text_color};
                gridline-color: {grid_color};
                border: 1px solid {border_color};
                selection-background-color: {sel_rgba};
                selection-color: {t.TEXT};
                alternate-background-color: {alt_bg};
            }}
            QHeaderView::section {{
                background: {header_bg};
                color: {header_text};
                border: none;
                padding: 6px 8px;
                font-weight: 600;
            }}
            QTableCornerButton::section {{ background: transparent; border: none; }}
        """)

    def _make_goals_table_widget(self, rows) -> QTableWidget:
        """Create a themed goals summary table (Name, % Reached)."""
        table = QTableWidget()
        self._style_table(table)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        table.setWordWrap(False)

        table.setColumnCount(2)
        table.setHorizontalHeaderLabels(["Name", "% Reached"])
        table.setRowCount(len(rows))
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)

        table.setSortingEnabled(False)
        table.setUpdatesEnabled(False)
        for r, row in enumerate(rows):
            # row = (id, name, to_reach, reached, category_id, currency, completed, start_date, end_date)
            name = "" if row[1] is None else str(row[1])
            pct  = self._pct_reached(row[3], row[2])
            name_item = QTableWidgetItem(name)
            pct_item  = QTableWidgetItem(pct)
            pct_item.setTextAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
            table.setItem(r, 0, name_item)
            table.setItem(r, 1, pct_item)
        table.setUpdatesEnabled(True)

        hdr = table.horizontalHeader()
        hdr.setMinimumSectionSize(80)
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)          # Name fills
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents) # % compact

        # Double-click to open full view
        table.doubleClicked.connect(lambda *_: self._open_full_dialog())
        return table

    def _fade_in_over_current(self, new_widget: QWidget, duration: int = 140):
        """Overview-like fade swap in Panel A (same as wallets).”
        """
        if self._summary_stack is None:
            return
        old = self._summary_table

        self._summary_stack.addWidget(new_widget)
        eff = QGraphicsOpacityEffect(new_widget)
        eff.setOpacity(0.0)
        new_widget.setGraphicsEffect(eff)
        self._summary_stack.setCurrentWidget(new_widget)

        anim = QPropertyAnimation(eff, b"opacity", self)
        anim.setDuration(duration)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.InOutCubic)

        def finalize():
            if old is not None:
                try:
                    idx = self._summary_stack.indexOf(old)
                    if idx != -1:
                        self._summary_stack.removeWidget(old)
                except Exception:
                    pass
                old.setParent(None)
                old.deleteLater()
            new_widget.setGraphicsEffect(None)
            self._summary_table = new_widget
            self._fade_anim = None

        anim.finished.connect(finalize)
        self._fade_anim = anim
        anim.start()

    def _build_goals_table(self):
        rows = self._fetch_goals()
        new_table = self._make_goals_table_widget(rows)
        self._fade_in_over_current(new_table, duration=140)

    def _open_full_dialog(self):
        """Open modal dialog containing the full goals table (all attributes EXCEPT ID)."""
        rows = self._fetch_goals()

        dlg = QDialog(self)
        dlg.setWindowTitle("All goals (full)")
        dlg.resize(820, 460)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        table = QTableWidget()
        self._style_table(table)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.setWordWrap(False)

        headers = [
            "Name", "Amount to reach", "Amount reached",
            "Category ID", "Currency", "Completed", "Start date", "End date"
        ]
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setRowCount(len(rows))

        for r, row in enumerate(rows):
            (_, name, to_reach, reached, cat_id, currency, completed, start_date, end_date) = row
            table.setItem(r, 0, QTableWidgetItem("" if name is None else str(name)))
            table.setItem(r, 1, QTableWidgetItem("" if to_reach is None else f"{to_reach:.2f}"))
            table.setItem(r, 2, QTableWidgetItem("" if reached is None else f"{reached:.2f}"))
            table.setItem(r, 3, QTableWidgetItem("" if cat_id is None else str(cat_id)))
            table.setItem(r, 4, QTableWidgetItem("" if currency is None else str(currency)))
            table.setItem(r, 5, QTableWidgetItem("Yes" if completed else "No"))
            table.setItem(r, 6, QTableWidgetItem("" if start_date is None else str(start_date)))
            table.setItem(r, 7, QTableWidgetItem("" if end_date is None else str(end_date)))

        hdr = table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)           # Name
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # Amount to reach
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # Amount reached
        hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # Category ID
        hdr.setSectionResizeMode(4, QHeaderView.ResizeToContents)  # Currency
        hdr.setSectionResizeMode(5, QHeaderView.ResizeToContents)  # Completed
        hdr.setSectionResizeMode(6, QHeaderView.ResizeToContents)  # Start date
        hdr.setSectionResizeMode(7, QHeaderView.ResizeToContents)  # End date

        lay.addWidget(table, 1)

        close_row = QHBoxLayout()
        close_row.addStretch(1)
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(dlg.accept)
        close_row.addWidget(btn_close)
        lay.addLayout(close_row)

        # Theme the dialog widgets
        self._style_table(table)
        self._style_dialog_buttons([btn_close])

        dlg.exec()

    # ---------- Data + misc ----------
    def _fetch_goals(self):
        """
        goals_order_by(1) returns rows as:
        (id, name, amount_to_reach, amount_reached, category_id, currency, completed, start_date, end_date)
        """
        try:
            rows = goals_order_by(1)
        except Exception:
            rows = []
        return rows if rows else []

    @staticmethod
    def _pct_reached(amount_reached, amount_to_reach) -> str:
        try:
            if amount_to_reach is None or float(amount_to_reach) <= 0:
                return "—"
            pct = (float(amount_reached or 0.0) / float(amount_to_reach)) * 100.0
            pct = max(0.0, pct)
            return f"{pct:.1f}%"
        except Exception:
            return "—"

    def eventFilter(self, obj, event):
        # Clear the default text once on first focus/click
        if hasattr(self, "add_goal_name") and obj is self.add_goal_name and event.type() == QEvent.FocusIn:
            if not self._add_goal_name_cleared and self.add_goal_name.text() == "e.g. shoes":
                self.add_goal_name.clear()
                self._add_goal_name_cleared = True
        return super().eventFilter(obj, event)

    # ---------- Smooth refresh & lifecycle (wallets-style) ----------
    def _refresh_from_db(self):
        """Re-read DB and refresh table + selectors smoothly."""
        self._build_goals_table()

        # Refresh selectors across pages, preserving selection where possible
        # Complete page
        if hasattr(self, "complete_goal_select"):
            prev_gid = self.complete_goal_select.currentData(Qt.UserRole)
            self._load_goals_into_combo(self.complete_goal_select)
            if prev_gid is not None:
                gidx = self.complete_goal_select.findData(prev_gid, role=Qt.UserRole)
                if gidx >= 0:
                    self.complete_goal_select.setCurrentIndex(gidx)
        if hasattr(self, "complete_goal_wallet"):
            prev_wid = self.complete_goal_wallet.currentData(Qt.UserRole)
            self._load_wallets_into_combo(self.complete_goal_wallet)
            if prev_wid is not None:
                widx = self.complete_goal_wallet.findData(prev_wid, role=Qt.UserRole)
                if widx >= 0:
                    self.complete_goal_wallet.setCurrentIndex(widx)

        # Edit page
        if hasattr(self, "edit_goal_select"):
            prev_gid = self.edit_goal_select.currentData(Qt.UserRole)
            self._load_goals_into_combo(self.edit_goal_select)
            if prev_gid is not None:
                eidx = self.edit_goal_select.findData(prev_gid, role=Qt.UserRole)
                if eidx >= 0:
                    self.edit_goal_select.setCurrentIndex(eidx)
            self._on_edit_goal_changed(self.edit_goal_select.currentIndex())

        if hasattr(self, "edit_goal_category"):
            # Try to keep the same selected category id if any
            prev_cid = self.edit_goal_category.currentData(Qt.UserRole)
            self._load_categories_into_combo(self.edit_goal_category)
            if prev_cid is not None:
                cidx = self.edit_goal_category.findData(prev_cid, role=Qt.UserRole)
                if cidx >= 0:
                    self.edit_goal_category.setCurrentIndex(cidx)

        # Remove page
        if hasattr(self, "remove_goal_select"):
            prev_gid = self.remove_goal_select.currentData(Qt.UserRole)
            self._load_goals_into_combo(self.remove_goal_select)
            if prev_gid is not None:
                ridx = self.remove_goal_select.findData(prev_gid, role=Qt.UserRole)
                if ridx >= 0:
                    self.remove_goal_select.setCurrentIndex(ridx)

    def _emit_data_changed(self):
        """Compatibility no-op (same rationale as wallets)."""
        pass

    def showEvent(self, e):
        super().showEvent(e)
        # Defer first DB read a tick so UI paints instantly
        QTimer.singleShot(35, self._refresh_from_db)

    # Toggle support (parity with other pages)
    def apply_toggle(self, key: int):
        if key == self.toggle_key:
            return
        self.toggle_key = key

    # ---------- THEME PLUMBING ----------
    def _style_dialog_buttons(self, buttons: list[QPushButton]):
        t = current_theme()
        if t.variant == "light":
            base_bg = "rgba(0,0,0,0.06)"
            base_bg_hover = "rgba(0,0,0,0.12)"
            border = "rgba(0,0,0,0.10)"
            border_hover = "rgba(0,0,0,0.18)"
        else:
            base_bg = "rgba(255,255,255,0.06)"
            base_bg_hover = "rgba(255,255,255,0.12)"
            border = "rgba(255,255,255,0.10)"
            border_hover = "rgba(255,255,255,0.18)"
        for b in buttons:
            b.setStyleSheet(f"""
                QPushButton {{
                    background: {base_bg};
                    border: 1px solid {border};
                    color: {t.TEXT};
                    border-radius: 8px; padding: 6px 12px; font-size:12px;
                }}
                QPushButton:hover {{
                    background: {base_bg_hover};
                    border-color: {border_hover};
                }}
            """)

    def _apply_theme_colors(self, theme):
        """Update buttons, labels, inputs and tables to the active theme."""
        mag = theme.MAGENTA
        blue = theme.ACCENT_BLUE
        text = theme.TEXT

        mag_rgba_checked = f"rgba({mag.red()},{mag.green()},{mag.blue()},{0.35 if theme.variant!='light' else 0.20})"
        mag_hex = mag.name()
        blue_rgba_checked = f"rgba({blue.red()},{blue.green()},{blue.blue()},{0.32 if theme.variant!='light' else 0.20})"
        blue_hex = blue.name()

        if theme.variant == "light":
            base_bg_glass   = "rgba(0,0,0,0.06)"
            base_bg_hover   = "rgba(0,0,0,0.12)"
            base_border     = "rgba(0,0,0,0.10)"
            base_border_hov = "rgba(0,0,0,0.18)"
            input_bg        = "rgba(255,255,255,0.75)"
            popup_bg        = "rgba(255,255,255,0.98)"
            sel_rgba        = mag_rgba_checked
            focus_color     = mag_hex
        else:
            base_bg_glass   = "rgba(255,255,255,0.06)"
            base_bg_hover   = "rgba(255,255,255,0.12)"
            base_border     = "rgba(255,255,255,0.10)"
            base_border_hov = "rgba(255,255,255,0.18)"
            input_bg        = "rgba(6,8,14,0.66)"
            popup_bg        = "rgba(12,14,22,0.95)"
            sel_rgba        = mag_rgba_checked
            focus_color     = mag_hex

        # Top nav chips
        nav_style = f"""
            QPushButton {{
                background: {base_bg_glass};
                border: 1px solid {base_border};
                border-radius: 12px;
                padding: 8px 14px;
                margin: 0px;
                font-size: 13px;
                font-weight: 600;
                color: {text};
            }}
            QPushButton:hover {{
                background: {base_bg_hover};
                border-color: {base_border_hov};
            }}
            QPushButton:checked {{
                background: {mag_rgba_checked};
                border-color: {mag_hex};
            }}
        """
        for b in (self.btn_nav_expenses, self.btn_nav_wallets, self.btn_nav_categories, self.btn_nav_goals):
            b.setStyleSheet(nav_style)

        # Action toggles (use blue accent when armed)
        action_style = f"""
            QPushButton {{
                background: {base_bg_glass};
                border: 1px solid {base_border};
                border-radius: 10px;
                padding: 3px 10px;
                font-size: 12px;
                color: {text};
            }}
            QPushButton:hover {{ background: {base_bg_hover}; }}
            QPushButton:checked {{
                background: {blue_rgba_checked};
                border-color: {blue_hex};
            }}
        """
        for b in (self.btn_add_goal, self.btn_complete_goal, self.btn_edit_goal, self.btn_remove_goal):
            b.setStyleSheet(action_style)

        # Label colors
        for lbl in self._themed_labels:
            lbl.setStyleSheet(f"font-size:12px; font-weight:600; color:{text};")

        # Inputs (theme-aware)
        inputs_qss = f"""
            QLineEdit, QComboBox, QDateEdit, QDoubleSpinBox {{
                background: {input_bg};
                color: {text};
                border: 1px solid {base_border};
                border-radius: 10px;
                padding: 5px 10px;
                min-height: 32px;
                max-height: 36px;
                selection-background-color: {sel_rgba};
                selection-color: {text};
            }}
            QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QDoubleSpinBox:focus {{
                border: 1px solid {focus_color};
            }}
            QComboBox QAbstractItemView {{
                background: {popup_bg};
                color: {text};
                selection-background-color: {sel_rgba};
                border: 1px solid {base_border};
            }}
            QComboBox::drop-down {{ width: 24px; border: none; }}
            QDateEdit::drop-down {{ width: 24px; border: none; }}
            QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{
                background: transparent; border: none; width: 16px;
            }}
            QAbstractSpinBox::up-arrow, QAbstractSpinBox::down-arrow {{ width: 8px; height: 8px; }}
        """
        # Apply to known inputs if present
        for w in (
            getattr(self, "add_goal_name", None),
            getattr(self, "add_goal_to_reach", None),
            getattr(self, "add_goal_reached", None),
            getattr(self, "add_goal_category", None),
            getattr(self, "add_goal_currency", None),
            getattr(self, "add_goal_start_date", None),
            getattr(self, "complete_goal_select", None),
            getattr(self, "complete_goal_wallet", None),
            getattr(self, "edit_goal_select", None),
            getattr(self, "edit_goal_name", None),
            getattr(self, "edit_goal_amount_to_reach", None),
            getattr(self, "edit_goal_amount_reached", None),
            getattr(self, "edit_goal_category", None),
            getattr(self, "edit_goal_currency", None),
            getattr(self, "remove_goal_select", None),
        ):
            if w:
                w.setStyleSheet(inputs_qss)

        # Restyle live table with theme
        if self._summary_table is not None:
            self._style_table(self._summary_table)
            self._summary_table.viewport().update()

    # ---------- Backend bridges (unchanged API placeholders) ----------
    def _add_goal_backend(self, name, to_reach, reached, category_id, currency, start_date):
        try:
            from backend.crud.goals import add_goal
        except Exception as e:
            QMessageBox.critical(self, "Backend not available",
                                 f"Could not import add_goal: {e}")
            return
        try:
            add_goal(name, to_reach, reached, category_id, currency, start_date)
            QMessageBox.information(self, "Goal added", f"Added goal “{name}”.")
            # Reset inputs
            if hasattr(self, "add_goal_name"):
                self.add_goal_name.clear()
                self._add_goal_name_cleared = True
            if hasattr(self, "add_goal_to_reach"):
                self.add_goal_to_reach.setValue(0.0)
            if hasattr(self, "add_goal_reached"):
                self.add_goal_reached.setValue(0.0)
            # Refresh all UI like wallets
            self._refresh_from_db()
            self._emit_data_changed()
        except Exception as e:
            QMessageBox.critical(self, "Error adding goal", str(e))

    def _complete_goal_backend(self, goal_id, wallet_id, goal_name, wallet_name, wallet_currency):
        try:
            from backend.high_level.analysis import complete_goal
        except Exception as e:
            QMessageBox.critical(self, "Backend not available",
                                 f"Could not import complete_goal: {e}")
            return
        try:
            complete_goal(goal_id, wallet_id)
            QMessageBox.information(
                self, "Goal completed",
                f"Completed “{goal_name}”. Funds moved to wallet “{wallet_name}” ({wallet_currency})."
            )
            self._refresh_from_db()
            self._emit_data_changed()
        except Exception as e:
            QMessageBox.critical(self, "Error completing goal", str(e))

    def _edit_goal_backend(self, **kwargs):
        try:
            from backend.crud.goals import edit_goal
        except Exception as e:
            QMessageBox.critical(self, "Backend not available",
                                 f"Could not import edit_goal: {e}")
            return
        try:
            edit_goal(**kwargs)
            QMessageBox.information(self, "Goal updated", "Goal updated successfully.")
            self._refresh_from_db()
            self._emit_data_changed()
        except Exception as e:
            QMessageBox.critical(self, "Error updating goal", str(e))

    def _remove_goal_backend(self, goal_id, goal_name):
        try:
            from backend.crud.goals import remove_goal
        except Exception as e:
            QMessageBox.critical(self, "Backend not available",
                                 f"Could not import remove_goal: {e}")
            return
        try:
            remove_goal(goal_id)
            QMessageBox.information(self, "Goal removed", f"Removed goal “{goal_name}”.")
            self._refresh_from_db()
            self._emit_data_changed()
        except Exception as e:
            QMessageBox.critical(self, "Error removing goal", str(e))


# ---------- Soft halo painter for the middle section (magenta + cool blue) ----------
class GoalsHaloPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("background: transparent;")
        on_theme_changed(lambda *_: self.update())  # repaint on theme change

    def paintEvent(self, e):
        t = current_theme()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = self.rect()

        # Left magenta orb (theme-aware)
        g1 = QRadialGradient(r.width()*0.28, r.height()*0.35, min(r.width(), r.height())*0.65)
        g1.setColorAt(0.0, QColor(t.MAGENTA.red(), t.MAGENTA.green(), t.MAGENTA.blue(), t.orb_magenta_alpha))
        g1.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.fillRect(r, g1)

        # Right cool orb (theme-aware)
        g2 = QRadialGradient(r.width()*0.82, r.height()*0.28, min(r.width(), r.height())*0.70)
        g2.setColorAt(0.0, QColor(t.ACCENT_BLUE.red(), t.ACCENT_BLUE.green(), t.ACCENT_BLUE.blue(), t.orb_blue_alpha))
        g2.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.fillRect(r, g2)
