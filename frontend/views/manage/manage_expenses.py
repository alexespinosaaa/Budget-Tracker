# frontend/views/manage/manage_expenses.py
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QSizePolicy,
    QGraphicsDropShadowEffect, QPushButton, QLabel, QButtonGroup,
    QTableWidget, QTableWidgetItem, QHeaderView, QDialog, QStackedWidget,
    QLineEdit, QDoubleSpinBox, QDateEdit, QComboBox, QTextEdit, QMessageBox,
    QStackedLayout, QGraphicsOpacityEffect
)
from PySide6.QtCore import Qt, Signal, QEvent, QTimer, QDate, QLocale, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QColor, QPainter, QRadialGradient

# Data helpers
from backend.crud.expenses import ordeBy  # option 5 = order by date DESC
from backend.db import get_connection
from backend.crud.wallets import get_wallet_by_id

# Theme API (live updates without touching backend/layout)
from frontend.theme import current_theme, on_theme_changed


# ---------- Small helper to support double-click on action buttons ----------
class ActionButton(QPushButton):
    """
    A small QPushButton subclass that:
      - is checkable (reflects 'armed' state)
      - emits "doubleClicked" when double-clicked
    """
    doubleClicked = Signal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setCheckable(True)

    def event(self, e):
        if e.type() == QEvent.MouseButtonDblClick:
            self.doubleClicked.emit()
            return True
        return super().event(e)


class ManageExpensesPage(QWidget):
    # Fire these to let main.py switch pages
    navigateWallets    = Signal()
    navigateCategories = Signal()
    navigateGoals      = Signal()

    # Emitted after a successful record/remove so other pages can refresh
    dataChanged = Signal()

    def __init__(self, initial_toggle_key: int = 1):
        super().__init__()
        self.toggle_key = initial_toggle_key
        self._armed_action = None  # "record" or "remove"

        # inputs (filled in _build_record_inputs)
        self.input_name = None
        self.input_cost = None
        self.input_date = None
        self.input_category = None
        self.input_wallet = None
        self.input_description = None

        # remove UI state
        self.remove_combo = None
        self.remove_hint = None
        self._remove_selected_id = None
        self._REMOVE_SHOW_ALL = -999999  # sentinel for "Show all..."

        # keep handles for theme-updated labels
        self._themed_labels: list[QLabel] = []

        # summary table swap state (Overview-like)
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
        self.middle_section = ManageHaloPanel()
        self.right_section  = QFrame(); self.right_section.setStyleSheet("background: transparent;")

        self._populate_middle(self.middle_section)

        row_layout = QHBoxLayout()
        row_layout.setContentsMargins(16, 16, 16, 16)
        row_layout.setSpacing(16)
        row_layout.addWidget(self.left_section, 2)
        row_layout.addWidget(self.middle_section, 6)
        row_layout.addWidget(self.right_section, 2)
        main_layout.addLayout(row_layout)

        # Initial theme pass + subscribe to live changes
        self._apply_theme_colors(current_theme())
        on_theme_changed(self._apply_theme_colors)

    def _create_colored_section(self, color: str, shadow: bool = False) -> QFrame:
        # Kept for compatibility; now returns a transparent section
        frame = QFrame()
        frame.setStyleSheet("background: transparent;")
        frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # No heavy shadows; background glow handles depth
        return frame

    def _populate_middle(self, parent: QFrame):
        layout = QVBoxLayout(parent)
        # Reduce top reserve for the overlay title (was 110)
        layout.setContentsMargins(24, 84, 24, 24)
        layout.setSpacing(12)  # tighter vertical rhythm

        # === TOP: big nav chips (glass lozenges) ===
        top_buttons_row = QHBoxLayout()
        top_buttons_row.setContentsMargins(0, 0, 0, 0)
        top_buttons_row.setSpacing(12)
        layout.addLayout(top_buttons_row)

        def make_primary_btn(text: str) -> QPushButton:
            b = QPushButton(text)
            b.setCheckable(True)
            b.setMinimumHeight(40)  # was 48
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            return b  # stylesheet applied in _apply_theme_colors
        self.btn_expenses   = make_primary_btn("Expenses")
        self.btn_wallets    = make_primary_btn("Wallets")
        self.btn_categories = make_primary_btn("Categories")
        self.btn_goals      = make_primary_btn("Goals")

        group = QButtonGroup(self)
        group.setExclusive(True)
        for b in (self.btn_expenses, self.btn_wallets, self.btn_categories, self.btn_goals):
            group.addButton(b)
        self.btn_expenses.setChecked(True)

        # Cross-navigation signals
        self.btn_wallets.clicked.connect(lambda *_: self.navigateWallets.emit())
        self.btn_categories.clicked.connect(lambda *_: self.navigateCategories.emit())
        self.btn_goals.clicked.connect(lambda *_: self.navigateGoals.emit())

        top_buttons_row.addWidget(self.btn_expenses,   1)
        top_buttons_row.addWidget(self.btn_wallets,    1)
        top_buttons_row.addWidget(self.btn_categories, 1)
        top_buttons_row.addWidget(self.btn_goals,      1)

        # === SECOND: small action toggles (glass) ===
        actions_row = QHBoxLayout()
        actions_row.setContentsMargins(0, 0, 0, 0)
        actions_row.setSpacing(12)
        layout.addLayout(actions_row)
        actions_row.addStretch(1)

        def make_toggle(text: str) -> ActionButton:
            t = ActionButton(text)
            t.setMinimumHeight(30)  # was 32
            return t  # stylesheet applied in _apply_theme_colors
        self.btn_record = make_toggle("Record expense")
        self.btn_remove = make_toggle("Remove expense")
        actions_row.addWidget(self.btn_record, 0, Qt.AlignRight)
        actions_row.addWidget(self.btn_remove, 0, Qt.AlignRight)

        # Make the two action buttons mutually exclusive (only one armed)
        self.actions_group = QButtonGroup(self)
        self.actions_group.setExclusive(True)
        for b in (self.btn_record, self.btn_remove):
            self.actions_group.addButton(b)

        # === THIRD: two panels (glass) ===
        panels_row = QHBoxLayout()
        panels_row.setContentsMargins(0, 0, 0, 0)
        panels_row.setSpacing(16)
        layout.addLayout(panels_row, 1)

        # Panel A (summary table) — wrap in stacked layout like Overview graph
        self.panelA = QFrame()
        self.panelA.setProperty("kind", "glassDeep")
        self.panelA.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        pA = QVBoxLayout(self.panelA)
        pA.setContentsMargins(16, 12, 16, 12)
        pA.setSpacing(8)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(8)
        lblA = QLabel("Recent expenses (last 14)")
        self._themed_labels.append(lblA)
        header_row.addWidget(lblA)
        header_row.addStretch(1)

        self.btn_view_full = QPushButton("View full")
        self.btn_view_full.setMinimumHeight(26)
        header_row.addWidget(self.btn_view_full, 0, Qt.AlignRight)
        pA.addLayout(header_row)

        # Stacked area for summary table (so we can fade-in updated table)
        summary_area = QFrame()
        self._summary_stack = QStackedLayout(summary_area)
        self._summary_stack.setContentsMargins(0, 0, 0, 0)
        self._summary_stack.setStackingMode(QStackedLayout.StackOne)

        # First mount with a lightweight empty table (instant)
        self._summary_table = self._make_summary_table_widget([])
        self._summary_stack.addWidget(self._summary_table)
        self._summary_stack.setCurrentWidget(self._summary_table)

        pA.addWidget(summary_area, 1)

        # Double-click or button opens full dialog
        self._connect_summary_signals(self._summary_table)
        self.btn_view_full.clicked.connect(self._open_full_dialog)

        # Panel B (stacked views)
        self.panelB = QFrame()
        self.panelB.setProperty("kind", "glassDeep")
        self.panelB.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._rebuild_panelB()  # builds record/remove pages + inputs

        panels_row.addWidget(self.panelA, 1)
        panels_row.addWidget(self.panelB, 1)

        # Arm-or-fire wiring for actions
        self.btn_record.clicked.connect(lambda: self._arm_or_fire("record", 0))
        self.btn_remove.clicked.connect(lambda: self._arm_or_fire("remove", 1))
        self.btn_record.doubleClicked.connect(lambda: self._execute_action("record"))
        self.btn_remove.doubleClicked.connect(lambda: self._execute_action("remove"))

        # Default — show Record view armed
        self.panelB_stack.setCurrentIndex(0)
        self.btn_record.setChecked(True)
        self._armed_action = "record"

    # ---------- Arm & Fire ----------
    def _arm_or_fire(self, action_key: str, stack_index: int):
        """
        First click on an action button 'arms' it (switches Panel B).
        Clicking the same armed button again 'fires' (executes) the action.
        """
        if self._armed_action != action_key:
            # Arm: switch and remember
            self.panelB_stack.setCurrentIndex(stack_index)
            self._armed_action = action_key
        else:
            # Fire the already-armed action
            self._execute_action(action_key)

    def _execute_action(self, action_key: str):
        """
        Execute the backend operation for the action.
        """
        if action_key == "record":
            data = self._collect_record_inputs()
            if data is None:
                return
            name, cost, date_str, category_id, wallet_id, description = data
            self._record_expense_backend(name, cost, date_str, category_id, wallet_id, description)
            # Refresh UI (smooth)
            self._refresh_from_db()
            self._emit_data_changed()
        elif action_key == "remove":
            # Resolve selected expense id (from dialog selection or combo)
            exp_id = None
            if self._remove_selected_id is not None:
                exp_id = self._remove_selected_id
            else:
                data = self.remove_combo.currentData(Qt.UserRole) if self.remove_combo else None
                if isinstance(data, int) and data != self._REMOVE_SHOW_ALL:
                    exp_id = data

            if exp_id is None:
                QMessageBox.warning(self, "No expense selected",
                                    "Please select an expense to remove.")
                return

            # Remove immediately (no confirmation dialog)
            self._remove_expense_backend(exp_id)

            # Refresh UI (smooth)
            self._refresh_from_db()
            self._remove_selected_id = None
            self._emit_data_changed()

    # ---------- Panel B builders ----------
    def _rebuild_panelB(self):
        """
        Panel B:
        - 'Record expense' → 6 compact boxes with actual inputs (no scroll).
        - 'Remove expense' → single compact box with selector UI inside.
        """
        SPACING = 12  # compact vertical spacing

        # Reset Panel B layout
        pB = QVBoxLayout(self.panelB)
        pB.setContentsMargins(SPACING, SPACING, SPACING, SPACING)
        pB.setSpacing(0)

        # Stacked content area
        self.panelB_stack = QStackedWidget(self.panelB)
        self.panelB_stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        pB.addWidget(self.panelB_stack)

        # --- Record view: 6 equal boxes with inputs (glass) ---
        record = QWidget()
        vrec = QVBoxLayout(record)
        vrec.setContentsMargins(0, 0, 0, 0)
        vrec.setSpacing(SPACING)

        # Build & add 6 input boxes (equal stretch ⇒ equal heights)
        b_name        = self._make_mini_box(); vrec.addWidget(b_name, 1)
        b_cost        = self._make_mini_box(); vrec.addWidget(b_cost, 1)
        b_date        = self._make_mini_box(); vrec.addWidget(b_date, 1)
        b_category    = self._make_mini_box(); vrec.addWidget(b_category, 1)
        b_wallet      = self._make_mini_box(); vrec.addWidget(b_wallet, 1)
        b_description = self._make_mini_box(); vrec.addWidget(b_description, 1)

        self._build_record_inputs(
            b_name, b_cost, b_date, b_category, b_wallet, b_description
        )

        self.panelB_stack.addWidget(record)

        # --- Remove view: 1 box with specified height + selector UI ---
        remove = QWidget()
        vrem = QVBoxLayout(remove)
        vrem.setContentsMargins(0, 0, 0, 0)
        vrem.setSpacing(SPACING)

        self.remove_box = self._make_mini_box()
        self.remove_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        vrem.addWidget(self.remove_box)
        vrem.addStretch(1)

        self.panelB_stack.addWidget(remove)

        # Build content inside remove box & load initial options
        self._build_remove_inputs(self.remove_box)
        self._load_remove_last10()

        # Keep remove box sized correctly as panelB resizes
        self.panelB.installEventFilter(self)
        self._size_remove_box()

    def _make_mini_box(self) -> QFrame:
        """
        Compact glass box that expands horizontally and keeps a reasonable min height.
        """
        box = QFrame()
        box.setObjectName("MiniBox")
        box.setProperty("kind", "glass")
        box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        box.setMinimumHeight(72)  # compact (was 84)
        return box

    # ---------- Record view: build inputs ----------
    def _box_layout(self, box: QFrame) -> QVBoxLayout:
        lay = QVBoxLayout(box)
        lay.setContentsMargins(12, 8, 12, 8)  # slightly tighter
        lay.setSpacing(6)
        return lay

    def _labeled(self, parent_lay: QVBoxLayout, title: str, widget: QWidget):
        lbl = QLabel(title)
        self._themed_labels.append(lbl)
        parent_lay.addWidget(lbl)

        # Input sizing; actual styles applied in _apply_theme_colors.
        from PySide6.QtWidgets import QTextEdit as _QTE
        if isinstance(widget, _QTE):
            widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            widget.setMinimumHeight(72)
            widget.setMaximumHeight(96)
        else:
            widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            widget.setMinimumHeight(32)
            widget.setMaximumHeight(36)

        parent_lay.addWidget(widget, 0)  # no vertical stretch

    def _build_record_inputs(self, b_name, b_cost, b_date, b_category, b_wallet, b_description):
        # Name
        self.input_name = QLineEdit()
        self.input_name.setPlaceholderText("e.g., Coffee")
        lay1 = self._box_layout(b_name)
        self._labeled(lay1, "Name", self.input_name)

        # Cost (force decimal point '.' regardless of OS locale)
        self.input_cost = QDoubleSpinBox()
        self.input_cost.setDecimals(2)
        self.input_cost.setRange(0.00, 1_000_000_000.00)
        self.input_cost.setSingleStep(0.50)
        self.input_cost.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.input_cost.setLocale(QLocale.c())           # C/English locale → dot as decimal separator
        self.input_cost.setGroupSeparatorShown(False)
        lay2 = self._box_layout(b_cost)
        self._labeled(lay2, "Cost", self.input_cost)

        # Date (QDateEdit)
        self.input_date = QDateEdit()
        self.input_date.setCalendarPopup(True)
        self.input_date.setDisplayFormat("yyyy-MM-dd")
        self.input_date.setDate(QDate.currentDate())
        lay3 = self._box_layout(b_date)
        self._labeled(lay3, "Date", self.input_date)

        # Category
        self.input_category = QComboBox()
        lay4 = self._box_layout(b_category)
        self._labeled(lay4, "Category", self.input_category)

        # Wallet
        self.input_wallet = QComboBox()
        lay5 = self._box_layout(b_wallet)
        self._labeled(lay5, "Wallet", self.input_wallet)

        # Description
        self.input_description = QTextEdit()
        self.input_description.setPlaceholderText("Optional notes…")
        self.input_description.setAcceptRichText(False)
        lay6 = self._box_layout(b_description)
        self._labeled(lay6, "Description", self.input_description)

        # Load options for category & wallet
        self._load_categories()
        self._load_wallets()

    # ---------- Remove view: build selector ----------
    def _build_remove_inputs(self, container: QFrame):
        lay = self._box_layout(container)

        self.remove_combo = QComboBox()
        self.remove_combo.setMinimumHeight(32)

        self._labeled(lay, "Select expense", self.remove_combo)
        self.remove_combo.currentIndexChanged.connect(self._on_remove_combo_changed)

        self.remove_hint = None  # keep UI minimal

    def _load_remove_last10(self):
        """Populate combo with last 10 expenses + trailing 'Show all…'."""
        if not self.remove_combo:
            return

        self.remove_combo.blockSignals(True)
        self.remove_combo.clear()
        self._remove_selected_id = None

        rows = ordeBy(5) or []  # newest first
        for row in rows[:10]:
            exp_id, name, category, cost, date_str, desc, wallet_id = row
            label = f"{(name or '')} | {(date_str or '')[:10]}"
            self.remove_combo.addItem(label, int(exp_id))

        # Add the sentinel "Show all…" option at the end
        self.remove_combo.addItem("Show all…", self._REMOVE_SHOW_ALL)

        if self.remove_combo.count() > 0:
            self.remove_combo.setCurrentIndex(0)

        self.remove_combo.blockSignals(False)

    def _on_remove_combo_changed(self, idx: int):
        if idx < 0:
            self._remove_selected_id = None
            return

        data = self.remove_combo.itemData(idx, Qt.UserRole)
        if data == self._REMOVE_SHOW_ALL:
            # Open the picker dialog; selection sets _remove_selected_id
            self._open_all_expenses_picker()
        elif isinstance(data, int):
            self._remove_selected_id = data

    def _open_all_expenses_picker(self):
        """Modal dialog to pick ANY expense (newest first)."""
        rows = ordeBy(5) or []  # newest first

        dlg = QDialog(self)
        dlg.setWindowTitle("Choose an expense to remove")
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
        headers = ["Name", "Cost", "Date"]
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setRowCount(len(rows))

        for r, row in enumerate(rows):
            exp_id, name, category, cost, date_str, desc, wallet_id = row
            name_item = QTableWidgetItem("" if name is None else str(name))
            name_item.setData(Qt.UserRole, int(exp_id))
            table.setItem(r, 0, name_item)
            table.setItem(r, 1, QTableWidgetItem("" if cost is None else f"{cost:.2f}"))
            table.setItem(r, 2, QTableWidgetItem("" if date_str is None else str(date_str)[:10]))

        hdr = table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)          # Name
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents) # Cost
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents) # Date

        lay.addWidget(table, 1)

        # Buttons
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        btn_cancel = QPushButton("Cancel")
        btn_select = QPushButton("Select")

        # theme-aware button styles added in _apply_theme_colors via findChildren
        buttons.addWidget(btn_cancel)
        buttons.addWidget(btn_select)
        lay.addLayout(buttons)

        def accept_current():
            idx = table.currentRow()
            if idx < 0:
                QMessageBox.warning(dlg, "No selection", "Please select an expense.")
                return
            dlg.accept()

        btn_cancel.clicked.connect(dlg.reject)
        btn_select.clicked.connect(accept_current)
        table.doubleClicked.connect(lambda *_: dlg.accept())

        # Apply theme styles to dialog buttons/tables now
        self._style_table(table)
        self._style_dialog_buttons([btn_cancel, btn_select])

        if dlg.exec() != QDialog.Accepted:
            # User cancelled → keep combo at first real item
            for i in range(self.remove_combo.count()):
                if self.remove_combo.itemData(i, Qt.UserRole) != self._REMOVE_SHOW_ALL:
                    self.remove_combo.setCurrentIndex(i)
                    break
            return

        # Extract chosen id & basic label
        row = table.currentRow()
        chosen_id = table.item(row, 0).data(Qt.UserRole)
        chosen_name = table.item(row, 0).text()
        chosen_date = table.item(row, 2).text()
        self._remove_selected_id = int(chosen_id)

        # If the id exists in the last10 list, select it; otherwise inject a temp item at top
        found_index = -1
        for i in range(self.remove_combo.count()):
            if self.remove_combo.itemData(i, Qt.UserRole) == self._remove_selected_id:
                found_index = i
                break

        if found_index >= 0:
            self.remove_combo.setCurrentIndex(found_index)
        else:
            label = f"{chosen_name} | {chosen_date} (selected)"
            self.remove_combo.insertItem(0, label, self._remove_selected_id)
            self.remove_combo.setCurrentIndex(0)

    # ---------- Option loaders ----------
    def _load_categories(self):
        self.input_category.clear()
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id, name FROM category ORDER BY name COLLATE NOCASE ASC")
            rows = cur.fetchall() or []
        for cid, name in rows:
            self.input_category.addItem("" if name is None else str(name), cid)

    def _load_wallets(self):
        self.input_wallet.clear()
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id, name FROM wallet ORDER BY name COLLATE NOCASE ASC")
            rows = cur.fetchall() or []
        for wid, name in rows:
            self.input_wallet.addItem("" if name is None else str(name), wid)

    # ---------- Collect & validate ----------
    def _collect_record_inputs(self):
        name = (self.input_name.text() or "").strip()
        if not name:
            QMessageBox.warning(self, "Missing name", "Please enter a name for the expense.")
            return None

        # QDoubleSpinBox.value() returns a float (already parsed using the spinbox locale).
        cost = float(self.input_cost.value() or 0.0)
        if cost <= 0.0:
            QMessageBox.warning(self, "Invalid cost", "Cost must be greater than 0.")
            return None

        # Read from QDateEdit in a normalized format the backend already accepts
        date_str = self.input_date.date().toString("yyyy-MM-dd")

        category_id = self.input_category.currentData(Qt.UserRole)
        if category_id is None:
            QMessageBox.warning(self, "Missing category", "Please choose a category.")
            return None

        wallet_id = self.input_wallet.currentData(Qt.UserRole)
        if wallet_id is None:
            QMessageBox.warning(self, "Missing wallet", "Please choose a wallet.")
            return None

        description = (self.input_description.toPlainText() or "").strip()

        return name, cost, date_str, int(category_id), int(wallet_id), description
    
    # ---------- Backend bridges ----------
    def _record_expense_backend(self, name, cost, date_str, category_id, wallet_id, description):
        """
        Calls your record_expense(...) function and reports status.
        """
        _fn = None
        try:
            from backend.crud.expenses import record_expense as _fn  # preferred path
        except Exception:
            try:
                from backend.high_level.analysis import record_expense as _fn  # fallback
            except Exception:
                _fn = None

        if _fn is None:
            QMessageBox.information(
                self,
                "Not wired yet",
                "Inputs captured successfully.\n\n"
                "Now wire your backend by exposing record_expense(...) in "
                "`backend.crud.expenses` (or update the import in "
                "`_record_expense_backend`)."
            )
            return

        try:
            _fn(
                name=name,
                cost=cost,
                date_str=date_str,
                category_id=category_id,
                wallet_id=wallet_id,
                description=description
            )
            QMessageBox.information(self, "Expense recorded",
                                    f"Recorded “{name}” for {cost:.2f} on {date_str}.")
            # Optional: clear inputs
            self.input_name.clear()
            self.input_cost.setValue(0.0)
            self.input_date.setDate(QDate.currentDate())
            self.input_description.clear()
        except Exception as e:
            QMessageBox.critical(self, "Error recording expense", str(e))

    def _remove_expense_backend(self, expense_id: int):
        """
        Directly call redo_expense(expense_id). Raises if import/call fails.
        """
        try:
            from backend.high_level.analysis import redo_expense
        except Exception as e:
            QMessageBox.critical(self, "Backend not available",
                                f"Could not import redo_expense: {e}")
            return

        try:
            redo_expense(expense_id)
            QMessageBox.information(self, "Expense removed",
                                    f"Expense ID {expense_id} was removed and the wallet balance restored.")
        except Exception as e:
            QMessageBox.critical(self, "Error removing expense", str(e))

    # ---------- Sizing helpers ----------
    def eventFilter(self, obj, event):
        if obj is self.panelB and event.type() == QEvent.Resize:
            self._size_remove_box()
        return super().eventFilter(obj, event)

    def _size_remove_box(self):
        """
        Set the single 'Remove expense' box height roughly to one sixth of available
        height (compact metrics), but never below the mini-box minimum.
        """
        if not hasattr(self, "remove_box") or self.remove_box is None:
            return
        total = self.panelB.height()
        # 2*outer margins (12) + 5 gaps between boxes (5*12) ≈ 84
        desired_h = max(72, (total - 84) // 6)
        self.remove_box.setFixedHeight(desired_h)

    # ---------- Data / UI builders ----------
    def _fetch_last10_rows(self):
        """
        Uses ordeBy(5) to get expenses ordered by date DESC.
        Columns returned by ordeBy(5):
          id, name, category(name or NULL), cost, date, description, wallet_id
        Returns the last 14 rows (newest first).
        """
        rows = ordeBy(5)  # newest first
        return rows[:14] if rows else []

    def _make_summary_table_widget(self, rows) -> QTableWidget:
        """Create a themed, populated QTableWidget (no side effects)."""
        table = QTableWidget()
        self._style_table(table)
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(["Name", "Cost", "Date"])
        table.setRowCount(len(rows))
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)

        # Faster fill: disable sorting & updates while populating
        table.setSortingEnabled(False)
        table.setUpdatesEnabled(False)
        for r, row in enumerate(rows):
            # row = (id, name, category, cost, date, description, wallet_id)
            name = row[1] if row[1] is not None else ""
            cost = f"{row[3]:.2f}" if row[3] is not None else ""
            date = row[4] if row[4] is not None else ""

            table.setItem(r, 0, QTableWidgetItem(str(name)))
            table.setItem(r, 1, QTableWidgetItem(str(cost)))
            table.setItem(r, 2, QTableWidgetItem(str(date)))
        table.setUpdatesEnabled(True)

        hdr = table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # Name
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # Cost
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # Date
        hdr.setStretchLastSection(False)
        return table

    def _connect_summary_signals(self, table: QTableWidget):
        table.doubleClicked.connect(self._open_full_dialog)

    def _fade_in_over_current(self, new_widget: QWidget, duration: int = 160):
        """Overview-like swap for the summary table."""
        if self._summary_stack is None:
            return
        old = self._summary_table

        # Ensure new widget is in the stack but not yet visible
        self._summary_stack.addWidget(new_widget)

        # Prepare fade on the new widget
        eff = QGraphicsOpacityEffect(new_widget)
        eff.setOpacity(0.0)
        new_widget.setGraphicsEffect(eff)

        # Make the new widget current (old is hidden by the stack)
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
        """Rebuild Panel A's summary table (last 14) with a soft fade swap."""
        rows = self._fetch_last10_rows()
        new_table = self._make_summary_table_widget(rows)
        self._connect_summary_signals(new_table)
        self._fade_in_over_current(new_table, duration=140)

    def _open_full_dialog(self):
        """
        Open a modal dialog with FULL expense history (all rows, newest first).
        Includes Currency (joined from wallet) and keeps Description last.
        """
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT e.name,
                       c.name AS category,
                       e.cost,
                       e.date,
                       w.currency,
                       e.wallet_id,
                       e.description
                FROM expense e
                LEFT JOIN category c ON e.category_id = c.id
                LEFT JOIN wallet   w ON e.wallet_id   = w.id
                ORDER BY e.date DESC
                """
            )
            rows = cur.fetchall()

        dlg = QDialog(self)
        dlg.setWindowTitle("Expenses (full history)")
        dlg.resize(760, 440)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        table = QTableWidget()
        self._style_table(table)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)

        headers = ["Name", "Category", "Cost", "Date", "Currency", "Wallet", "Description"]
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setRowCount(len(rows))

        # Faster fill
        table.setSortingEnabled(False)
        table.setUpdatesEnabled(False)

        wallet_name_cache: dict[int, str] = {}

        for r, row in enumerate(rows):
            name, category, cost, date, currency, wallet, description = row

            # Resolve wallet id -> wallet name for display
            wallet_display = ""
            try:
                if wallet is not None:
                    wid = int(wallet)
                    if wid in wallet_name_cache:
                        wallet_display = wallet_name_cache[wid]
                    else:
                        wrow = get_wallet_by_id(wid)
                        wname = wrow[1] if (wrow and len(wrow) > 1) else str(wid)
                        wallet_name_cache[wid] = str(wname) if wname is not None else ""
                        wallet_display = wallet_name_cache[wid]
            except Exception:
                wallet_display = "" if wallet is None else str(wallet)

            table.setItem(r, 0, QTableWidgetItem("" if name is None else str(name)))
            table.setItem(r, 1, QTableWidgetItem("" if category is None else str(category)))
            table.setItem(r, 2, QTableWidgetItem("" if cost is None else f"{cost:.2f}"))
            table.setItem(r, 3, QTableWidgetItem("" if date is None else str(date)))
            table.setItem(r, 4, QTableWidgetItem("" if currency is None else str(currency)))
            table.setItem(r, 5, QTableWidgetItem(wallet_display))
            table.setItem(r, 6, QTableWidgetItem("" if description is None else str(description)))
        table.setUpdatesEnabled(True)

        hdr = table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # Name
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # Category
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # Cost
        hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # Date
        hdr.setSectionResizeMode(4, QHeaderView.ResizeToContents)  # Currency
        hdr.setSectionResizeMode(5, QHeaderView.ResizeToContents)  # Wallet
        hdr.setSectionResizeMode(6, QHeaderView.Stretch)           # Description

        lay.addWidget(table, 1)

        close_row = QHBoxLayout()
        close_row.addStretch(1)
        btn_close = QPushButton("Close")
        close_row.addWidget(btn_close)
        lay.addLayout(close_row)

        # Theme the dialog controls
        self._style_table(table)
        self._style_dialog_buttons([btn_close])

        btn_close.clicked.connect(dlg.accept)
        dlg.exec()

    # (Kept for parity; no longer used by the global toggle)
    def apply_toggle(self, key: int):
        if key == self.toggle_key:
            return
        self.toggle_key = key

    # ---------- THEME PLUMBING ----------
    def _style_dialog_buttons(self, buttons: list[QPushButton]):
        t = current_theme()
        # Subtle glass button, theme-aware text
        for b in buttons:
            b.setStyleSheet(f"""
                QPushButton {{
                    background: {"rgba(255,255,255,0.06)" if t.variant!="light" else "rgba(0,0,0,0.06)"};
                    border: 1px solid {"rgba(255,255,255,0.10)" if t.variant!="light" else "rgba(0,0,0,0.10)"};
                    color: {t.TEXT};
                    border-radius: 8px; padding: 6px 12px; font-size:12px;
                }}
                QPushButton:hover {{
                    background: {"rgba(255,255,255,0.12)" if t.variant!="light" else "rgba(0,0,0,0.12)"};
                    border-color: {"rgba(255,255,255,0.18)" if t.variant!="light" else "rgba(0,0,0,0.18)"};
                }}
            """)

    def _apply_theme_colors(self, theme):
        """Re-style buttons/labels/inputs and tables to the active theme."""
        # Colors used repeatedly
        mag = theme.MAGENTA
        blue = theme.ACCENT_BLUE
        text = theme.TEXT
        text_secondary = theme.TEXT_SECONDARY

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

        # Top NAV chips (Expenses/Wallets/Categories/Goals)
        nav_style = f"""
            QPushButton {{
                background: rgba(8,10,18,0.58) if 1 else {base_bg_glass};
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
        for b in (self.btn_expenses, self.btn_wallets, self.btn_categories, self.btn_goals):
            b.setStyleSheet(nav_style)

        # Action toggles (Record / Remove) — use ACCENT_BLUE for 'armed'
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
        self.btn_record.setStyleSheet(action_style)
        self.btn_remove.setStyleSheet(action_style)

        # "View full" button — subtle glass
        self.btn_view_full.setStyleSheet(f"""
            QPushButton {{
                background: {base_bg_glass};
                border: 1px solid {base_border};
                color: {text};
                border-radius: 8px;
                padding: 2px 10px; font-size:12px;
            }}
            QPushButton:hover {{ background: {base_bg_hover}; }}
        """)

        # Labels (titles / field labels)
        for lbl in self._themed_labels:
            lbl.setStyleSheet(f"font-size:12px; font-weight:600; color:{text};")

        # Inputs (theme-aware backgrounds/borders/selection/focus)
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
            QTextEdit {{
                background: {input_bg};
                color: {text};
                border: 1px solid {base_border};
                border-radius: 10px;
                padding: 6px 10px;
                min-height: 72px;
                max-height: 96px;
                selection-background-color: {sel_rgba};
                selection-color: {text};
            }}
            QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QDoubleSpinBox:focus, QTextEdit:focus {{
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
        for w in (self.input_name, self.input_cost, self.input_date, self.input_category,
                  self.input_wallet, self.input_description, self.remove_combo, self.btn_view_full):
            if w:
                try:
                    w.setStyleSheet(inputs_qss)
                except Exception:
                    pass

        # Restyle live table(s)
        try:
            if self._summary_table is not None:
                self._style_table(self._summary_table)
                self._summary_table.viewport().update()
        except Exception:
            pass

    # ---------- Smooth DB refresh (Overview-like) ----------
    def _refresh_from_db(self):
        """
        Re-read DB-backed values and update summary table + remove combo smoothly.
        Called on showEvent and after record/remove.
        """
        # Summary table (fade swap)
        self._build_summary_table()
        # Remove list
        self._load_remove_last10()

    def _emit_data_changed(self):
        """
        Notify any listeners that expense data changed (e.g., Overview can refresh).
        Does not alter backend behavior or layout.
        """
        try:
            self.dataChanged.emit()
        except Exception:
            pass

    # ---------- LIFECYCLE ----------
    def showEvent(self, e):
        super().showEvent(e)
        # Defer DB read slightly so first paint is smooth (same as Overview)
        QTimer.singleShot(35, self._refresh_from_db)


# ---------- Soft halo painter for the middle section (magenta + cool blue) ----------
class ManageHaloPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("background: transparent;")
        # repaint on theme change
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
