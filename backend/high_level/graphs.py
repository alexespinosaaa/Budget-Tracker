# ─── Standard Library ────────────────────────────────────────────────────────
from datetime import datetime, timedelta
from calendar import monthrange
from collections import defaultdict
from statistics import mean
from typing import Dict, List, Tuple

# ─── Third-Party Libraries ──────────────────────────────────────────────────
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import matplotlib as mpl
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
import calendar
from statistics import stdev
import plotly.graph_objects as go
from dateutil.relativedelta import relativedelta
import pandas as pd
from PySide6.QtWidgets import (
    QWidget,QHeaderView,
)

try:
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
except ImportError:
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

# ─── Internal Project Imports ───────────────────────────────────────────────
from backend.db import get_connection
from backend.crud.expenses import get_all_expenses 
from backend.crud.categories import get_all_categories,get_all_categories_full
from backend.high_level.analysis import calc_networth, filter_expenses_by_toggle, get_avg_monthly_expense, weekly_expenses

# ─────────────────────────────
# 🗂️ CATEGORY FUNCTIONS
# ─────────────────────────────

def cat_volatility_qt(toggle_state: int = 0):
    """
    Qt version of cat_volatility.
    Returns a FigureCanvas (Qt widget) showing per-category standard deviation (bar height)
    with the mean annotated above each bar.

    Theme-only coloring (no per-category palette):
    - Reads palette from frontend.theme.current_theme() when available
    - Uses a single accent color for all bars (theme.ACCENT_BLUE)
    - Falls back to dark-friendly defaults if theme is unavailable
    """
    from collections import defaultdict
    from statistics import stdev, mean
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas

    # ---- Fetch & filter data (behavior unchanged) ----
    expenses = get_all_expenses()
    categories = get_all_categories()
    filtered_expenses = filter_expenses_by_toggle(expenses, categories, toggle_state)

    cat_name_map = {cat[0]: cat[1] for cat in categories}

    cost_per_category: dict[str, list[float]] = defaultdict(list)
    for exp in filtered_expenses:
        try:
            category_id = exp[2]
            cost = float(exp[3])
            cat_name = cat_name_map.get(category_id, "Unknown")
            cost_per_category[cat_name].append(cost)
        except (TypeError, ValueError):
            continue

    # ---- THEME (non-breaking) ----
    def _hex(c):
        try:
            return c.name()
        except Exception:
            return str(c)

    try:
        from frontend.theme import current_theme  # optional
        t = current_theme()
        variant = getattr(t, "variant", "dark")
        TEXT = _hex(getattr(t, "TEXT", "#E8ECF6"))
        TICK = _hex(getattr(t, "TICK", "#B8C1D9"))
        BAR  = _hex(getattr(t, "ACCENT_BLUE", "#2F6BCE"))
        if variant == "light":
            SPINE = (0, 0, 0, 0.25)
            GRID  = (0, 0, 0, 0.10)
        else:
            SPINE = (1, 1, 1, 0.18)
            GRID  = (1, 1, 1, 0.06)
    except Exception:
        # Fallbacks
        TEXT  = "#E8ECF6"
        TICK  = "#B8C1D9"
        BAR   = "#2F6BCE"
        SPINE = (1, 1, 1, 0.18)
        GRID  = (1, 1, 1, 0.06)

    # ---- Prepare figure/canvas (transparent) ----
    fig = Figure(figsize=(10, 5.5), dpi=100)
    fig.patch.set_alpha(0.0)
    ax = fig.add_subplot(111)
    ax.set_facecolor("none")

    if not cost_per_category:
        ax.text(0.5, 0.5, "No data available.", ha="center", va="center",
                fontsize=12, color=TEXT)
        ax.set_axis_off()
        canvas = FigureCanvas(fig)
        canvas.setStyleSheet("background: transparent;")
        canvas.setMinimumSize(0, 0)
        return canvas

    # ---- Compute SD & mean per category (unchanged) ----
    volatility_per_category: dict[str, float] = {}
    mean_per_category: dict[str, float] = {}
    for cat, costs in cost_per_category.items():
        if len(costs) > 1:
            volatility_per_category[cat] = round(stdev(costs), 2)
        else:
            volatility_per_category[cat] = 0.0
        mean_per_category[cat] = round(mean(costs), 2)

    # Sort by volatility descending (unchanged)
    sorted_cats = sorted(volatility_per_category.items(), key=lambda x: x[1], reverse=True)
    labels = [c for c, _ in sorted_cats]
    sd_values = [volatility_per_category[c] for c in labels]
    mean_values = [mean_per_category[c] for c in labels]
    x_positions = list(range(len(labels)))

    # Layout room for rotated labels
    fig.subplots_adjust(left=0.10, right=0.98, top=0.88, bottom=0.30)

    # Bars (single theme accent color)
    bars = ax.bar(x_positions, sd_values, color=BAR, edgecolor="none")

    # Mean annotations (styled via theme)
    offset = 0.02 * max(sd_values, default=1)
    for x, bar, m in zip(x_positions, bars, mean_values):
        h = bar.get_height()
        ax.text(x, h + offset, f"€{m}", ha="center", va="bottom",
                fontsize=9, color=TEXT)

    # Axes & styling
    ax.set_ylabel("Standard Deviation (€)", color=TEXT, fontsize=10)
    ax.set_title("Spending Volatility by Category", color=TEXT, fontsize=13, pad=8)
    ax.set_xticks(x_positions)
    ax.set_xticklabels(labels, rotation=45, ha="right", color=TEXT, fontsize=9)

    ax.tick_params(axis="y", colors=TICK, labelsize=9, length=3)
    for s in ax.spines.values():
        s.set_linewidth(1.0)
        s.set_color(SPINE)

    ax.grid(True, axis="y", color=GRID, linewidth=1.0)
    ax.margins(x=0.01)

    canvas = FigureCanvas(fig)
    canvas.setStyleSheet("background: transparent;")
    canvas.setMinimumSize(0, 0)
    return canvas

def bar_graph_qt(toggle_state: int = 0, month_key: int = 0):
    """
    Qt version of bar_graph.
    Returns a FigureCanvas (Qt widget) comparing category limits vs actual spend
    for the current month (month_key=0) or previous month (month_key=1).
    Respects toggle_state (1 = exclude fixed categories).

    Theme-aware (no functionality changes):
    - Reads palette from frontend.theme.current_theme() when available
    - Falls back to original dark-friendly constants otherwise
    """
    from datetime import datetime, timedelta
    from collections import defaultdict
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas

    # Determine target month (unchanged)
    today = datetime.today()
    if month_key == 1:
        first_day = today.replace(day=1)
        target_date = first_day - timedelta(days=1)
    else:
        target_date = today

    month_str = f"{target_date.month:02d}"
    year_str = str(target_date.year)
    prefix = f"{year_str}-{month_str}"

    # Data (unchanged)
    expenses = get_all_expenses()
    categories = get_all_categories()
    filtered_expenses = filter_expenses_by_toggle(expenses, categories, toggle_state)

    cat_name_limit = {cat[0]: (cat[1], cat[2]) for cat in categories}
    cat_type_map   = {cat[0]: cat[3] for cat in categories}

    totals_per_category = defaultdict(float)
    for exp in filtered_expenses:
        exp_date = str(exp[4])  # YYYY-MM-DD
        if exp_date.startswith(prefix):
            cat_id = exp[2]
            try:
                totals_per_category[cat_id] += float(exp[3])
            except (TypeError, ValueError):
                continue

    labels, spent, limits = [], [], []
    for cat_id, (name, limit) in cat_name_limit.items():
        if limit is None:
            continue
        if toggle_state == 1 and cat_type_map.get(cat_id) == 1:
            continue
        labels.append(name)
        spent.append(totals_per_category.get(cat_id, 0.0))
        try:
            limits.append(float(limit))
        except (TypeError, ValueError):
            limits.append(0.0)

    # ---- THEME (non-breaking) ----
    def _hex(c):
        try:
            return c.name()
        except Exception:
            return str(c)

    try:
        from frontend.theme import current_theme  # optional
        t = current_theme()
        variant = getattr(t, "variant", "dark")
        TEXT  = _hex(getattr(t, "TEXT", "#E8ECF6"))
        TICK  = _hex(getattr(t, "TICK", "#B8C1D9"))
        BLUE  = _hex(getattr(t, "ACCENT_BLUE", "#2F6BCE"))
        if variant == "light":
            SPINE       = (0, 0, 0, 0.25)
            GRID        = (0, 0, 0, 0.10)
            LIMIT_COLOR = (0, 0, 0, 0.20)  # soft black on light bg
        else:
            SPINE       = (1, 1, 1, 0.18)
            GRID        = (1, 1, 1, 0.08)
            LIMIT_COLOR = (1, 1, 1, 0.20)  # soft white on dark bg
        SPENT_COLOR = BLUE
    except Exception:
        # Fallback to original constants
        TEXT        = "#E8ECF6"
        TICK        = "#B8C1D9"
        SPINE       = (1, 1, 1, 0.18)
        GRID        = (1, 1, 1, 0.08)
        LIMIT_COLOR = (1, 1, 1, 0.20)
        SPENT_COLOR = "#2F6BCE"

    # Prepare figure/canvas (transparent) (unchanged)
    fig = Figure(figsize=(10, 6), dpi=100)
    fig.patch.set_alpha(0.0)
    ax = fig.add_subplot(111)
    ax.set_facecolor("none")

    if not labels:
        ax.text(0.5, 0.5, "No data to display.", ha="center", va="center",
                fontsize=12, color=TEXT)
        ax.set_axis_off()
        canvas = FigureCanvas(fig)
        canvas.setStyleSheet("background: transparent;")
        canvas.setMinimumSize(0, 0)
        return canvas

    # Plot (unchanged)
    x = list(range(len(labels)))
    width = 0.36

    ax.bar(x, limits, width=width, label="Limit",
           color=LIMIT_COLOR, edgecolor="none")
    ax.bar([i + width for i in x], spent, width=width, label="Spent",
           color=SPENT_COLOR, edgecolor="none")

    ax.set_ylabel("Amount (€)", color=TEXT, fontsize=10)

    title_suffix = "Previous" if month_key == 1 else "Current"
    ax.set_title(f"Spending vs Limit — {title_suffix} Month",
                 color=TEXT, fontsize=13, pad=8)

    ax.set_xticks([i + width / 2 for i in x])
    ax.set_xticklabels(labels, rotation=45, ha="right", color=TEXT, fontsize=9)

    # Legend styling
    leg = ax.legend(loc="best", frameon=False)
    if leg:
        for t_ in leg.get_texts():
            t_.set_color(TEXT)

    # Axes styling
    ax.tick_params(axis="y", colors=TICK, labelsize=9, length=3)
    for s in ax.spines.values():
        s.set_linewidth(1.0)
        s.set_color(SPINE)

    ax.grid(True, axis="y", color=GRID, linewidth=1.0)
    ax.margins(x=0.02)

    fig.subplots_adjust(left=0.10, right=0.98, top=0.88, bottom=0.30)

    canvas = FigureCanvas(fig)
    canvas.setStyleSheet("background: transparent;")
    canvas.setMinimumSize(0, 0)
    return canvas

def over_under_qt(toggle_state: int = 0):
    """
    Qt version of over_under.
    Returns a FigureCanvas (Qt widget) showing how many months each category
    exceeded its monthly limit. Respects toggle_state.

    Theme-aware (no functionality changes):
    - Reads palette from frontend.theme.current_theme() when available
    - Falls back to original dark-friendly constants otherwise
    """
    from collections import defaultdict
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas

    # ---- THEME (non-breaking) ----
    def _hex(c):
        try:
            return c.name()
        except Exception:
            return str(c)

    try:
        from frontend.theme import current_theme  # optional
        t = current_theme()
        variant = getattr(t, "variant", "dark")
        TEXT = _hex(getattr(t, "TEXT", "#E8ECF6"))
        TICK = _hex(getattr(t, "TICK", "#B8C1D9"))
        BAR  = _hex(getattr(t, "MAGENTA", "#B91D73"))
        if variant == "light":
            SPINE = (0, 0, 0, 0.25)
            GRID  = (0, 0, 0, 0.10)
        else:
            SPINE = (1, 1, 1, 0.18)
            GRID  = (1, 1, 1, 0.08)
    except Exception:
        # Fallback to previous hard-coded palette
        TEXT  = "#E8ECF6"          # light text
        TICK  = "#B8C1D9"          # softer ticks
        SPINE = (1, 1, 1, 0.18)    # subtle white spines
        GRID  = (1, 1, 1, 0.08)    # soft grid
        BAR   = "#B91D73"          # magenta

    # Fetch & filter data (backend behavior unchanged)
    expenses = get_all_expenses()
    categories = get_all_categories()
    filtered_expenses = filter_expenses_by_toggle(expenses, categories, toggle_state)

    # cat[0]=id, cat[1]=name, cat[2]=limit, cat[3]=type
    cat_meta = {cat[0]: (cat[1], cat[2], cat[3]) for cat in categories}

    # Sum monthly totals per (YYYY-MM, category_id)
    monthly_totals = defaultdict(float)
    for exp in filtered_expenses:
        try:
            cat_id = exp[2]
            date_key = str(exp[4])[:7]  # YYYY-MM
            amount = float(exp[3])
        except (TypeError, ValueError):
            continue
        monthly_totals[(date_key, cat_id)] += amount

    # Count months over limit per category name
    over_limit_counts = defaultdict(int)
    for (month_key, cat_id), total in monthly_totals.items():
        name, limit, _ = cat_meta.get(cat_id, ("Unknown", None, None))
        try:
            lim = float(limit) if limit is not None else None
        except (TypeError, ValueError):
            lim = None
        if lim is not None and total > lim:
            over_limit_counts[name] += 1

    # Prepare figure/canvas (transparent for glass card)
    fig = Figure(figsize=(10, 6), dpi=100)
    fig.patch.set_alpha(0.0)
    ax = fig.add_subplot(111)
    ax.set_facecolor("none")

    if not over_limit_counts:
        ax.text(0.5, 0.5, "No over-limit spending detected.",
                ha="center", va="center", fontsize=12, color=TEXT)
        ax.set_axis_off()
        canvas = FigureCanvas(fig)
        canvas.setStyleSheet("background: transparent;")
        canvas.setMinimumSize(0, 0)
        return canvas

    labels = list(over_limit_counts.keys())
    counts = [int(over_limit_counts[k]) for k in labels]
    x = list(range(len(labels)))

    # Leave space for rotated labels
    fig.subplots_adjust(left=0.10, right=0.98, top=0.88, bottom=0.30)

    # Bars
    bars = ax.bar(x, counts, color=BAR, edgecolor="none")

    # Value labels above bars (small)
    max_val = max(counts) if counts else 1
    for xi, bar in zip(x, bars):
        h = bar.get_height()
        ax.text(xi, h + max(0.03 * max_val, 0.06), f"{int(h)}",
                ha="center", va="bottom", fontsize=9, color=TEXT)

    # Axes & styling
    ax.set_ylabel("Months Over Limit", color=TEXT, fontsize=10)
    ax.set_title("# Each Category Exceeded Monthly Limit", color=TEXT, fontsize=13, pad=8)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha="right", color=TEXT, fontsize=9)
    ax.tick_params(axis="y", colors=TICK, labelsize=9, length=3)

    for s in ax.spines.values():
        s.set_linewidth(1.0)
        s.set_color(SPINE)

    ax.grid(True, axis="y", color=GRID, linewidth=1.0)
    ax.margins(x=0.02)

    canvas = FigureCanvas(fig)
    canvas.setStyleSheet("background: transparent;")
    canvas.setMinimumSize(0, 0)
    return canvas

# ─────────────────────────────
# 💸 EXPENSE FUNCTIONS
# ─────────────────────────────
def cumulative_expenditure_qt(
    timeframe: str = "this_month",
    toggle_state: int = 0,
    skip_months: list[str] | None = None,
    target_currency: str = "EUR",
    minimal: bool = True,
):
    from datetime import date
    from calendar import monthrange
    from dateutil.relativedelta import relativedelta
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QSizePolicy

    def _to_hex(c):
        try:
            return c.name()
        except Exception:
            return str(c)

    try:
        from frontend.theme import current_theme
        t = current_theme()
        variant = getattr(t, "variant", "dark")
        TEXT   = _to_hex(getattr(t, "TEXT", "#E8ECF6"))
        TICK   = _to_hex(getattr(t, "TICK", "#B8C1D9"))
        CURR_COLOR = _to_hex(getattr(t, "ACCENT_BLUE", "#2F6BCE"))
        LAST_COLOR = _to_hex(getattr(t, "ACCENT_BLUE_SOFT", "#84A6E8"))
        AVG_COLOR  = _to_hex(getattr(t, "TEAL", "#69C4B8"))
        if variant == "light":
            SPINE = (0, 0, 0, 0.25)
            GRID  = (0, 0, 0, 0.10)
            FAINT = (0, 0, 0, 0.28)
        else:
            SPINE = (1, 1, 1, 0.18)
            GRID  = (1, 1, 1, 0.10)
            FAINT = (1, 1, 1, 0.28)
    except Exception:
        TEXT  = "#E8ECF6"
        TICK  = "#B8C1D9"
        SPINE = (1, 1, 1, 0.18)
        GRID  = (1, 1, 1, 0.10)
        FAINT = (1, 1, 1, 0.28)
        CURR_COLOR = "#2F6BCE"
        LAST_COLOR = "#84A6E8"
        AVG_COLOR  = "#69C4B8"

    try:
        from backend.crud.expenses import get_all_expenses
    except Exception:
        def get_all_expenses():
            return []

    fixed_ids: set[int] = set()
    if toggle_state == 1:
        try:
            from backend.crud.categories import get_all_categories_full
            cats = get_all_categories_full() or []
            fixed_ids = {int(c[0]) for c in cats if len(c) > 3 and int(c[3] or 0) == 1}
        except Exception:
            fixed_ids = set()

    def _currency_conversion_or_none(amount: float, from_cur: str, to_cur: str) -> float | None:
        try:
            from backend.high_level.analysis import currency_conversion
            return float(currency_conversion(amount, from_currency=from_cur, to_currency=to_cur))
        except Exception:
            return None

    def _convert_cost(cost: float, wallet_id: int) -> float:
        try:
            from backend.crud.wallets import get_wallet_by_id
            w = get_wallet_by_id(int(wallet_id))
            w_currency = str(w[3]) if (w and len(w) > 3 and w[3] is not None) else None
            if w_currency and w_currency != target_currency:
                converted = _currency_conversion_or_none(cost, w_currency, target_currency)
                if isinstance(converted, (int, float)):
                    return float(converted)
        except Exception:
            pass
        return float(cost or 0.0)

    def _passes_toggle(exp_row) -> bool:
        if toggle_state != 1:
            return True
        try:
            cat_id = int(exp_row[2])
            return cat_id not in fixed_ids
        except Exception:
            return True

    skip_months = set(skip_months or [])
    _all = [e for e in (get_all_expenses() or []) if len(e) >= 7]
    expenses = [e for e in _all if _passes_toggle(e)]

    def _sum_for_day(d: date) -> float:
        ds = d.strftime("%Y-%m-%d")
        total = 0.0
        for e in expenses:
            if str(e[4]) == ds:
                total += _convert_cost(float(e[3] or 0.0), int(e[6] or 0))
        return round(total, 2)

    def _cumulative_for_month(y: int, m: int) -> list[float]:
        days = monthrange(y, m)[1]
        run = 0.0
        cum = []
        for day in range(1, days + 1):
            run += _sum_for_day(date(y, m, day))
            cum.append(round(run, 2))
        return cum

    def _average_cumulative(months_list: list[tuple[int, int]]) -> list[float]:
        if not months_list:
            return []
        max_days = max(monthrange(y, m)[1] for (y, m) in months_list)
        per_month_cum = [_cumulative_for_month(y, m) for (y, m) in months_list]
        avg_curve = []
        for k in range(1, max_days + 1):
            vals = []
            for cm in per_month_cum:
                idx = min(k, len(cm)) - 1
                vals.append(cm[idx])
            avg_curve.append(round(sum(vals) / len(vals), 2))
        return avg_curve

    today = date.today()
    if timeframe != "this_month":
        w = QWidget()
        w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        lay = QVBoxLayout(w); lay.setContentsMargins(0, 0, 0, 0)
        msg = QLabel("cumulative_expenditure_qt currently supports the 'this_month' view.")
        msg.setAlignment(Qt.AlignCenter)
        msg.setStyleSheet("color:#a00;")
        lay.addWidget(msg, 1)
        return w

    cur_y, cur_m = today.year, today.month
    cur_full_cum = _cumulative_for_month(cur_y, cur_m)
    cur_x = list(range(1, today.day + 1))
    cur_y_vals = cur_full_cum[: today.day]

    last_day_prev_month = (today.replace(day=1) - relativedelta(days=1))
    prev_y, prev_m = last_day_prev_month.year, last_day_prev_month.month
    prev_full_cum = _cumulative_for_month(prev_y, prev_m)
    prev_x = list(range(1, len(prev_full_cum) + 1))
    prev_y_vals = prev_full_cum

    months_for_avg = []
    cursor = last_day_prev_month.replace(day=1)
    for _ in range(12):
        ym_key = f"{cursor.year:04d}-{cursor.month:02d}"
        if ym_key not in skip_months:
            months_for_avg.append((cursor.year, cursor.month))
        cursor = (cursor - relativedelta(months=1))
    avg_curve = _average_cumulative(months_for_avg) if months_for_avg else []
    avg_x = list(range(1, len(avg_curve) + 1))
    avg_y_vals = avg_curve

    fig = Figure(figsize=(10, 4.6), dpi=100)
    fig.patch.set_alpha(0.0)
    ax = fig.add_subplot(111)
    ax.set_facecolor("none")

    if cur_x and cur_y_vals:
        ax.plot(cur_x, cur_y_vals, label="This month (to date)", linewidth=2.4, color=CURR_COLOR)
    if prev_x and prev_y_vals:
        ax.plot(prev_x, prev_y_vals, label="Last month", linewidth=1.9, color=LAST_COLOR)
    if avg_x and avg_y_vals:
        ax.plot(avg_x, avg_y_vals, label="12-month average", linewidth=1.9, color=AVG_COLOR)

    max_len = max(len(cur_x), len(prev_x), len(avg_x))
    ax.set_xlim(1, max_len if max_len > 1 else 1)
    ymin = 0.0
    ymax = max((cur_y_vals or [0]) + (prev_y_vals or [0]) + (avg_y_vals or [0])) if (cur_y_vals or prev_y_vals or avg_y_vals) else 1.0
    ax.set_ylim(ymin, ymax * 1.05 if ymax > 0 else 1.0)

    if minimal:
        for s in ax.spines.values():
            s.set_visible(True)
            s.set_linewidth(1.2)
            s.set_color(FAINT)
        ax.grid(False)
        ax.set_title("")
        ax.set_xlabel("")
        ax.set_ylabel("")
        ax.legend_.remove() if ax.get_legend() else None
        ax.tick_params(axis="both", which="both", bottom=True, top=True, left=True, right=True,
                       labelbottom=False, labelleft=False, length=3, width=1.0, colors=FAINT)
        fig.subplots_adjust(left=0.02, right=0.98, top=0.98, bottom=0.02)
    else:
        for s in ax.spines.values():
            s.set_visible(True)
            s.set_linewidth(1.0)
            s.set_color(SPINE)
        ax.grid(True, which="major", color=GRID, linewidth=1.0)
        ax.set_title("Cumulative Expenditure — This Month vs Last & 12-month Avg", color=TEXT, fontsize=13, pad=8)
        ax.set_xlabel("Day of month", color=TEXT, fontsize=10)
        ax.set_ylabel(f"Amount ({target_currency})", color=TEXT, fontsize=10)
        ax.tick_params(axis="x", colors=TICK, labelsize=9, length=3)
        ax.tick_params(axis="y", colors=TICK, labelsize=9, length=3)
        leg = ax.legend(loc="best", frameon=False)
        if leg:
            for t in leg.get_texts():
                t.set_color(TEXT)
        fig.subplots_adjust(left=0.08, right=0.98, top=0.90, bottom=0.14)

    canvas = FigureCanvas(fig)
    canvas.setStyleSheet("background: transparent;")
    return canvas

def expenses_in_calendar_qt(toggle_state: int = 0, main_wallet: int | None = None):
    """
    Returns a FigureCanvas (Qt widget) for the monthly expenses heatmap.

    Now theme-aware: reads colors & variant from frontend.theme.current_theme().
    """
    import calendar
    from collections import defaultdict
    from datetime import datetime
    import numpy as np
    import matplotlib as mpl
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.colors import LinearSegmentedColormap, Normalize
    try:
        from frontend.theme import current_theme
        T = current_theme()
    except Exception:
        class _F: pass
        T = _F()
        T.variant = "dark"
        T.MAGENTA = type("C", (), {"name": lambda self="#B91D73": self})()
        T.ACCENT_RED = type("C", (), {"name": lambda self="#E53935": self})()
        T.TEXT = "#FFFFFF"; T.TEXT_SECONDARY = "#B7B9BE"
        T.PLUM = type("C", (), {"name": lambda self="#1A0D1F": self,
                                "darker": lambda self, f=200: self})()
    def _hex(qcolor):
        try:
            return qcolor.name()
        except Exception:
            return str(qcolor)
    if getattr(T, "variant", "dark") == "light":
        base0 = "#ECEFF4"
        ramp_colors = [
            "#E6E7EB",
            _hex(getattr(T, "MAGENTA", T)),
            _hex(getattr(T, "ACCENT_RED", T)),
        ]
        grid_rgba = (0, 0, 0, 0.10)
        axis_face = (0, 0, 0, 0.03)
        tick_color = getattr(T, "TEXT_SECONDARY", "#4B5563")
        title_color = getattr(T, "TEXT", "#0E1220")
        cbar_tick = tick_color
        cbar_label = tick_color
    else:
        try:
            base0 = T.PLUM.darker(220).name()
        except Exception:
            base0 = "#2A1028"
        ramp_colors = [
            base0,
            _hex(getattr(T, "MAGENTA", T)),
            _hex(getattr(T, "ACCENT_RED", T)),
        ]
        grid_rgba = (1, 1, 1, 0.06)
        axis_face = (1, 1, 1, 0.02)
        tick_color = getattr(T, "TEXT_SECONDARY", "#B7B9BE")
        title_color = getattr(T, "TEXT", "#FFFFFF")
        cbar_tick = tick_color
        cbar_label = tick_color
    expenses = get_all_expenses()
    categories = get_all_categories()
    filtered_expenses = filter_expenses_by_toggle(expenses, categories, toggle_state)
    currency_code = "EUR"
    if main_wallet is not None:
        try:
            from backend.crud.wallets import get_wallet_by_id
            w = get_wallet_by_id(int(main_wallet)) or ()
            if len(w) >= 4 and w[3]:
                currency_code = str(w[3])
        except Exception:
            pass
        try:
            filtered_expenses = [
                e for e in filtered_expenses
                if len(e) > 6 and e[6] == int(main_wallet)
            ]
        except Exception:
            filtered_expenses = []
    today = datetime.today()
    current_year = today.year
    current_month = today.month
    month_str = f"{current_year}-{current_month:02d}"
    daily_totals = defaultdict(float)
    for exp in filtered_expenses:
        date_str = exp[4]
        if isinstance(date_str, str) and date_str.startswith(month_str):
            try:
                day = int(date_str[-2:])
                daily_totals[day] += float(exp[3])
            except Exception:
                pass
    cal = calendar.Calendar()
    month_matrix = cal.monthdayscalendar(current_year, current_month)
    num_days = mpl.dates.num2date(mpl.dates.date2num(datetime(current_year, current_month, 1))).month
    num_days = calendar.monthrange(current_year, current_month)[1]
    heatmap_data = []
    for week in month_matrix:
        row = []
        for day in week:
            row.append(0 if day == 0 or day > num_days else daily_totals.get(day, 0.0))
        heatmap_data.append(row)
    max_val = max(daily_totals.values()) if daily_totals else 1.0
    fig = Figure(figsize=(10, 6), dpi=100, facecolor=(0, 0, 0, 0))
    ax = fig.add_subplot(111, facecolor=axis_face)
    cmap = LinearSegmentedColormap.from_list("themed_ramp", ramp_colors)
    cmap.set_under((0, 0, 0, 0))
    norm = Normalize(vmin=1e-6, vmax=max_val)
    im = ax.imshow(
        heatmap_data,
        cmap=cmap,
        norm=norm,
        aspect="auto",
        interpolation="nearest"
    )
    ax.set_xticks(np.arange(-.5, 7, 1), minor=True)
    ax.set_yticks(np.arange(-.5, len(month_matrix), 1), minor=True)
    ax.grid(which="minor", color=grid_rgba, linewidth=0.8)
    ax.tick_params(which="minor", bottom=False, left=False)
    ax.set_xticks(range(7))
    ax.set_xticklabels(['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
                       fontsize=10, color=tick_color)
    ax.set_yticks(range(len(month_matrix)))
    ax.set_yticklabels([f"Week {i+1}" for i in range(len(month_matrix))],
                       fontsize=10, color=tick_color)
    ax.tick_params(axis='y', which='major', pad=6)
    for i, week in enumerate(month_matrix):
        for j, day in enumerate(week):
            if day == 0 or day > num_days:
                continue
            val = daily_totals.get(day, 0.0)
            if val > 0:
                lbl = f"{day}\n{int(val)} {currency_code}"
                col = title_color
                alpha = 0.95
            else:
                lbl = f"{day}"
                col = tick_color
                alpha = 0.90
            ax.text(j, i, lbl, ha='center', va='center',
                    fontsize=8.5, color=col, alpha=alpha, linespacing=0.9)
    import calendar as _cal
    ax.set_title(f"{_cal.month_name[current_month]} {current_year}",
                 fontsize=16, fontweight="bold", color=title_color, pad=12)
    for spine in ax.spines.values():
        spine.set_visible(False)
    left, right, top, bottom = 0.14, 0.98, 0.88, 0.24
    fig.subplots_adjust(left=left, right=right, top=top, bottom=bottom)
    cbar_h = 0.03
    gap    = 0.06
    cax_left   = left + 0.02
    cax_width  = (right - left) - 0.04
    cax_bottom = bottom - (cbar_h + gap)
    cax = fig.add_axes([cax_left, cax_bottom, cax_width, cbar_h], facecolor=(0, 0, 0, 0))
    cb  = fig.colorbar(im, cax=cax, orientation='horizontal')
    cb.outline.set_visible(False)
    cb.set_label(f'Expenses ({currency_code})', fontsize=10, color=cbar_label, labelpad=2)
    cb.ax.tick_params(labelsize=9, colors=cbar_tick)
    for spine in cb.ax.spines.values():
        spine.set_visible(False)
    canvas = FigureCanvas(fig)
    canvas.setMinimumSize(0, 0)
    return canvas

def weekly_exp_trend_qt(n: int = 10, toggle_state: int = 0):
    """
    Qt version of weekly_exp_trend.
    Returns a FigureCanvas (Qt widget) showing weekly expenses for the past `n` weeks
    and a simple linear trend line. Respects toggle_state.

    Theme-aware (no API change):
    - Pulls colors from frontend.theme.current_theme() when available.
    - Falls back to previous hard-coded palette if theme module isn't present.
    """
    import numpy as np
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas

    # ---- THEME LOOKUP (non-breaking) ---------------------------------------
    def _to_hex(c):
        # QColor or similar with .name() => "#RRGGBB"; else assume string like "#fff..."
        try:
            return c.name()
        except Exception:
            return str(c)

    try:
        # Optional dependency: we only read if present
        from frontend.theme import current_theme  # type: ignore
        t = current_theme()
        variant = getattr(t, "variant", "dark")

        TEXT   = _to_hex(getattr(t, "TEXT",   "#E8ECF6"))
        TICK   = _to_hex(getattr(t, "TICK",   "#B8C1D9"))
        SERIES = _to_hex(getattr(t, "ACCENT_BLUE", "#2F6BCE"))
        TREND  = _to_hex(getattr(t, "MAGENTA",     "#B91D73"))

        if variant == "light":
            SPINE = (0, 0, 0, 0.25)   # subtle black spines in light
            GRID  = (0, 0, 0, 0.10)   # soft grid in light
        else:
            SPINE = (1, 1, 1, 0.18)   # subtle white spines in dark
            GRID  = (1, 1, 1, 0.08)   # soft grid in dark
    except Exception:
        # Fallback to the original static palette
        TEXT  = "#E8ECF6"
        TICK  = "#B8C1D9"
        SPINE = (1, 1, 1, 0.18)
        GRID  = (1, 1, 1, 0.08)
        SERIES = "#2F6BCE"
        TREND  = "#B91D73"
    # -----------------------------------------------------------------------

    # Project-provided data helper (unchanged)
    weekly_data = weekly_expenses(n, toggle_state)

    # Prepare figure/canvas early (transparent for glass card)
    fig = Figure(figsize=(9, 4.8), dpi=100)
    fig.patch.set_alpha(0.0)
    ax = fig.add_subplot(111)
    ax.set_facecolor("none")

    if not weekly_data:
        ax.text(0.5, 0.5, "No data available to plot.",
                ha="center", va="center", fontsize=12, color=TEXT)
        ax.set_axis_off()
        canvas = FigureCanvas(fig)
        canvas.setStyleSheet("background: transparent;")
        canvas.setMinimumSize(0, 0)
        return canvas

    # Respect original order reversal (assumes weekly_data is most-recent-first)
    weeks = list(weekly_data.keys())[::-1]
    amounts = [float(v) for v in list(weekly_data.values())[::-1]]

    x = np.arange(len(weeks))
    y = np.array(amounts, dtype=float)

    # Leave space for rotated tick labels
    fig.subplots_adjust(left=0.10, right=0.98, top=0.88, bottom=0.28)

    # Main series
    ax.plot(
        x, y,
        marker='o', markersize=4.0, linewidth=2.0,
        color=SERIES, label='Weekly Expenses',
        markerfacecolor=SERIES, markeredgecolor="white", markeredgewidth=0.8
    )

    # Trend line only if we have 2+ points
    if len(x) >= 2 and np.isfinite(y).all():
        try:
            coeffs = np.polyfit(x, y, 1)
            trend = np.poly1d(coeffs)
            ax.plot(x, trend(x), linestyle='--', color=TREND, linewidth=1.5, label='Trend')
        except Exception:
            pass

    # Axes & ticks
    ax.set_xticks(x)
    ax.set_xticklabels(weeks, rotation=45, ha='right', color=TEXT, fontsize=9)
    ax.tick_params(axis='y', colors=TICK, labelsize=9, length=3)

    # Labels & title
    ax.set_xlabel('Week', color=TEXT, fontsize=10)
    ax.set_ylabel('Total Expenses (€)', color=TEXT, fontsize=10)
    ax.set_title(f'Weekly Expense Trend (Last {n} Weeks)', color=TEXT, fontsize=13, pad=8)

    # Spines & grid
    for s in ax.spines.values():
        s.set_linewidth(1.0)
        s.set_color(SPINE)
    ax.grid(True, axis="y", color=GRID, linewidth=1.0)

    # Headroom for markers/labels
    try:
        y_max = max(y) if len(y) else 0.0
        ax.set_ylim(0, y_max * 1.10 if y_max > 0 else 1)
    except Exception:
        pass
    ax.margins(x=0.02)

    # Legend (light text, no frame)
    leg = ax.legend(loc='best', frameon=False)
    if leg:
        for t in leg.get_texts():
            t.set_color(TEXT)

    canvas = FigureCanvas(fig)
    canvas.setStyleSheet("background: transparent;")
    canvas.setMinimumSize(0, 0)
    return canvas

def plot_category_distribution_qt(
    month: str | None = None,
    toggle_state: int = 0,
    timeframe: str = "month",   # 'month' (default), '6m', 'year'
):
    """
    Pie of category proportions for a selected period.
    - If timeframe == 'month': uses the given `month` ('MM-YYYY') or the current month if None.
    - If timeframe in {'6m','year'}: aggregates across that range ending today.
    Respects toggle_state via filter_expenses_by_toggle(...).
    Returns a Qt FigureCanvas with a BLACK background.
    """
    # Local imports to avoid leaking pyplot state
    from collections import defaultdict
    from datetime import datetime, timedelta
    import re
    import matplotlib as mpl
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas

    _CAT_COLORS = {
        "Coffee": "#6F4E37", "Clothes": "#8E44AD", "Extra": "#90A4AE",
        "Going out": "#C2185B", "Health Care": "#00897B", "Home": "#8D6E63",
        "Memberships": "#7B1FA2", "Personal Projects": "#3949AB",
        "Pharmacy": "#26A69A", "Rent": "#455A64", "Restaurant": "#2E7D32",
        "Shopping": "#EC407A", "Sport": "#FB8C00", "Trasport": "#00ACC1",
        "Travel": "#1E88E5", "University Payment": "#D32F2F", "Groceries": "#4CAF50",
    }

    # ----- Resolve date range -----
    today = datetime.today()
    if timeframe == "6m":
        start_date = (today - timedelta(days=182)).strftime("%Y-%m-%d")
        end_date   = today.strftime("%Y-%m-%d")
        title_tag  = "Past 6 Months"
    elif timeframe == "year":
        start_date = (today - timedelta(days=365)).strftime("%Y-%m-%d")
        end_date   = today.strftime("%Y-%m-%d")
        title_tag  = "Past 12 Months"
    else:
        # single month
        if month is None:
            month = f"{today.month:02d}-{today.year}"
        if not re.fullmatch(r"\d{2}-\d{4}", month):
            raise ValueError("Month format should be 'MM-YYYY'")
        mm, yyyy = month.split("-")
        start_date = f"{yyyy}-{mm}-01"
        # simple end: today if current month else last day by month change trick
        if int(yyyy) == today.year and int(mm) == today.month:
            end = today
        else:
            first_next = datetime(int(yyyy) + (int(mm) == 12), (int(mm) % 12) + 1, 1)
            end = first_next - timedelta(days=1)
        end_date  = end.strftime("%Y-%m-%d")
        title_tag = datetime.strptime(f"01-{month}", "%d-%m-%Y").strftime("%b %Y")

    # ----- Data -----
    expenses   = get_all_expenses()
    categories = get_all_categories()
    filtered   = filter_expenses_by_toggle(expenses, categories, toggle_state)

    id_to_name = {c[0]: c[1] for c in categories}

    totals = defaultdict(float)
    for exp in filtered:
        d = str(exp[4])[:10]
        if start_date <= d <= end_date:
            name = id_to_name.get(exp[2], "Unknown")
            try:
                totals[name] += float(exp[3] or 0.0)
            except (TypeError, ValueError):
                pass

    # ----- Figure (BLACK background) -----
    fig = Figure(figsize=(8, 5), dpi=100)
    fig.patch.set_facecolor("#000000")  # <-- black figure bg
    ax = fig.add_subplot(111)
    ax.set_facecolor("#000000")         # <-- black axes bg

    if not totals:
        ax.text(0.5, 0.5, "No expenses in selected period.",
                ha="center", va="center", fontsize=12, color="#BBBBBB")
        ax.set_axis_off()
        return FigureCanvas(fig)

    labels = list(totals.keys())
    sizes  = list(totals.values())

    tab20 = mpl.cm.get_cmap("tab20").colors
    colors = [_CAT_COLORS.get(lbl, tab20[i % len(tab20)]) for i, lbl in enumerate(labels)]

    fig.subplots_adjust(left=0.08, right=0.68, top=0.88, bottom=0.10)
    wedges, _, autotexts = ax.pie(
        sizes,
        labels=None,
        colors=colors,
        autopct="%1.1f%%",
        startangle=140,
        textprops={"fontsize": 9, "color": "#FFFFFF"},  # white % labels on black
        wedgeprops={"linewidth": 0.75, "edgecolor": "white"},
        pctdistance=0.7
    )
    ax.axis("equal")

    leg = ax.legend(
        wedges, labels, title="Categories", loc="center left",
        bbox_to_anchor=(1.02, 0.5), borderaxespad=0.0, fontsize=9, title_fontsize=10,
        facecolor="#000000", edgecolor="#444444"  # legend panel styled for dark bg
    )
    leg.get_title().set_color("#FFFFFF")
    for t in leg.get_texts():
        t.set_color("#FFFFFF")

    ax.set_title(f"Spending Distribution — {title_tag}", fontsize=13, color="#FFFFFF")

    canvas = FigureCanvas(fig)
    canvas.setMinimumSize(0, 0)
    return canvas

def cat_sum_table_qt(timeframe: str = "month", toggle_state: int = 0):
    """
    Qt widget: table of total expenses per category for a given timeframe.

    Args:
        timeframe: 'month' | '6m' | 'year' (also accepts 'last_month')
        toggle_state: 0 = include all categories, 1 = exclude fixed
    Returns:
        QWidget (QTableWidget inside) ready to drop into the Insights grid.
    """
    from PySide6.QtWidgets import QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem, QSizePolicy, QLabel
    from PySide6.QtCore import Qt
    from collections import defaultdict
    from datetime import datetime, timedelta

    # ----- date range -----
    today = datetime.today()
    if timeframe == "month":
        start_date = today.replace(day=1).strftime("%Y-%m-%d")
        end_date   = today.strftime("%Y-%m-%d")
        title_lbl  = "This Month"
    elif timeframe == "last_month":
        first = today.replace(day=1)
        last_month_end = first - timedelta(days=1)
        start_date = last_month_end.replace(day=1).strftime("%Y-%m-%d")
        end_date   = last_month_end.strftime("%Y-%m-%d")
        title_lbl  = "Last Month"
    elif timeframe == "6m":
        start_date = (today - timedelta(days=182)).strftime("%Y-%m-%d")
        end_date   = today.strftime("%Y-%m-%d")
        title_lbl  = "Past 6 Months"
    elif timeframe == "year":
        start_date = (today - timedelta(days=365)).strftime("%Y-%m-%d")
        end_date   = today.strftime("%Y-%m-%d")
        title_lbl  = "Past 12 Months"
    else:
        start_date = today.replace(day=1).strftime("%Y-%m-%d")
        end_date   = today.strftime("%Y-%m-%d")
        title_lbl  = "This Month"

    # ----- data -----
    expenses   = get_all_expenses()
    categories = get_all_categories()
    filtered   = filter_expenses_by_toggle(expenses, categories, toggle_state)

    id_to_name = {c[0]: c[1] for c in categories}
    sums = defaultdict(float)

    for exp in filtered:
        d = (exp[4] or "")[:10]
        if start_date <= d <= end_date:
            cat_id = exp[2]
            try:
                sums[id_to_name.get(cat_id, "Unknown")] += float(exp[3])
            except (TypeError, ValueError):
                pass

    # ----- widget -----
    container = QWidget()
    container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(4)

    if not sums:
        msg = QLabel(f"No expenses in {title_lbl}.")
        msg.setAlignment(Qt.AlignCenter)
        msg.setStyleSheet("color:#666; font-size:12px;")
        layout.addWidget(msg, 1)
        return container

    items = sorted(sums.items(), key=lambda x: x[1], reverse=True)

    table = QTableWidget(len(items), 2, container)
    table.setHorizontalHeaderLabels(["Category", "Total Spent"])
    table.setEditTriggers(QTableWidget.NoEditTriggers)
    table.setSelectionBehavior(QTableWidget.SelectRows)
    table.setAlternatingRowColors(True)
    table.verticalHeader().setVisible(False)

    for r, (cat, total) in enumerate(items):
        table.setItem(r, 0, QTableWidgetItem(cat))
        v = QTableWidgetItem(f"{total:.2f}")
        v.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        table.setItem(r, 1, v)

    hdr = table.horizontalHeader()
    hdr.setSectionResizeMode(0, QHeaderView.Stretch)           # Category
    hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # Total

    layout.addWidget(table, 1)
    return container

# ─────────────────────────────
# 🎯 GOAL FUNCTIONS
# ─────────────────────────────

def plot_completeness_goals_qt(toggle_state: int = 0):
    """
    Qt version of plot_completeness_goals.
    Returns a FigureCanvas (Qt widget) showing each goal's saved vs remaining (stacked bar).

    Theme-aware (no API changes, functionality preserved):
    - Reads colors from frontend.theme.current_theme() when available.
    - Falls back to the original palette otherwise.
    """
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
    import numpy as np

    # ----- THEME LOOKUP (non-breaking) -------------------------------------
    def _hex(c):
        try:
            return c.name()  # QColor-like
        except Exception:
            return str(c)

    try:
        from frontend.theme import current_theme  # optional
        t = current_theme()
        variant = getattr(t, "variant", "dark")

        TEXT   = _hex(getattr(t, "TEXT", "#E8ECF6"))
        TICK   = _hex(getattr(t, "TICK", "#B8C1D9"))
        ACCENT = _hex(getattr(t, "ACCENT_BLUE", "#2F6BCE"))

        if variant == "light":
            SPINE  = (0, 0, 0, 0.25)   # subtle black in light
            GRID   = (0, 0, 0, 0.10)
            REMAIN = (0, 0, 0, 0.15)   # translucent dark for remaining
        else:
            SPINE  = (1, 1, 1, 0.18)   # subtle white in dark
            GRID   = (1, 1, 1, 0.06)
            REMAIN = (1, 1, 1, 0.18)   # translucent light for remaining
    except Exception:
        # Fallback to the original static palette
        ACCENT = "#2F6BCE"
        REMAIN = (1, 1, 1, 0.18)
        TEXT   = "#E8ECF6"
        TICK   = "#B8C1D9"
        SPINE  = (1, 1, 1, 0.18)
        GRID   = (1, 1, 1, 0.06)
    # -----------------------------------------------------------------------

    # Fetch categories and active (incomplete) goals
    categories = get_all_categories()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT name, amount_to_reach, amount_reached, category_id
            FROM goal
            WHERE completed = 0
        """)
        goals = cursor.fetchall()  # (name, total, saved, cat_id)

    # Apply toggle: exclude goals tied to fixed categories when toggle_state == 1
    if toggle_state == 1:
        valid_category_ids = {cat[0] for cat in categories if cat[3] == 0}  # cat[3] = type flag (0 = variable)
        goals = [g for g in goals if g[3] in valid_category_ids]

    # Prepare figure/canvas (transparent), dynamic height: ~0.6in per goal, min 3in
    height_in = max(3.0, 0.6 * max(1, len(goals)))
    fig = Figure(figsize=(10, height_in), dpi=100)
    fig.patch.set_alpha(0.0)

    ax = fig.add_subplot(111)
    ax.set_facecolor("none")

    if not goals:
        ax.text(0.5, 0.5, "No active goals found.",
                ha="center", va="center", fontsize=12, color=TEXT)
        ax.set_axis_off()
        canvas = FigureCanvas(fig)
        canvas.setStyleSheet("background: transparent;")
        canvas.setMinimumSize(0, 0)
        return canvas

    # Build series
    goal_names, reached, remaining = [], [], []
    for name, total, saved, _ in goals:
        try:
            total_f = float(total)
            saved_f = float(saved)
        except (TypeError, ValueError):
            continue
        rem = max(total_f - saved_f, 0.0)
        goal_names.append(str(name))
        reached.append(saved_f)
        remaining.append(rem)

    y_pos = np.arange(len(goal_names))

    # Bars (stacked)
    ax.barh(y_pos, reached, color=ACCENT, edgecolor="none", label="Saved")
    ax.barh(y_pos, remaining, left=reached, color=REMAIN, edgecolor="none", label="Remaining")

    # Labels & axes
    ax.set_yticks(y_pos)
    ax.set_yticklabels(goal_names, color=TEXT, fontsize=9)
    ax.invert_yaxis()
    ax.set_xlabel("Amount", color=TEXT, fontsize=10)
    ax.set_title("Goal Completion Progress", color=TEXT, fontsize=13, pad=8)

    # Ticks
    ax.tick_params(axis="x", colors=TICK, labelsize=9, length=3)
    ax.tick_params(axis="y", length=0)

    # Spines
    for s in ax.spines.values():
        s.set_linewidth(1.0)
        s.set_color(SPINE)

    # Grid (x only)
    ax.grid(axis="x", color=GRID, linewidth=1.0)

    # Legend
    leg = ax.legend(loc="lower right", frameon=False)
    if leg:
        for text in leg.get_texts():
            text.set_color(TEXT)

    # Percent labels on the saved segment
    for i, (r, rem_v) in enumerate(zip(reached, remaining)):
        total = r + rem_v
        if total <= 0:
            continue
        pct = int(round((r / total) * 100))
        if r < 0.08 * total:
            ax.text(r + (0.02 * max(total, 1.0)), i, f"{pct}%", va="center", ha="left",
                    fontsize=9, color=TEXT)
        else:
            ax.text(r * 0.5, i, f"{pct}%", va="center", ha="center",
                    fontsize=9, color="#FFFFFF")

    # Room for long goal names on the left; compact elsewhere
    fig.subplots_adjust(left=0.30, right=0.98, top=0.88, bottom=0.12)

    canvas = FigureCanvas(fig)
    canvas.setStyleSheet("background: transparent;")
    canvas.setMinimumSize(0, 0)
    return canvas

# ─────────────────────────────
# 💰 WALLET FUNCTIONS
# ─────────────────────────────

def simulate_networth_projection_qt(
    n_months: int,
    avg_income_per_month: float,
    exclude_months: list = None,
    target_currency: str = "EUR"
):
    """
    Qt version of simulate_networth_projection.
    Returns a FigureCanvas (Qt widget) plotting projected net worth over the next n_months
    with a ±25% envelope. Uses Matplotlib with QtAgg backend; no Streamlit.

    IMPORTANT (no FX conversion):
    - We no longer perform cross-currency conversion.
    - The starting net worth is computed **only from wallets already in `target_currency`**.
    - If other currencies exist, we exclude them and annotate the chart.

    UI theme tweaks:
    - Transparent figure/axes to sit on the dark glass tile
    - Electric-blue line (#2F6BCE), translucent fill
    - Light labels/ticks, subtle white spines/grid
    - Compact margins to fit tiles; ChartTile.mini will further slim for minis
    """
    from datetime import datetime
    from dateutil.relativedelta import relativedelta
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
    import matplotlib.dates as mdates

    # Avoid mutable default pitfalls
    if exclude_months is None:
        exclude_months = []

    # --- Data inputs (unchanged backend calls) ---
    avg_expenses = get_avg_monthly_expense(exclude_months, only_non_fixed=False)
    networth_by_currency = calc_networth(mode=1)  # {currency: amount}

    # Current net worth in target_currency ONLY (no cross-currency conversion)
    total_current = 0.0
    try:
        total_current = float((networth_by_currency or {}).get(target_currency, 0.0))
    except Exception:
        total_current = 0.0

    # Track excluded currencies (purely for user annotation)
    excluded_currencies = sorted(
        [c for c in (networth_by_currency or {}).keys() if c != target_currency]
    )

    # Build projection series
    base_date = datetime.today()
    dates, predicted, upper, lower = [], [], [], []

    # Fallbacks in case helpers return weird values
    try:
        avg_expenses = float(avg_expenses) if avg_expenses is not None else 0.0
    except Exception:
        avg_expenses = 0.0

    try:
        income_minus_exp = float(avg_income_per_month) - avg_expenses
    except Exception:
        income_minus_exp = -avg_expenses  # if income is bad, assume just expenses

    for i in range(max(0, int(n_months)) + 1):
        d = base_date + relativedelta(months=i)
        net = total_current + income_minus_exp * i
        dates.append(d)
        predicted.append(round(net, 2))
        upper.append(round(net * 1.25, 2))
        lower.append(round(net * 0.75, 2))

    # --- Figure/axes (transparent, dark-friendly) ---
    fig = Figure(figsize=(9.5, 4.8), dpi=100)
    fig.patch.set_alpha(0.0)  # fully transparent background

    ax = fig.add_subplot(111)
    ax.set_facecolor("none")  # transparent axes

    # Theme colors
    ACCENT = "#2F6BCE"          # electric blue (UI accent)
    FILL_ALPHA = 0.18
    TEXT = "#E8ECF6"            # light text
    TICK = "#B8C1D9"            # softer ticks
    SPINE = (1, 1, 1, 0.18)     # subtle white spines
    GRID = (1, 1, 1, 0.06)      # very soft grid

    # Plot
    ax.plot(dates, predicted, label="Predicted", color=ACCENT, linewidth=2.2)
    ax.fill_between(dates, upper, lower, color=ACCENT, alpha=FILL_ALPHA, label="±25% range")

    # Formatting
    locator = mdates.AutoDateLocator()
    formatter = mdates.ConciseDateFormatter(locator)
    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(formatter)

    # Titles/labels
    ax.set_title("Future Net Worth Projection", color=TEXT, fontsize=13, pad=8)
    ax.set_xlabel("Date", color=TEXT, fontsize=10)
    ax.set_ylabel(f"Net Worth ({target_currency})", color=TEXT, fontsize=10)

    # If we excluded other currencies, annotate so the user knows
    if excluded_currencies:
        note = f"Excluded currencies (no FX): {', '.join(excluded_currencies)}"
        ax.text(
            0.01, 0.02, note,
            transform=ax.transAxes,
            ha="left", va="bottom",
            color=TICK, fontsize=9
        )

    # Ticks
    ax.tick_params(axis="x", colors=TICK, labelsize=9, length=3)
    ax.tick_params(axis="y", colors=TICK, labelsize=9, length=3)

    # Spines
    for spine in ax.spines.values():
        spine.set_linewidth(1.0)
        spine.set_color(SPINE)

    # Grid
    ax.grid(True, which="major", color=GRID, linewidth=1.0)

    # Legend
    leg = ax.legend(loc="best", frameon=False)
    if leg:
        for text in leg.get_texts():
            text.set_color(TEXT)

    # Compact margins to fit tiles; modal still looks good
    fig.subplots_adjust(left=0.08, right=0.98, top=0.88, bottom=0.16)

    # Canvas (transparent)
    canvas = FigureCanvas(fig)
    canvas.setStyleSheet("background: transparent;")
    canvas.setMinimumSize(0, 0)
    return canvas

def budget_flow_qt(
    toggle_state: int = 0,
    timeframe: str = 'month',
    show_title: bool = True,
    monthly_budget: float | None = None,
) -> QWidget:
    """
    Sankey of how the budget splits across categories.
    UI-theming: fully transparent background so the glass/halo tile shows through,
    and light (white) typography for labels/hover.
    """
    from PySide6.QtWidgets import QWidget, QVBoxLayout, QSizePolicy
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor
    import plotly.graph_objects as go
    from collections import defaultdict
    from datetime import datetime, timedelta

    # ---- Category colors (names must match your DB) ----
    _CAT_COLORS = {
        "Coffee":              "#6F4E37",
        "Clothes":             "#8E44AD",
        "Extra":               "#90A4AE",
        "Going out":           "#C2185B",
        "Health Care":         "#00897B",
        "Home":                "#8D6E63",
        "Memberships":         "#7B1FA2",
        "Personal Projects":   "#3949AB",
        "Pharmacy":            "#26A69A",
        "Rent":                "#455A64",
        "Restaurant":          "#2E7D32",
        "Shopping":            "#EC407A",
        "Sport":               "#FB8C00",
        "Trasport":            "#00ACC1",
        "Travel":              "#1E88E5",
        "University Payment":  "#D32F2F",
        "Groceries":           "#4CAF50",
    }
    # Tile-friendly accents
    BUDGET_COLOR = "#2F6BCE"
    REMAIN_COLOR = "#BDBDBD"

    def _hex_to_rgba(hex_color: str, alpha: float) -> str:
        s = (hex_color or "#9E9E9E").lstrip('#')
        try:
            r, g, b = int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
        except Exception:
            r, g, b = 158, 158, 158
        a = max(0.0, min(1.0, float(alpha)))
        return f"rgba({r},{g},{b},{a})"

    today = datetime.today()

    # ----- Select date range & months multiplier -----
    if timeframe == 'month':
        start_date = today.replace(day=1).strftime('%Y-%m-%d')
        end_date   = today.strftime('%Y-%m-%d')
        time_title = "This Month"
        months_mult = 1
    elif timeframe == 'last_month':
        first_day_this_month = today.replace(day=1)
        last_month_end = first_day_this_month - timedelta(days=1)
        start_date = last_month_end.replace(day=1).strftime('%Y-%m-%d')
        end_date   = last_month_end.strftime('%Y-%m-%d')
        time_title = "Last Month"
        months_mult = 1
    elif timeframe == '6m':
        start_date = (today - timedelta(days=182)).strftime('%Y-%m-%d')
        end_date   = today.strftime('%Y-%m-%d')
        time_title = "Past 6 Months"
        months_mult = 6
    elif timeframe == 'year':
        start_date = (today - timedelta(days=365)).strftime('%Y-%m-%d')
        end_date   = today.strftime('%Y-%m-%d')
        time_title = "Past 12 Months"
        months_mult = 12
    else:
        start_date = today.replace(day=1).strftime('%Y-%m-%d')
        end_date   = today.strftime('%Y-%m-%d')
        time_title = "This Month"
        months_mult = 1

    # ----- Determine monthly budget (prefer param; fallback to profile) -----
    if monthly_budget is None:
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT monthly_budget FROM profile LIMIT 1")
            row = cur.fetchone()
            if not row:
                ph = QWidget(); ph.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                return ph
            monthly_budget = float(row[0])

    base_budget = float(monthly_budget) * months_mult  # scale by timeframe

    # ----- Load & filter expenses -----
    expenses   = get_all_expenses()
    categories = get_all_categories()
    filtered   = filter_expenses_by_toggle(expenses, categories, toggle_state)

    id_to_name = {c[0]: c[1] for c in categories}

    # Totals per category in range (already filtered as per toggle)
    cat_totals = defaultdict(float)
    for exp in filtered:
        exp_date = str(exp[4])[:10]
        if start_date <= exp_date <= end_date:
            try:
                cat_totals[id_to_name.get(exp[2], "Unknown")] += float(exp[3] or 0.0)
            except (TypeError, ValueError):
                pass

    # ----- Toggle behavior for BUDGET -----
    if toggle_state == 0:
        effective_budget = max(base_budget, 0.0)
    else:
        fixed_limits_sum = 0.0
        for c in categories:  # (id, name, limit_amount, type, currency)
            try:
                if c[3] == 1:
                    fixed_limits_sum += float(c[2] or 0.0)
            except Exception:
                pass
        effective_budget = max(base_budget - fixed_limits_sum * months_mult, 0.0)

    # ----- Build Sankey data (sorted for stable order) -----
    sorted_items    = sorted(cat_totals.items(), key=lambda kv: kv[1], reverse=True)
    categories_list = [k for k, _ in sorted_items]
    values          = [v for _, v in sorted_items]
    spent_total     = sum(values)
    remaining       = max(effective_budget - spent_total, 0.0)

    labels  = ['Budget'] + categories_list + ['Remaining']
    sources = [0] * (len(categories_list) + 1)
    targets = list(range(1, len(categories_list) + 1)) + [len(labels) - 1]
    flows   = values + [remaining]

    node_colors = [BUDGET_COLOR] + [_CAT_COLORS.get(n, "#9E9E9E") for n in categories_list] + [REMAIN_COLOR]
    link_colors = [_hex_to_rgba(_CAT_COLORS.get(n, "#9E9E9E"), 0.45) for n in categories_list]
    link_colors.append(_hex_to_rgba(REMAIN_COLOR, 0.35))

    # --- Figure (true transparent + light text) ---
    sankey = go.Sankey(
        arrangement='snap',
        node=dict(
            pad=14,
            thickness=16,
            line=dict(color="rgba(255,255,255,0.12)", width=0.6),
            label=labels,
            color=node_colors,
        ),
        link=dict(source=sources, target=targets, value=flows, color=link_colors),
        textfont=dict(color="#E8ECF6", size=12),  # force light labels for nodes/links
        hoverlabel=dict(bgcolor="rgba(255,255,255,0.92)", font_color="#0A0C14"),
    )
    fig = go.Figure(data=[sankey])

    fig.update_layout(
        title_text=(f"{time_title} Budget Flow" if show_title else ""),
        title_font=dict(color="#FFFFFF", size=14),
        font=dict(color="#E8ECF6", size=12),
        margin=dict(l=6, r=6, t=20 if show_title else 4, b=6),
        paper_bgcolor="rgba(0,0,0,0)",  # allow glass tile to show through
        plot_bgcolor="rgba(0,0,0,0)",
    )

    # --- Transparent HTML shell + CSS overrides to kill any Plotly white rects ---
    fragment = fig.to_html(
        full_html=False,
        include_plotlyjs='cdn',
        config={'displayModeBar': False, 'responsive': True}
    )
    html = f"""
    <html>
      <head>
        <meta charset="utf-8" />
        <style>
          html, body {{
            background: transparent !important;
            margin: 0; padding: 0; overflow: hidden;
          }}
          .plot-container, .plotly, .plotly div {{
            background: transparent !important;
          }}
          .js-plotly-plot .plotly .main-svg {{
            background: transparent !important;
          }}
          /* This rect is Plotly's plot background; force transparent. */
          .js-plotly-plot .plotly .bg {{
            fill: transparent !important;
          }}
          /* Expand to parent tile */
          .plotly-graph-div, .js-plotly-plot {{
            width: 100% !important;
            height: 100% !important;
          }}
        </style>
      </head>
      <body>{fragment}</body>
    </html>
    """

    # --- Container & WebView (transparent all the way down) ---
    container = QWidget()
    container.setAttribute(Qt.WA_StyledBackground, True)
    container.setStyleSheet("background: transparent;")
    container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    v = QVBoxLayout(container)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(0)

    view = QWebEngineView(container)
    view.setAttribute(Qt.WA_TranslucentBackground, True)
    view.setStyleSheet("background: transparent;")
    # Ensure the web page itself paints transparent (fixes white box on some Qt builds)
    view.page().setBackgroundColor(QColor(0, 0, 0, 0))

    view.setHtml(html)
    view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    v.addWidget(view)
    return container
