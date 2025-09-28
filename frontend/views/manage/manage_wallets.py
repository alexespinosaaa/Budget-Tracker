# frontend/views/manage/manage_wallets.py
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QSizePolicy,
    QPushButton, QLabel, QButtonGroup,
    QTableWidget, QTableWidgetItem, QHeaderView, QStackedWidget,
    QLineEdit, QDoubleSpinBox, QComboBox, QMessageBox, QDateEdit,
    QStackedLayout, QGraphicsOpacityEffect, QDialog
)
from PySide6.QtCore import Qt, Signal, QLocale, QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QColor, QPainter, QRadialGradient

# Data
from backend.high_level.analysis import order_by  # (id, name, amount, currency, ...)

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


class ManageWalletsPage(QWidget):
    # Cross-navigation to sibling manage pages
    navigateExpenses   = Signal()
    navigateWallets    = Signal()
    navigateCategories = Signal()
    navigateGoals      = Signal()

    def __init__(self, initial_toggle_key: int = 1):
        super().__init__()
        self.toggle_key = initial_toggle_key

        self._boxes_by_page: dict[int, list[QFrame]] = {}   # page-id -> list[QFrame]
        self._armed_action  = None  # "add" | "transfer" | "edit" | "remove"
        self._themed_labels: list[QLabel] = []  # labels recolored on theme change

        # Panel A summary (smooth swaps)
        self._summary_stack: QStackedLayout | None = None
        self._summary_table: QTableWidget | None = None   # current table widget
        self.table_wallets: QTableWidget | None = None    # compatibility alias
        self._fade_anim = None

        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setMinimumSize(1000, 700)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # ---------- Root layout (transparent gutters + halo center) ----------
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.left_section   = QFrame(); self.left_section.setStyleSheet("background: transparent;")
        self.middle_section = WalletsHaloPanel()   # paints soft magenta/blue orbs
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
        self._build_add_wallet_inputs()
        self._build_transfer_inputs()
        self._build_edit_wallet_inputs()
        self._build_remove_wallet_inputs()

        # Theme pass + subscribe
        self._apply_theme_colors(current_theme())
        on_theme_changed(self._apply_theme_colors)

    # ---------- Middle content ----------
    def _populate_middle(self, parent: QFrame):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(24, 84, 24, 24)
        layout.setSpacing(12)

        # === TOP: big nav chips (glass lozenges) ===
        top_buttons_row = QHBoxLayout()
        top_buttons_row.setContentsMargins(0, 0, 0, 0)
        top_buttons_row.setSpacing(12)
        layout.addLayout(top_buttons_row)

        def make_primary_btn(text: str) -> QPushButton:
            b = QPushButton(text)
            b.setCheckable(True)
            b.setMinimumHeight(40)
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            return b  # styled in _apply_theme_colors
        self.btn_nav_expenses   = make_primary_btn("Expenses")
        self.btn_nav_wallets    = make_primary_btn("Wallets")
        self.btn_nav_categories = make_primary_btn("Categories")
        self.btn_nav_goals      = make_primary_btn("Goals")

        nav_group = QButtonGroup(self)
        nav_group.setExclusive(True)
        for b in (self.btn_nav_expenses, self.btn_nav_wallets, self.btn_nav_categories, self.btn_nav_goals):
            nav_group.addButton(b)
        self.btn_nav_wallets.setChecked(True)

        self.btn_nav_expenses.clicked.connect(lambda *_: self.navigateExpenses.emit())
        self.btn_nav_categories.clicked.connect(lambda *_: self.navigateCategories.emit())
        self.btn_nav_goals.clicked.connect(lambda *_: self.navigateGoals.emit())

        top_buttons_row.addWidget(self.btn_nav_expenses,   1)
        top_buttons_row.addWidget(self.btn_nav_wallets,    1)
        top_buttons_row.addWidget(self.btn_nav_categories, 1)
        top_buttons_row.addWidget(self.btn_nav_goals,      1)

        # === SECOND: wallet action toggles (glass) ===
        actions_row = QHBoxLayout()
        actions_row.setContentsMargins(0, 0, 0, 0)
        actions_row.setSpacing(12)
        layout.addLayout(actions_row)
        actions_row.addStretch(1)

        def make_toggle(text: str) -> ActionButton:
            t = ActionButton(text)
            t.setMinimumHeight(30)
            return t
        self.btn_add_wallet     = make_toggle("Add wallet")
        self.btn_transfer_money = make_toggle("Transfer money")
        self.btn_edit_wallet    = make_toggle("Edit wallet")
        self.btn_remove_wallet  = make_toggle("Remove wallet")

        actions_row.addWidget(self.btn_add_wallet,     0, Qt.AlignRight)
        actions_row.addWidget(self.btn_transfer_money, 0, Qt.AlignRight)
        actions_row.addWidget(self.btn_edit_wallet,    0, Qt.AlignRight)
        actions_row.addWidget(self.btn_remove_wallet,  0, Qt.AlignRight)

        # Mutually exclusive
        self.actions_group = QButtonGroup(self)
        self.actions_group.setExclusive(True)
        for b in (self.btn_add_wallet, self.btn_transfer_money, self.btn_edit_wallet, self.btn_remove_wallet):
            self.actions_group.addButton(b)

        # === THIRD: two glass panels ===
        panels_row = QHBoxLayout()
        panels_row.setContentsMargins(0, 0, 0, 0)
        panels_row.setSpacing(16)
        layout.addLayout(panels_row, 1)

        # Panel A — wallets summary (stacked for smooth swaps)
        self.panelA = QFrame()
        self.panelA.setProperty("kind", "glassDeep")
        self.panelA.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        pA = QVBoxLayout(self.panelA)
        pA.setContentsMargins(16, 12, 16, 12)
        pA.setSpacing(8)

        lblA = QLabel("Wallets")
        self._themed_labels.append(lblA)
        pA.addWidget(lblA)

        summary_area = QFrame()
        self._summary_stack = QStackedLayout(summary_area)
        self._summary_stack.setContentsMargins(0, 0, 0, 0)

        # First mount: empty table, then fade in real data on showEvent
        self._summary_table = self._make_wallets_table_widget([])
        self._summary_stack.addWidget(self._summary_table)
        self._summary_stack.setCurrentWidget(self._summary_table)
        self.table_wallets = self._summary_table  # compatibility alias

        pA.addWidget(summary_area, 1)

        # Panel B — stacked pages (compact top-aligned mini boxes)
        self.panelB = QFrame()
        self.panelB.setProperty("kind", "glassDeep")
        self.panelB.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        vB = QVBoxLayout(self.panelB)
        vB.setContentsMargins(12, 12, 12, 12)
        vB.setSpacing(0)

        self.panelBStack = QStackedWidget(self.panelB)
        self.panelBStack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        vB.addWidget(self.panelBStack)

        # Build pages with required box counts
        self.page_add_wallet     = self._build_action_page(3)
        self.page_transfer_money = self._build_action_page(3)
        self.page_edit_wallet    = self._build_action_page(4)
        self.page_remove_wallet  = self._build_action_page(1)

        self.panelBStack.addWidget(self.page_add_wallet)      # 0
        self.panelBStack.addWidget(self.page_transfer_money)  # 1
        self.panelBStack.addWidget(self.page_edit_wallet)     # 2
        self.panelBStack.addWidget(self.page_remove_wallet)   # 3

        # Default: armed "add"
        self.panelBStack.setCurrentIndex(0)
        self.btn_add_wallet.setChecked(True)
        self._armed_action = "add"

        # Arm-or-fire wiring
        self.btn_add_wallet.clicked.connect(     lambda *_: self._arm_or_fire("add",      0))
        self.btn_transfer_money.clicked.connect(lambda *_: self._arm_or_fire("transfer",  1))
        self.btn_edit_wallet.clicked.connect(    lambda *_: self._arm_or_fire("edit",     2))
        self.btn_remove_wallet.clicked.connect(  lambda *_: self._arm_or_fire("remove",   3))

        self.btn_add_wallet.doubleClicked.connect(     lambda *_: self._execute_action("add"))
        self.btn_transfer_money.doubleClicked.connect(lambda *_: self._execute_action("transfer"))
        self.btn_edit_wallet.doubleClicked.connect(    lambda *_: self._execute_action("edit"))
        self.btn_remove_wallet.doubleClicked.connect(  lambda *_: self._execute_action("remove"))

        panels_row.addWidget(self.panelA, 1)
        panels_row.addWidget(self.panelB, 1)

    # ---------- Box helpers (compact / glass) ----------
    def _build_action_page(self, box_count: int) -> QWidget:
        """
        Create a stacked page holding `box_count` compact glass boxes.
        Boxes are top-aligned with tight 12px gaps; remaining space sits below.
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
            b.setMinimumHeight(72)
            v.addWidget(b, 0)      # don't stretch: keeps content top-aligned
            boxes.append(b)
        v.addStretch(1)
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

        widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        widget.setMinimumHeight(32)
        widget.setMaximumHeight(36)
        parent_lay.addWidget(widget, 0)

    # ---------- Arm & Fire ----------
    def _arm_or_fire(self, action_key: str, stack_index: int):
        """First click arms (switch), second click fires (executes)."""
        if self._armed_action != action_key:
            self.panelBStack.setCurrentIndex(stack_index)
            self._armed_action = action_key
        else:
            self._execute_action(action_key)

    def _execute_action(self, action_key: str):
        """Execute the armed action. (Backend behavior unchanged.)"""
        if action_key == "add":
            name = (self.add_wallet_name.text() or "").strip()
            if not name:
                QMessageBox.warning(self, "Missing name", "Please enter a wallet name.")
                return

            amount = float(self.add_wallet_amount.value() or 0.0)
            currency = self.add_wallet_currency.currentData(Qt.UserRole)
            if not currency:
                currency = "EUR"

            self._add_wallet_backend(name, amount, str(currency))

        elif action_key == "transfer":
            if not hasattr(self, "transfer_sender_combo") or not hasattr(self, "transfer_receiver_combo"):
                QMessageBox.warning(self, "Missing inputs", "Sender/Receiver selectors are not available.")
                return

            giver_id = self.transfer_sender_combo.currentData(Qt.UserRole)
            receiver_id = self.transfer_receiver_combo.currentData(Qt.UserRole)

            if giver_id is None or receiver_id is None:
                QMessageBox.warning(self, "Missing selection", "Please choose both a sender and a receiver wallet.")
                return
            if giver_id == receiver_id:
                QMessageBox.warning(self, "Invalid selection", "Sender and receiver must be different wallets.")
                return

            amount = float(self.transfer_amount.value() or 0.0) if hasattr(self, "transfer_amount") else 0.0
            if amount <= 0.0:
                QMessageBox.warning(self, "Invalid amount", "Please enter an amount greater than 0.")
                return

            self._transfer_money_backend(int(giver_id), int(receiver_id), amount)

        elif action_key == "edit":
            if not hasattr(self, "edit_wallet_select"):
                QMessageBox.warning(self, "Missing selector", "Select wallet control is not available.")
                return

            wid = self.edit_wallet_select.currentData(Qt.UserRole)
            if wid is None:
                QMessageBox.warning(self, "No wallet selected", "Please choose a wallet to edit.")
                return

            new_name = (self.edit_wallet_name.text() or "").strip() if hasattr(self, "edit_wallet_name") else ""
            if not new_name:
                QMessageBox.warning(self, "Missing name", "Name cannot be empty.")
                return

            new_amount = float(self.edit_wallet_amount.value()) if hasattr(self, "edit_wallet_amount") else 0.0

            new_currency = self.edit_wallet_currency.currentData(Qt.UserRole) if hasattr(self, "edit_wallet_currency") else None
            if not new_currency:
                new_currency = "EUR"

            self._edit_wallet_backend(int(wid), new_name, new_amount, str(new_currency))

        elif action_key == "remove":
            if not hasattr(self, "remove_wallet_combo"):
                QMessageBox.warning(self, "Missing selector", "Select wallet control is not available.")
                return

            wid = self.remove_wallet_combo.currentData(Qt.UserRole)
            if wid is None:
                QMessageBox.warning(self, "No wallet selected", "Please choose a wallet to remove.")
                return

            wallet_name = self.remove_wallet_combo.currentText()
            self._remove_wallet_backend(int(wid), wallet_name)

    # ---------- UI builders for each page ----------
    def _build_add_wallet_inputs(self):
        boxes = self._boxes_by_page.get(id(self.page_add_wallet), [])
        if len(boxes) < 3:
            return

        # 1) Name
        self.add_wallet_name = QLineEdit()
        self.add_wallet_name.setPlaceholderText("e.g., Main account")
        lay1 = self._box_layout(boxes[0])
        self._labeled(lay1, "Name", self.add_wallet_name)

        # 2) Amount
        self.add_wallet_amount = QDoubleSpinBox()
        self.add_wallet_amount.setDecimals(2)
        self.add_wallet_amount.setRange(0.00, 1_000_000_000.00)
        self.add_wallet_amount.setSingleStep(1.00)
        self.add_wallet_amount.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.add_wallet_amount.setLocale(QLocale.c())          # force decimal point
        self.add_wallet_amount.setGroupSeparatorShown(False)
        lay2 = self._box_layout(boxes[1])
        self._labeled(lay2, "Amount", self.add_wallet_amount)

        # 3) Currency
        self.add_wallet_currency = QComboBox()
        for c in ("EUR", "MXN", "USD"):
            self.add_wallet_currency.addItem(c, c)
        lay3 = self._box_layout(boxes[2])
        self._labeled(lay3, "Currency", self.add_wallet_currency)

    def _build_transfer_inputs(self):
        boxes = self._boxes_by_page.get(id(self.page_transfer_money), [])
        if len(boxes) < 3:
            return

        # 1) Sender
        self.transfer_sender_combo = QComboBox()
        self._load_wallets_into_combo(self.transfer_sender_combo)
        lay1 = self._box_layout(boxes[0])
        self._labeled(lay1, "Sender", self.transfer_sender_combo)

        # 2) Receiver (excludes sender)
        self.transfer_receiver_combo = QComboBox()
        sender_id = self.transfer_sender_combo.currentData(Qt.UserRole)
        self._load_wallets_into_combo(self.transfer_receiver_combo, exclude_id=sender_id)
        lay2 = self._box_layout(boxes[1])
        self._labeled(lay2, "Receiver", self.transfer_receiver_combo)

        self.transfer_sender_combo.currentIndexChanged.connect(self._on_transfer_sender_changed)

        # 3) Amount
        self.transfer_amount = QDoubleSpinBox()
        self.transfer_amount.setDecimals(2)
        self.transfer_amount.setRange(0.00, 1_000_000_000.00)
        self.transfer_amount.setSingleStep(1.00)
        self.transfer_amount.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.transfer_amount.setLocale(QLocale.c())            # force decimal point
        self.transfer_amount.setGroupSeparatorShown(False)
        lay3 = self._box_layout(boxes[2])
        self._labeled(lay3, "Money transferred", self.transfer_amount)

    def _on_transfer_sender_changed(self, _idx: int):
        if not hasattr(self, "transfer_sender_combo") or not hasattr(self, "transfer_receiver_combo"):
            return
        sender_id = self.transfer_sender_combo.currentData(Qt.UserRole)
        self._load_wallets_into_combo(self.transfer_receiver_combo, exclude_id=sender_id)
        if self.transfer_receiver_combo.count() > 0:
            self.transfer_receiver_combo.setCurrentIndex(0)

    def _build_edit_wallet_inputs(self):
        boxes = self._boxes_by_page.get(id(self.page_edit_wallet), [])
        if len(boxes) < 4:
            return

        # 1) Select wallet
        self.edit_wallet_select = QComboBox()
        self._load_wallets_into_combo(self.edit_wallet_select)
        lay1 = self._box_layout(boxes[0])
        self._labeled(lay1, "Select wallet", self.edit_wallet_select)

        # 2) New Name
        self.edit_wallet_name = QLineEdit()
        lay2 = self._box_layout(boxes[1])
        self._labeled(lay2, "New name", self.edit_wallet_name)

        # 3) New amount
        self.edit_wallet_amount = QDoubleSpinBox()
        self.edit_wallet_amount.setDecimals(2)
        self.edit_wallet_amount.setRange(0.00, 1_000_000_000.00)
        self.edit_wallet_amount.setSingleStep(1.00)
        self.edit_wallet_amount.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.edit_wallet_amount.setLocale(QLocale.c())         # force decimal point
        self.edit_wallet_amount.setGroupSeparatorShown(False)
        lay3 = self._box_layout(boxes[2])
        self._labeled(lay3, "New amount", self.edit_wallet_amount)

        # 4) New currency
        self.edit_wallet_currency = QComboBox()
        for c in ("EUR", "MXN", "USD"):
            self.edit_wallet_currency.addItem(c, c)
        lay4 = self._box_layout(boxes[3])
        self._labeled(lay4, "New currency", self.edit_wallet_currency)

        # Prefill when selection changes
        self.edit_wallet_select.currentIndexChanged.connect(self._on_edit_wallet_changed)
        self._on_edit_wallet_changed(self.edit_wallet_select.currentIndex())

    def _on_edit_wallet_changed(self, _idx: int):
        if not hasattr(self, "edit_wallet_select"):
            return
        wid = self.edit_wallet_select.currentData(Qt.UserRole)
        if wid is None:
            return

        rows = self._fetch_wallets()
        row = next((r for r in rows if r[0] == wid), None)
        if not row:
            return

        _id, name, amount, currency = row[0], row[1], row[2], row[3]

        if hasattr(self, "edit_wallet_name"):
            self.edit_wallet_name.setText("" if name is None else str(name))

        if hasattr(self, "edit_wallet_amount"):
            try:
                self.edit_wallet_amount.setValue(0.0 if amount is None else float(amount))
            except Exception:
                self.edit_wallet_amount.setValue(0.0)

        if hasattr(self, "edit_wallet_currency"):
            cur = "" if currency is None else str(currency)
            found = self.edit_wallet_currency.findText(cur, Qt.MatchExactly)
            self.edit_wallet_currency.setCurrentIndex(found if found >= 0 else 0)

    def _build_remove_wallet_inputs(self):
        boxes = self._boxes_by_page.get(id(self.page_remove_wallet), [])
        if len(boxes) < 1:
            return

        self.remove_wallet_combo = QComboBox()
        self._load_wallets_into_combo(self.remove_wallet_combo)

        lay = self._box_layout(boxes[0])
        self._labeled(lay, "Select wallet", self.remove_wallet_combo)

    # ---------- Data / UI ----------
    def _load_wallets_into_combo(self, combo: QComboBox, exclude_id: int | None = None):
        combo.clear()
        rows = self._fetch_wallets()
        rows.sort(key=lambda r: (r[1] or "").lower())
        for r in rows:
            wid = r[0]
            if exclude_id is not None and wid == exclude_id:
                continue
            name = "" if r[1] is None else str(r[1])
            combo.addItem(name, wid)

    def _fetch_wallets(self):
        """Get all wallets ordered by ID. Expected tuple: (id, name, amount, currency, ...)."""
        try:
            return order_by(1) or []
        except Exception:
            return []

    # ---------- Theme-aware table ----------
    def _style_table(self, table: QTableWidget):
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

    def _make_wallets_table_widget(self, rows) -> QTableWidget:
        """Create a themed wallets summary table."""
        table = QTableWidget()
        self._style_table(table)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        table.setWordWrap(False)

        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(["Name", "Amount", "Currency"])
        table.setRowCount(len(rows))
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)

        table.setSortingEnabled(False)
        table.setUpdatesEnabled(False)
        for r, row in enumerate(rows):
            name = row[1] if len(row) > 1 and row[1] is not None else ""
            amt  = row[2] if len(row) > 2 and row[2] is not None else 0.0
            curr = row[3] if len(row) > 3 and row[3] is not None else ""

            name_item = QTableWidgetItem(str(name))
            amt_item  = QTableWidgetItem(f"{amt:.2f}")
            curr_item = QTableWidgetItem(str(curr))
            amt_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            curr_item.setTextAlignment(Qt.AlignHCenter | Qt.AlignVCenter)

            table.setItem(r, 0, name_item)
            table.setItem(r, 1, amt_item)
            table.setItem(r, 2, curr_item)
        table.setUpdatesEnabled(True)

        hdr = table.horizontalHeader()
        hdr.setMinimumSectionSize(60)
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)          # Name takes remaining space
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents) # Amount tight
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents) # Currency tight

        # Optional: double-click to open full view (same columns here)
        table.doubleClicked.connect(lambda *_: self._open_full_dialog())
        return table

    def _fade_in_over_current(self, new_widget: QWidget, duration: int = 140):
        """Overview-like fade swap in Panel A."""
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
            self.table_wallets = new_widget  # compatibility
            self._fade_anim = None

        anim.finished.connect(finalize)
        self._fade_anim = anim
        anim.start()

    def _build_wallets_table(self):
        rows = self._fetch_wallets()
        new_table = self._make_wallets_table_widget(rows)
        self._fade_in_over_current(new_table, duration=140)

    def _open_full_dialog(self):
        rows = self._fetch_wallets()

        dlg = QDialog(self)
        dlg.setWindowTitle("All wallets (full)")
        dlg.resize(720, 420)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        table = self._make_wallets_table_widget(rows)
        lay.addWidget(table, 1)

        close_row = QHBoxLayout()
        close_row.addStretch(1)
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(dlg.accept)
        close_row.addWidget(btn_close)
        lay.addLayout(close_row)

        self._style_table(table)
        self._style_dialog_buttons([btn_close])

        dlg.exec()

    def _add_wallet_backend(self, name: str, amount: float, currency: str):
        try:
            from backend.crud.wallets import add_wallet as _add
        except Exception:
            _add = None

        if _add is None:
            QMessageBox.information(
                self,
                "Not wired yet",
                "Inputs captured successfully.\n\n"
                "Expose add_wallet(name, amount, currency) in backend.crud.wallets (or adjust the import)."
            )
            # print("[INFO] Would call add_wallet:", name, amount, currency)
            return

        try:
            _add(name=name, amount=amount, currency=currency)
            QMessageBox.information(self, "Wallet added", f'Wallet "{name}" ({amount:.2f} {currency}) was added.')
            self._refresh_from_db()
            self._emit_data_changed()
            if hasattr(self, "add_wallet_name"):
                self.add_wallet_name.clear()
            if hasattr(self, "add_wallet_amount"):
                self.add_wallet_amount.setValue(0.0)
        except Exception as e:
            QMessageBox.critical(self, "Error adding wallet", str(e))

    def _transfer_money_backend(self, giver_id: int, receiver_id: int, amount: float) -> None:
        try:
            from backend.high_level.analysis import transfer_money as _transfer
        except Exception:
            _transfer = None

        if _transfer is None:
            QMessageBox.information(
                self,
                "Not wired yet",
                "Inputs captured, but transfer_money(...) is not importable.\n"
                "Expose transfer_money(giver_wallet_id, receiver_wallet_id, amount) in backend.high_level.analysis."
            )
            # print("[INFO] Would call transfer_money:", giver_id, receiver_id, amount)
            return

        rows_before = self._fetch_wallets()

        def _lookup(rows, wid):
            for r in rows:
                if r[0] == wid:
                    return (r[1] or ""), (float(r[2]) if r[2] is not None else 0.0), (r[3] or "")
            return "", 0.0, ""

        sender_name, sender_amt_before, sender_curr = _lookup(rows_before, giver_id)
        receiver_name, receiver_amt_before, receiver_curr = _lookup(rows_before, receiver_id)

        try:
            _transfer(giver_wallet_id=giver_id, receiver_wallet_id=receiver_id, amount=amount)

            self._refresh_from_db()
            rows_after = self._fetch_wallets()
            _, sender_amt_after, _ = _lookup(rows_after, giver_id)
            _, receiver_amt_after, _ = _lookup(rows_after, receiver_id)

            if round(sender_amt_after, 2) == round(sender_amt_before, 2):
                QMessageBox.warning(self, "Transfer failed",
                                    "No balance changes detected. Check available funds and try again.")
            else:
                received_delta = receiver_amt_after - receiver_amt_before
                QMessageBox.information(
                    self,
                    "Transfer complete",
                    (f'{amount:.2f} {sender_curr} sent from "{sender_name}" '
                     f'to "{receiver_name}" (received {received_delta:.2f} {receiver_curr}).')
                )
            self._emit_data_changed()

            # Keep sender/receiver selections stable where possible
            if hasattr(self, "transfer_sender_combo"):
                self._load_wallets_into_combo(self.transfer_sender_combo)
                sidx = self.transfer_sender_combo.findData(giver_id, role=Qt.UserRole)
                if sidx >= 0:
                    self.transfer_sender_combo.setCurrentIndex(sidx)
                self._on_transfer_sender_changed(self.transfer_sender_combo.currentIndex())
                if hasattr(self, "transfer_receiver_combo"):
                    ridx = self.transfer_receiver_combo.findData(receiver_id, role=Qt.UserRole)
                    if ridx >= 0:
                        self.transfer_receiver_combo.setCurrentIndex(ridx)

            if hasattr(self, "transfer_amount"):
                self.transfer_amount.setValue(0.0)

        except Exception as e:
            QMessageBox.critical(self, "Error transferring money", str(e))

    def _edit_wallet_backend(self, wallet_id: int, new_name: str, new_amount: float, new_currency: str) -> None:
        try:
            from backend.crud.wallets import edit_wallet as _edit
        except Exception:
            _edit = None

        if _edit is None:
            QMessageBox.information(
                self,
                "Not wired yet",
                "Inputs captured, but edit_wallet(...) is not importable.\n"
                "Expose edit_wallet(wallet_id, new_name, new_amount, new_currency) in backend.crud.wallets."
            )
            # print("[INFO] Would call edit_wallet:", wallet_id, new_name, new_amount, new_currency)
            return

        try:
            _edit(wallet_id=wallet_id, new_name=new_name, new_amount=new_amount, new_currency=new_currency)

            QMessageBox.information(self, "Wallet updated",
                                    f'Wallet updated to "{new_name}" ({new_amount:.2f} {new_currency}).')

            self._refresh_from_db()
            self._emit_data_changed()
        except Exception as e:
            QMessageBox.critical(self, "Error updating wallet", str(e))

    def _remove_wallet_backend(self, wallet_id: int, wallet_name: str) -> None:
        try:
            from backend.crud.wallets import remove_wallet as _remove
        except Exception:
            _remove = None

        if _remove is None:
            QMessageBox.information(
                self,
                "Not wired yet",
                "Input captured, but remove_wallet(...) is not importable.\n"
                "Expose remove_wallet(wallet_id: int) in backend.crud.wallets."
            )
            # print("[INFO] Would call remove_wallet:", wallet_id)
            return

        prev_sender_id   = self.transfer_sender_combo.currentData(Qt.UserRole)   if hasattr(self, "transfer_sender_combo")   else None
        prev_receiver_id = self.transfer_receiver_combo.currentData(Qt.UserRole) if hasattr(self, "transfer_receiver_combo") else None

        try:
            _remove(wallet_id=wallet_id)
            QMessageBox.information(self, "Wallet deleted", f'Wallet "{wallet_name}" was successfully deleted.')

            self._refresh_from_db()
            self._emit_data_changed()

            # Try to restore previous selections
            if hasattr(self, "transfer_sender_combo"):
                if prev_sender_id is not None and prev_sender_id != wallet_id:
                    sidx = self.transfer_sender_combo.findData(prev_sender_id, role=Qt.UserRole)
                    if sidx >= 0:
                        self.transfer_sender_combo.setCurrentIndex(sidx)
                self._on_transfer_sender_changed(self.transfer_sender_combo.currentIndex())
                if hasattr(self, "transfer_receiver_combo") and prev_receiver_id is not None and prev_receiver_id != wallet_id:
                    ridx = self.transfer_receiver_combo.findData(prev_receiver_id, role=Qt.UserRole)
                    if ridx >= 0:
                        self.transfer_receiver_combo.setCurrentIndex(ridx)

        except Exception as e:
            QMessageBox.critical(self, "Error deleting wallet", str(e))

    # ---------- Smooth refresh & lifecycle ----------
    def _refresh_from_db(self):
        """Re-read DB and refresh table + selectors smoothly."""
        self._build_wallets_table()
        # refresh combos across pages
        if hasattr(self, "transfer_sender_combo"):
            current_sender_id = self.transfer_sender_combo.currentData(Qt.UserRole)
            self._load_wallets_into_combo(self.transfer_sender_combo)
            if current_sender_id is not None:
                sidx = self.transfer_sender_combo.findData(current_sender_id, role=Qt.UserRole)
                if sidx >= 0:
                    self.transfer_sender_combo.setCurrentIndex(sidx)
            self._on_transfer_sender_changed(self.transfer_sender_combo.currentIndex())
        if hasattr(self, "edit_wallet_select"):
            current_id = self.edit_wallet_select.currentData(Qt.UserRole)
            self._load_wallets_into_combo(self.edit_wallet_select)
            if current_id is not None:
                eidx = self.edit_wallet_select.findData(current_id, role=Qt.UserRole)
                if eidx >= 0:
                    self.edit_wallet_select.setCurrentIndex(eidx)
            self._on_edit_wallet_changed(self.edit_wallet_select.currentIndex())
        if hasattr(self, "remove_wallet_combo"):
            current_id = self.remove_wallet_combo.currentData(Qt.UserRole)
            self._load_wallets_into_combo(self.remove_wallet_combo)
            if current_id is not None:
                ridx = self.remove_wallet_combo.findData(current_id, role=Qt.UserRole)
                if ridx >= 0:
                    self.remove_wallet_combo.setCurrentIndex(ridx)

    def _emit_data_changed(self):
        """
        Compatibility no-op: some older code expected a cross-page
        event emitter (frontend.events). We don't have it here, and
        _refresh_from_db() already updates the UI, so do nothing.
        """
        pass

    def showEvent(self, e):
        super().showEvent(e)
        # Defer first DB read a tick so UI paints instantly
        QTimer.singleShot(35, self._refresh_from_db)

    # (Kept for parity; global toggle not used here)
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
        """Apply theme-aware styling to nav/action buttons, labels, inputs, and tables."""
        mag = theme.MAGENTA
        blue = theme.ACCENT_BLUE
        text = theme.TEXT

        mag_rgba_checked = f"rgba({mag.red()},{mag.green()},{mag.blue()},{0.35 if theme.variant!='light' else 0.20})"
        blue_rgba_checked = f"rgba({blue.red()},{blue.green()},{blue.blue()},{0.32 if theme.variant!='light' else 0.20})"

        if theme.variant == "light":
            base_bg_glass   = "rgba(0,0,0,0.06)"
            base_bg_hover   = "rgba(0,0,0,0.12)"
            base_border     = "rgba(0,0,0,0.10)"
            base_border_hov = "rgba(0,0,0,0.18)"
            input_bg        = "rgba(255,255,255,0.75)"
            popup_bg        = "rgba(255,255,255,0.98)"
        else:
            base_bg_glass   = "rgba(255,255,255,0.06)"
            base_bg_hover   = "rgba(255,255,255,0.12)"
            base_border     = "rgba(255,255,255,0.10)"
            base_border_hov = "rgba(255,255,255,0.18)"
            input_bg        = "rgba(6,8,14,0.66)"
            popup_bg        = "rgba(12,14,22,0.95)"

        # Top nav chips (magenta when checked)
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
                border-color: {theme.MAGENTA.name()};
            }}
        """
        for b in (self.btn_nav_expenses, self.btn_nav_wallets, self.btn_nav_categories, self.btn_nav_goals):
            b.setStyleSheet(nav_style)

        # Action toggles (blue when armed)
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
                border-color: {theme.ACCENT_BLUE.name()};
            }}
        """
        for b in (self.btn_add_wallet, self.btn_transfer_money, self.btn_edit_wallet, self.btn_remove_wallet):
            b.setStyleSheet(action_style)

        # Label colors
        for lbl in self._themed_labels:
            lbl.setStyleSheet(f"font-size:14px; font-weight:600; color:{text};")

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
                selection-background-color: {mag_rgba_checked};
                selection-color: {text};
            }}
            QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QDoubleSpinBox:focus {{
                border: 1px solid {theme.MAGENTA.name()};
            }}
            QComboBox QAbstractItemView {{
                background: {popup_bg};
                color: {text};
                selection-background-color: {mag_rgba_checked};
                border: 1px solid {base_border};
            }}
            QComboBox::drop-down {{ width: 24px; border: none; }}
            QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{
                background: transparent; border: none; width: 16px;
            }}
            QAbstractSpinBox::up-arrow, QAbstractSpinBox::down-arrow {{ width: 8px; height: 8px; }}
        """
        for w in (
            getattr(self, "add_wallet_name", None),
            getattr(self, "add_wallet_amount", None),
            getattr(self, "add_wallet_currency", None),
            getattr(self, "transfer_sender_combo", None),
            getattr(self, "transfer_receiver_combo", None),
            getattr(self, "transfer_amount", None),
            getattr(self, "edit_wallet_select", None),
            getattr(self, "edit_wallet_name", None),
            getattr(self, "edit_wallet_amount", None),
            getattr(self, "edit_wallet_currency", None),
            getattr(self, "remove_wallet_combo", None),
        ):
            if w:
                w.setStyleSheet(inputs_qss)

        # Restyle live table with theme
        if self._summary_table is not None:
            self._style_table(self._summary_table)
            self._summary_table.viewport().update()


# ---------- Soft halo painter for the middle section (magenta + cool blue) ----------
class WalletsHaloPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("background: transparent;")
        on_theme_changed(lambda *_: self.update())  # repaint when theme changes

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
