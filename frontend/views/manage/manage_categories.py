# frontend/views/manage/manage_categories.py
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QSizePolicy,
    QPushButton, QLabel, QButtonGroup,
    QTableWidget, QTableWidgetItem, QHeaderView, QDialog, QStackedWidget,
    QLineEdit, QDoubleSpinBox, QComboBox, QMessageBox
)
from PySide6.QtCore import Qt, Signal, QLocale
from PySide6.QtGui import QColor, QPainter, QRadialGradient

import inspect

# Data (backend unchanged)
from backend.crud.categories import get_all_categories  # (id, name, limit_amount, type, currency)

# Theme API (live updates without changing backend/layout)
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


class ManageCategoriesPage(QWidget):
    # Cross-navigation signals to sibling manage pages
    navigateExpenses  = Signal()
    navigateWallets   = Signal()
    navigateGoals     = Signal()

    def __init__(self, initial_toggle_key: int = 1):
        super().__init__()
        self.toggle_key = initial_toggle_key

        self._boxes_by_page: dict[int, list[QFrame]] = {}
        self._armed_action  = None  # "add" | "edit" | "remove"

        # Keep references to labels/buttons we recolor on theme change
        self._themed_labels: list[QLabel] = []
        self._nav_buttons: list[QPushButton] = []
        self._action_buttons: list[QPushButton] = []

        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setMinimumSize(1000, 700)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # ---------- Root layout (transparent gutters + halo center) ----------
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.left_section   = QFrame(); self.left_section.setStyleSheet("background: transparent;")
        self.middle_section = CategoriesHaloPanel()
        self.right_section  = QFrame(); self.right_section.setStyleSheet("background: transparent;")

        self._populate_middle(self.middle_section)

        row_layout = QHBoxLayout()
        row_layout.setContentsMargins(16, 16, 16, 16)
        row_layout.setSpacing(16)
        row_layout.addWidget(self.left_section, 2)
        row_layout.addWidget(self.middle_section, 6)
        row_layout.addWidget(self.right_section, 2)
        main_layout.addLayout(row_layout)

        # Initial theme pass + subscribe to changes
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

        def _nav_btn_qss():
            t = current_theme()
            if t.variant == "light":
                base_bg   = "rgba(0,0,0,0.06)"
                hover_bg  = "rgba(0,0,0,0.12)"
                base_brd  = "rgba(0,0,0,0.10)"
                hover_brd = "rgba(0,0,0,0.18)"
            else:
                base_bg   = "rgba(8,10,18,0.58)"
                hover_bg  = "rgba(255,255,255,0.10)"
                base_brd  = "rgba(255,255,255,0.10)"
                hover_brd = "rgba(255,255,255,0.18)"
            mag = t.MAGENTA
            sel_bg = f"rgba({mag.red()},{mag.green()},{mag.blue()},0.35)"
            sel_bd = mag.name()
            return f"""
                QPushButton {{
                    background: {base_bg};
                    border: 1px solid {base_brd};
                    border-radius: 12px;
                    padding: 8px 14px;
                    margin: 0px;
                    font-size: 13px;
                    font-weight: 600;
                    color: {t.TEXT};
                }}
                QPushButton:hover {{
                    background: {hover_bg};
                    border-color: {hover_brd};
                }}
                QPushButton:checked {{
                    background: {sel_bg};
                    border-color: {sel_bd};
                }}
            """

        def make_primary_btn(text: str) -> QPushButton:
            b = QPushButton(text)
            b.setCheckable(True)
            b.setMinimumHeight(40)
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            b.setStyleSheet(_nav_btn_qss())
            self._nav_buttons.append(b)
            return b

        self.btn_nav_expenses  = make_primary_btn("Expenses")
        self.btn_nav_wallets   = make_primary_btn("Wallets")
        self.btn_nav_categories= make_primary_btn("Categories")
        self.btn_nav_goals     = make_primary_btn("Goals")

        nav_group = QButtonGroup(self)
        nav_group.setExclusive(True)
        for b in (self.btn_nav_expenses, self.btn_nav_wallets, self.btn_nav_categories, self.btn_nav_goals):
            nav_group.addButton(b)
        self.btn_nav_categories.setChecked(True)

        self.btn_nav_expenses.clicked.connect(lambda *_: self.navigateExpenses.emit())
        self.btn_nav_wallets.clicked.connect(lambda *_: self.navigateWallets.emit())
        self.btn_nav_goals.clicked.connect(lambda *_: self.navigateGoals.emit())

        top_buttons_row.addWidget(self.btn_nav_expenses, 1)
        top_buttons_row.addWidget(self.btn_nav_wallets, 1)
        top_buttons_row.addWidget(self.btn_nav_categories, 1)
        top_buttons_row.addWidget(self.btn_nav_goals, 1)

        # === SECOND: action toggles (arm & fire) ===
        actions_row = QHBoxLayout()
        actions_row.setContentsMargins(0, 0, 0, 0)
        actions_row.setSpacing(12)
        layout.addLayout(actions_row)
        actions_row.addStretch(1)

        def _toggle_btn_qss():
            t = current_theme()
            if t.variant == "light":
                base_bg   = "rgba(0,0,0,0.06)"
                base_brd  = "rgba(0,0,0,0.10)"
                hover_bg  = "rgba(0,0,0,0.12)"
            else:
                base_bg   = "rgba(12,14,22,0.50)"
                base_brd  = "rgba(255,255,255,0.10)"
                hover_bg  = "rgba(255,255,255,0.10)"
            acc = t.ACCENT_BLUE
            sel_bg = f"rgba({acc.red()},{acc.green()},{acc.blue()},0.32)"
            sel_bd = acc.name()
            return f"""
                QPushButton {{
                    background: {base_bg};
                    border: 1px solid {base_brd};
                    border-radius: 10px;
                    padding: 3px 10px;
                    font-size: 12px;
                    color: {t.TEXT};
                }}
                QPushButton:hover {{ background: {hover_bg}; }}
                QPushButton:checked {{
                    background: {sel_bg};
                    border-color: {sel_bd};
                }}
            """

        def make_toggle(text: str) -> ActionButton:
            tbtn = ActionButton(text)
            tbtn.setMinimumHeight(30)
            tbtn.setStyleSheet(_toggle_btn_qss())
            self._action_buttons.append(tbtn)
            return tbtn

        self.btn_add_category    = make_toggle("Add category")
        self.btn_edit_category   = make_toggle("Edit category")
        self.btn_remove_category = make_toggle("Remove category")

        actions_row.addWidget(self.btn_add_category,    0, Qt.AlignRight)
        actions_row.addWidget(self.btn_edit_category,   0, Qt.AlignRight)
        actions_row.addWidget(self.btn_remove_category, 0, Qt.AlignRight)

        self.actions_group = QButtonGroup(self)
        self.actions_group.setExclusive(True)
        for b in (self.btn_add_category, self.btn_edit_category, self.btn_remove_category):
            self.actions_group.addButton(b)

        # === THIRD: two glass panels ===
        panels_row = QHBoxLayout()
        panels_row.setContentsMargins(0, 0, 0, 0)
        panels_row.setSpacing(16)
        layout.addLayout(panels_row, 1)

        # Panel A — summary table
        self.panelA = QFrame()
        self.panelA.setProperty("kind", "glassDeep")
        self.panelA.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        vA = QVBoxLayout(self.panelA)
        vA.setContentsMargins(16, 12, 16, 12)
        vA.setSpacing(8)

        lblA = QLabel("Categories")
        self._themed_labels.append(lblA)
        vA.addWidget(lblA)

        self.table_summary = QTableWidget()
        self._style_table(self.table_summary)
        self.table_summary.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._build_summary_table()
        vA.addWidget(self.table_summary, 1)

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

        # Build action pages (layout-based mini boxes)
        self.page_add    = self._build_action_page(4)  # Name, Limit, Type, Currency
        self.page_edit   = self._build_action_page(5)  # Select, New name, New limit, New type, New currency
        self.page_remove = self._build_action_page(1)  # Select

        self.panelBStack.addWidget(self.page_add)     # idx 0
        self.panelBStack.addWidget(self.page_edit)    # idx 1
        self.panelBStack.addWidget(self.page_remove)  # idx 2

        # Default state
        self.panelBStack.setCurrentIndex(0)
        self.btn_add_category.setChecked(True)
        self._armed_action = "add"

        # Drop inputs into the boxes
        self._build_add_inputs()
        self._build_edit_inputs()
        self._build_remove_inputs()

        # Arm-or-fire wiring
        self.btn_add_category.clicked.connect(   lambda *_: self._arm_or_fire("add",    0))
        self.btn_edit_category.clicked.connect(  lambda *_: self._arm_or_fire("edit",   1))
        self.btn_remove_category.clicked.connect(lambda *_: self._arm_or_fire("remove", 2))

        self.btn_add_category.doubleClicked.connect(   lambda *_: self._execute_action("add"))
        self.btn_edit_category.doubleClicked.connect(  lambda *_: self._execute_action("edit"))
        self.btn_remove_category.doubleClicked.connect(lambda *_: self._execute_action("remove"))

        panels_row.addWidget(self.panelA, 1)
        panels_row.addWidget(self.panelB, 1)

    # ---------- Compact glass mini boxes (TOP-ALIGNED) ----------
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
        self._themed_labels.append(lbl)  # recolor on theme change
        parent_lay.addWidget(lbl)

        # Sizing only; theme styles are applied centrally in _apply_theme_colors
        widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        widget.setMinimumHeight(32)
        widget.setMaximumHeight(36)

        parent_lay.addWidget(widget, 0)

    # ---------- Common data helpers ----------
    def _fetch_categories(self):
        """(id, name, limit_amount, type, currency)"""
        rows = get_all_categories()
        return rows if rows else []

    def _load_categories_into_combo(self, combo: QComboBox):
        combo.clear()
        rows = self._fetch_categories()
        rows.sort(key=lambda r: (r[1] or "").lower())
        for cid, name, *_rest in rows:
            combo.addItem("" if name is None else str(name), int(cid))

    # ---------- Arm & Fire ----------
    def _arm_or_fire(self, action_key: str, stack_index: int):
        if self._armed_action != action_key:
            self.panelBStack.setCurrentIndex(stack_index)
            self._armed_action = action_key
        else:
            self._execute_action(action_key)

    def _execute_action(self, action_key: str):
        if action_key == "add":
            name = (self.add_name_input.text() or "").strip()
            if not name:
                QMessageBox.warning(self, "Missing name", "Please enter a category name.")
                return
            limit_amount = float(self.add_limit_input.value() or 0.0)
            category_type = self.add_type_combo.currentData(Qt.UserRole)
            if category_type is None:
                category_type = 0  # Non-fixed
            currency = self.add_currency_combo.currentData(Qt.UserRole)
            if not currency:
                currency = "EUR"
            self._add_category_backend(name, limit_amount, int(category_type), str(currency))

        elif action_key == "edit":
            cid = self.edit_select_combo.currentData(Qt.UserRole) if hasattr(self, "edit_select_combo") else None
            if cid is None:
                QMessageBox.warning(self, "No category selected", "Please choose a category to edit.")
                return
            new_name = (self.edit_name_input.text() or "").strip()
            if not new_name:
                QMessageBox.warning(self, "Missing name", "Name cannot be empty.")
                return
            new_limit_amount = float(self.edit_limit_input.value())
            new_type = self.edit_type_combo.currentData(Qt.UserRole)
            if new_type is None:
                new_type = 0
            new_currency = self.edit_currency_combo.currentData(Qt.UserRole)
            if not new_currency:
                new_currency = "EUR"
            self._edit_category_backend(int(cid), new_name, new_limit_amount, int(new_type), str(new_currency))

        elif action_key == "remove":
            if not hasattr(self, "remove_category_combo"):
                QMessageBox.warning(self, "Unavailable", "The remove selector is not available.")
                return
            cid = self.remove_category_combo.currentData(Qt.UserRole)
            name = self.remove_category_combo.currentText()
            if cid is None:
                QMessageBox.warning(self, "No category selected", "Please choose a category to remove.")
                return
            self._remove_category_backend(int(cid), name)

    # ---------- ADD (4 boxes) ----------
    def _build_add_inputs(self):
        boxes = self._boxes_by_page.get(id(self.page_add), [])
        if len(boxes) < 4:
            return

        # 1) Name
        self.add_name_input = QLineEdit()
        self.add_name_input.setPlaceholderText("e.g., Groceries")
        lay1 = self._box_layout(boxes[0])
        self._labeled(lay1, "Name", self.add_name_input)

        # 2) Limit
        self.add_limit_input = QDoubleSpinBox()
        self.add_limit_input.setDecimals(2)
        self.add_limit_input.setRange(0.00, 1_000_000_000.00)
        self.add_limit_input.setSingleStep(1.00)
        self.add_limit_input.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.add_limit_input.setLocale(QLocale.c())            # force decimal point
        self.add_limit_input.setGroupSeparatorShown(False)
        lay2 = self._box_layout(boxes[1])
        self._labeled(lay2, "Limit", self.add_limit_input)

        # 3) Type
        self.add_type_combo = QComboBox()
        self.add_type_combo.addItem("Fixed", 1)
        self.add_type_combo.addItem("Non-fixed", 0)
        lay3 = self._box_layout(boxes[2])
        self._labeled(lay3, "Type", self.add_type_combo)

        # 4) Currency
        self.add_currency_combo = QComboBox()
        for c in ("EUR", "MXN", "USD"):
            self.add_currency_combo.addItem(c, c)
        lay4 = self._box_layout(boxes[3])
        self._labeled(lay4, "Currency", self.add_currency_combo)

    # ---------- EDIT (5 boxes) ----------
    def _build_edit_inputs(self):
        boxes = self._boxes_by_page.get(id(self.page_edit), [])
        if len(boxes) < 5:
            return

        # 1) Choose category
        self.edit_select_combo = QComboBox()
        self._load_categories_into_combo(self.edit_select_combo)
        lay1 = self._box_layout(boxes[0])
        self._labeled(lay1, "Choose category", self.edit_select_combo)

        # 2) New name
        self.edit_name_input = QLineEdit()
        lay2 = self._box_layout(boxes[1])
        self._labeled(lay2, "New name", self.edit_name_input)

        # 3) New limit
        self.edit_limit_input = QDoubleSpinBox()
        self.edit_limit_input.setDecimals(2)
        self.edit_limit_input.setRange(0.00, 1_000_000_000.00)
        self.edit_limit_input.setSingleStep(1.00)
        self.edit_limit_input.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.edit_limit_input.setLocale(QLocale.c())           # force decimal point
        self.edit_limit_input.setGroupSeparatorShown(False)
        lay3 = self._box_layout(boxes[2])
        self._labeled(lay3, "New limit", self.edit_limit_input)

        # 4) New type
        self.edit_type_combo = QComboBox()
        self.edit_type_combo.addItem("Fixed", 1)
        self.edit_type_combo.addItem("Non-fixed", 0)
        lay4 = self._box_layout(boxes[3])
        self._labeled(lay4, "New type", self.edit_type_combo)

        # 5) New currency
        self.edit_currency_combo = QComboBox()
        for c in ("EUR", "MXN", "USD"):
            self.edit_currency_combo.addItem(c, c)
        lay5 = self._box_layout(boxes[4])
        self._labeled(lay5, "New currency", self.edit_currency_combo)

        # Prefill values when selection changes
        self.edit_select_combo.currentIndexChanged.connect(self._on_edit_category_changed)
        self._on_edit_category_changed(self.edit_select_combo.currentIndex())

    def _on_edit_category_changed(self, _idx: int):
        if not hasattr(self, "edit_select_combo"):
            return
        cid = self.edit_select_combo.currentData(Qt.UserRole)
        if cid is None:
            return

        rows = self._fetch_categories()
        row = next((r for r in rows if r[0] == cid), None)
        if row is None:
            return

        _id, name, limit_amount, type_flag, currency = row

        self.edit_name_input.setText("" if name is None else str(name))
        try:
            self.edit_limit_input.setValue(0.0 if limit_amount is None else float(limit_amount))
        except Exception:
            self.edit_limit_input.setValue(0.0)

        self.edit_type_combo.setCurrentIndex(0 if type_flag == 1 else 1)

        cur = "" if currency is None else str(currency)
        found = self.edit_currency_combo.findText(cur, Qt.MatchExactly)
        self.edit_currency_combo.setCurrentIndex(found if found >= 0 else 0)

    # ---------- REMOVE (1 box) ----------
    def _build_remove_inputs(self):
        boxes = self._boxes_by_page.get(id(self.page_remove), [])
        if len(boxes) < 1:
            return

        self.remove_category_combo = QComboBox()
        self._load_categories_into_combo(self.remove_category_combo)

        lay = self._box_layout(boxes[0])
        self._labeled(lay, "Select category", self.remove_category_combo)

    # ---------- Tables ----------
    def _style_table(self, table: QTableWidget):
        """Apply theme-aware table stylesheet."""
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

    def _build_summary_table(self):
        rows = self._fetch_categories()

        self.table_summary.clear()
        self.table_summary.setColumnCount(2)
        self.table_summary.setHorizontalHeaderLabels(["Name", "Type"])
        self.table_summary.setRowCount(len(rows))
        self.table_summary.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_summary.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_summary.setAlternatingRowColors(True)
        self.table_summary.verticalHeader().setVisible(False)
        self.table_summary.setWordWrap(False)

        for r, row in enumerate(rows):
            name = "" if row[1] is None else str(row[1])
            cat_type = "Fixed" if (row[3] == 1) else "Non-fixed"
            self.table_summary.setItem(r, 0, QTableWidgetItem(name))
            self.table_summary.setItem(r, 1, QTableWidgetItem(cat_type))

        hdr = self.table_summary.horizontalHeader()
        hdr.setMinimumSectionSize(80)
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)          # Name fills
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents) # Type compact

    def _open_full_dialog(self):
        rows = self._fetch_categories()

        dlg = QDialog(self)
        dlg.setWindowTitle("All categories (full)")
        dlg.resize(720, 420)
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

        headers = ["Name", "Limit", "Type", "Currency"]
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setRowCount(len(rows))

        for r, row in enumerate(rows):
            name      = "" if row[1] is None else str(row[1])
            limit_str = "" if row[2] is None else f"{row[2]:.2f}"
            type_str  = "Fixed" if (row[3] == 1) else "Non-fixed"
            currency  = "" if row[4] is None else str(row[4])

            table.setItem(r, 0, QTableWidgetItem(name))
            table.setItem(r, 1, QTableWidgetItem(limit_str))
            table.setItem(r, 2, QTableWidgetItem(type_str))
            table.setItem(r, 3, QTableWidgetItem(currency))

        hdr = table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)          # Name
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents) # Limit
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents) # Type
        hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents) # Currency

        lay.addWidget(table, 1)

        close_row = QHBoxLayout()
        close_row.addStretch(1)
        btn_close = QPushButton("Close")
        close_row.addWidget(btn_close)
        lay.addLayout(close_row)

        # Theme dialog controls
        self._style_table(table)
        self._style_dialog_buttons([btn_close])

        btn_close.clicked.connect(dlg.accept)
        dlg.exec()

    # Toggle support (parity with other pages)
    def apply_toggle(self, key: int):
        if key == self.toggle_key:
            return
        self.toggle_key = key

    # ---------- Theme plumbing ----------
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
        """Update inline label colors, tables, inputs, and button chips to match active theme."""
        # Labels
        try:
            for lbl in self._themed_labels:
                lbl.setStyleSheet(f"font-size:12px; font-weight:600; color:{theme.TEXT};")
        except Exception:
            pass

        # Tables
        try:
            if hasattr(self, "table_summary"):
                self._style_table(self.table_summary)
                self.table_summary.viewport().update()
        except Exception:
            pass

        # Nav chips (Expenses / Wallets / Categories / Goals)
        try:
            if self._nav_buttons:
                if theme.variant == "light":
                    base_bg   = "rgba(0,0,0,0.06)"
                    hover_bg  = "rgba(0,0,0,0.12)"
                    base_brd  = "rgba(0,0,0,0.10)"
                    hover_brd = "rgba(0,0,0,0.18)"
                else:
                    base_bg   = "rgba(8,10,18,0.58)"
                    hover_bg  = "rgba(255,255,255,0.10)"
                    base_brd  = "rgba(255,255,255,0.10)"
                    hover_brd = "rgba(255,255,255,0.18)"
                mag = theme.MAGENTA
                sel_bg = f"rgba({mag.red()},{mag.green()},{mag.blue()},0.35)"
                sel_bd = mag.name()
                qss = f"""
                    QPushButton {{
                        background: {base_bg};
                        border: 1px solid {base_brd};
                        border-radius: 12px;
                        padding: 8px 14px;
                        margin: 0px;
                        font-size: 13px;
                        font-weight: 600;
                        color: {theme.TEXT};
                    }}
                    QPushButton:hover {{
                        background: {hover_bg};
                        border-color: {hover_brd};
                    }}
                    QPushButton:checked {{
                        background: {sel_bg};
                        border-color: {sel_bd};
                    }}
                """
                for b in self._nav_buttons:
                    b.setStyleSheet(qss)
        except Exception:
            pass

        # Action toggles (Add / Edit / Remove)
        try:
            if self._action_buttons:
                if theme.variant == "light":
                    base_bg   = "rgba(0,0,0,0.06)"
                    base_brd  = "rgba(0,0,0,0.10)"
                    hover_bg  = "rgba(0,0,0,0.12)"
                else:
                    base_bg   = "rgba(12,14,22,0.50)"
                    base_brd  = "rgba(255,255,255,0.10)"
                    hover_bg  = "rgba(255,255,255,0.10)"
                acc = theme.ACCENT_BLUE
                sel_bg = f"rgba({acc.red()},{acc.green()},{acc.blue()},0.32)"
                sel_bd = acc.name()
                qss = f"""
                    QPushButton {{
                        background: {base_bg};
                        border: 1px solid {base_brd};
                        border-radius: 10px;
                        padding: 3px 10px;
                        font-size: 12px;
                        color: {theme.TEXT};
                    }}
                    QPushButton:hover {{ background: {hover_bg}; }}
                    QPushButton:checked {{
                        background: {sel_bg};
                        border-color: {sel_bd};
                    }}
                """
                for b in self._action_buttons:
                    b.setStyleSheet(qss)
        except Exception:
            pass

        # Inputs (theme-aware, applied centrally)
        try:
            if theme.variant == "light":
                input_bg    = "rgba(255,255,255,0.75)"
                base_border = "rgba(0,0,0,0.10)"
                popup_bg    = "rgba(255,255,255,0.98)"
            else:
                input_bg    = "rgba(6,8,14,0.66)"
                base_border = "rgba(255,255,255,0.10)"
                popup_bg    = "rgba(12,14,22,0.95)"
            sel_rgba = f"rgba({theme.MAGENTA.red()},{theme.MAGENTA.green()},{theme.MAGENTA.blue()},0.35)"
            focus_color = theme.MAGENTA.name()
            inputs_qss = f"""
                QLineEdit, QComboBox, QDoubleSpinBox {{
                    background: {input_bg};
                    color: {theme.TEXT};
                    border: 1px solid {base_border};
                    border-radius: 10px;
                    padding: 5px 10px;
                    min-height: 32px;
                    max-height: 36px;
                    selection-background-color: {sel_rgba};
                    selection-color: {theme.TEXT};
                }}
                QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus {{
                    border: 1px solid {focus_color};
                }}
                QComboBox QAbstractItemView {{
                    background: {popup_bg};
                    color: {theme.TEXT};
                    selection-background-color: {sel_rgba};
                    border: 1px solid {base_border};
                }}
                QComboBox::drop-down {{ width: 24px; border: none; }}
                QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{
                    background: transparent; border: none; width: 16px;
                }}
                QAbstractSpinBox::up-arrow, QAbstractSpinBox::down-arrow {{ width: 8px; height: 8px; }}
            """
            for w in (
                getattr(self, "add_name_input", None),
                getattr(self, "add_limit_input", None),
                getattr(self, "add_type_combo", None),
                getattr(self, "add_currency_combo", None),
                getattr(self, "edit_select_combo", None),
                getattr(self, "edit_name_input", None),
                getattr(self, "edit_limit_input", None),
                getattr(self, "edit_type_combo", None),
                getattr(self, "edit_currency_combo", None),
                getattr(self, "remove_category_combo", None),
            ):
                if w:
                    w.setStyleSheet(inputs_qss)
        except Exception:
            pass

    # ---------- Backend bridges (no backend changes; safe imports) ----------
    @staticmethod
    def _filtered_call(fn, **kwargs):
        """
        Call backend `fn` with only the kwargs it actually accepts.
        Also supports common aliasing:
          - category_type -> type
          - new_limit_amount -> new_limit
        """
        sig = None
        try:
            sig = inspect.signature(fn)
        except Exception:
            # best-effort fallback
            return fn(**kwargs)

        params = set(sig.parameters.keys())
        call_kwargs = {k: v for k, v in kwargs.items() if k in params}

        # Alias shims if needed
        if "category_type" in kwargs and "category_type" not in params and "type" in params:
            call_kwargs["type"] = kwargs["category_type"]
        if "new_limit_amount" in kwargs and "new_limit_amount" not in params and "new_limit" in params:
            call_kwargs["new_limit"] = kwargs["new_limit_amount"]

        return fn(**call_kwargs)

    def _add_category_backend(self, name, limit_amount, category_type, currency):
        """
        Preferred: backend.crud.categories.add_category(name, limit_amount, category_type, currency)
        Fallback:  try backend.high_level.analysis.add_category (param shim handled).
        """
        _fn = None
        try:
            from backend.crud.categories import add_category as _fn  # preferred
        except Exception:
            try:
                from backend.high_level.analysis import add_category as _fn  # fallback if present
            except Exception:
                _fn = None

        if _fn is None:
            QMessageBox.information(
                self, "Not wired yet",
                "Inputs captured successfully.\n\n"
                "Expose add_category(...) in your backend to enable this action."
            )
            return

        try:
            self._filtered_call(
                _fn,
                name=name,
                limit_amount=limit_amount,
                category_type=category_type,
                currency=currency,
            )
            QMessageBox.information(self, "Category added", f"Added “{name}”.")
            self._build_summary_table()
            # refresh combos if present
            for combo in ("edit_select_combo", "remove_category_combo"):
                if hasattr(self, combo):
                    self._load_categories_into_combo(getattr(self, combo))
        except Exception as e:
            QMessageBox.critical(self, "Error adding category", str(e))

    def _edit_category_backend(self, cid, new_name, new_limit_amount, new_type, new_currency):
        """
        Preferred: backend.crud.categories.edit_category(
            category_id, new_name, new_limit_amount, new_type, new_currency
        )
        Fallback supported with param shims.
        """
        _fn = None
        try:
            from backend.crud.categories import edit_category as _fn
        except Exception:
            try:
                from backend.high_level.analysis import edit_category as _fn
            except Exception:
                _fn = None

        if _fn is None:
            QMessageBox.information(
                self, "Not wired yet",
                "Inputs captured successfully.\n\n"
                "Expose edit_category(...) in your backend to enable this action."
            )
            return

        try:
            self._filtered_call(
                _fn,
                category_id=cid,
                new_name=new_name,
                new_limit_amount=new_limit_amount,
                new_type=new_type,
                new_currency=new_currency,
            )
            QMessageBox.information(self, "Category updated", "Category updated successfully.")
            self._build_summary_table()
            # reload combos to reflect changes
            for combo in ("edit_select_combo", "remove_category_combo"):
                if hasattr(self, combo):
                    self._load_categories_into_combo(getattr(self, combo))
        except Exception as e:
            QMessageBox.critical(self, "Error updating category", str(e))

    def _remove_category_backend(self, cid, name):
        """
        Preferred: backend.crud.categories.remove_category(category_id)
        Fallback supported.
        """
        _fn = None
        try:
            from backend.crud.categories import remove_category as _fn
        except Exception:
            try:
                from backend.high_level.analysis import remove_category as _fn
            except Exception:
                _fn = None

        if _fn is None:
            QMessageBox.information(
                self, "Not wired yet",
                "Selection captured successfully.\n\n"
                "Expose remove_category(...) in your backend to enable this action."
            )
            return

        try:
            self._filtered_call(_fn, category_id=cid)
            QMessageBox.information(self, "Category removed", f"Removed “{name}”.")
            self._build_summary_table()
            # refresh selectors
            for combo in ("edit_select_combo", "remove_category_combo"):
                if hasattr(self, combo):
                    self._load_categories_into_combo(getattr(self, combo))
        except Exception as e:
            QMessageBox.critical(self, "Error removing category", str(e))


# ---------- Soft halo painter (magenta + cool blue) ----------
class CategoriesHaloPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("background: transparent;")
        # Repaint when theme changes
        on_theme_changed(lambda *_: self.update())

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
