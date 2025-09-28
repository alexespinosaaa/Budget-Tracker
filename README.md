# Budget Tracker

A lightweight personal finance and budgeting tool to track **wallets, expenses, categories, and goals**, with built-in analytics and a simple Qt interface for displaying net worth.

---

![Python](https://img.shields.io/badge/python-3.11+-blue.svg)
![License](https://img.shields.io/badge/license-TODO-lightgrey.svg)
![CI](https://img.shields.io/badge/build-passing-brightgreen.svg)
![Code style](https://img.shields.io/badge/code%20style-PEP8-yellow.svg)

---

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Architecture](#architecture)
- [Data & Database](#data--database)
- [Installation](#installation)
- [Usage](#usage)
- [Examples & Screenshots](#examples--screenshots)
- [Analytics & Reports](#analytics--reports)
- [Building a Windows exe](#building-a-windows-exe)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [License](#license)
- [Acknowledgments](#acknowledgments)

---

## Overview

This project is a **personal budgeting/finance tool** built with Python and SQLite.  
It allows users to:

- Track **wallet balances** and **net worth** (by currency).
- Record and undo **expenses**.
- Organize spending with **categories**.
- Define and complete **goals**.
- Generate **analytics and descriptive statistics**.
- Display **net worth by currency** in a PySide6 (Qt) widget.

Designed for individuals who want a simple, extensible tool to manage personal finances while providing developers with a clean backend structure for further customization.

---

## Key Features

- 💸 **Expenses**
  - Record new expenses with `record_expense`.
  - Undo expenses with `redo_expense`.
  - Summaries by week/month.
  - Descriptive statistics: mean, median, and "mode" by expense name.

- 💰 **Wallets**
  - Manage multiple wallets with `get_all_wallets` and `order_by`.
  - Transfer between wallets (`transfer_money`).
  - Calculate net worth per currency with `calc_networth(mode=1)`.

- 🎯 **Goals**
  - Complete goals via `complete_goal`: deduct from wallet, log as expense, and delete the goal.
  - ⚠️ Legacy function `ordeBy` remains for backward compatibility.

- 📊 **Analytics**
  - Weekly aggregates (`weekly_expenses`).
  - Monthly comparisons (`month_comparasion` ⚠️ typo in function name preserved for compatibility).
  - Descriptive stats (`calc_descriptive_stats_per_month`).

- 🖥️ **UI**
  - Qt table widget `networth_by_currency_table_qt` showing net worth totals grouped by currency.

---

## Architecture

The project is structured into layers for clarity and maintainability:

main.py # Entry point for the application
│
├── ui/ # Qt windows and UI logic
│ ├── ... # (multiple files for different windows)
│
├── backend/
│ ├── crud/ # Low-level CRUD operations (database I/O)
│ │ ├── wallets.py
│ │ ├── expenses.py
│ │ ├── categories.py
│ │ └── goals.py
│ │
│ ├── high_level/ # High-level functions and analytics
│ │ ├── analysis.py # Graph plotting, analytics
│ │ └── reporting.py # Additional high-level utilities
│ │
│ └── db.py # SQLite connection handler
│
└── util/ # Configuration and helpers
└── config.py

### Flow

1. **`main.py`** starts the program and initializes the UI.  
2. **UI layer** (in `ui/`) manages user interactions and windows.  
3. **High-level layer** (in `backend/high_level/`) provides plotting functions and analytics used by the UI.  
4. **CRUD layer** (in `backend/crud/`) directly interacts with the database (`wallet`, `expense`, `goal`, `category`).  
5. **Database layer** (`backend/db.py`) manages connections to SQLite.  

This layered approach ensures a clean separation of concerns:  
- UI handles presentation.  
- High-level logic handles analytics/graphs.  
- CRUD handles raw database operations.  
- DB handles persistence.  

### Key functions

- **Wallets**: `get_all_wallets`, `get_wallet_by_id`, `order_by`, `transfer_money`, `calc_networth`
- **Expenses**: `add_expense`, `get_all_expenses`, `redo_expense`, `record_expense`, `weekly_expenses`, `calc_descriptive_stats_per_month`
- **Goals**: `complete_goal`, `ordeBy`
- **UI**: `networth_by_currency_table_qt`

---

## Data & Database

The project uses **SQLite** as its backend. The schema is defined in [`schema.sql`](schema.sql)-

---

## Installation

### Prerequisites
- Python **3.11+**
- SQLite (bundled with Python stdlib)
- Virtual environment recommended

### Steps

git clone https://github.com/your-username/budget-tracker.git
cd budget-tracker

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate   # Linux/macOS
.venv\Scripts\activate      # Windows

# Install dependencies
pip install -r requirements.txt

### Roadmap

Planned improvements and future features include:

- **Currency Conversion:**  
  Extend `calc_networth(mode=2)` to support automatic conversion between currencies using live exchange rates.  

- **Testing & CI:**  
  Add a test suite (e.g., with `pytest`) and configure continuous integration (e.g., GitHub Actions) to ensure reliability across updates.  

- **AI-Powered Analytics:**  
  Introduce AI/ML features for advanced insights, such as identifying unusual spending patterns, forecasting future expenses, and providing personalized recommendations.  

- **Enhanced UI:**  
  Expand beyond the current Qt table widget to include charts, dashboards, and richer visualizations of financial data.  

## Usage

After installation, run the application with:

python main.py
The main.py file starts the program and initializes the UI.

Common tasks
Record a new expense
from backend.high_level.analysis import record_expense
record_expense(
    name="Lunch",
    cost=12.50,
    date_str="2025-09-15",
    category_id=1,
    wallet_id=2,
    description="Sandwich and coffee"
)

Undo an expense
from backend.high_level.analysis import redo_expense
redo_expense(expense_id=10)
Calculate net worth per currency

from backend.high_level.analysis import calc_networth
print(calc_networth(mode=1))
# Example output: {'EUR': 200.0, 'USD': 150.0}

Display net worth in a Qt widget
from backend.high_level.analysis import networth_by_currency_table_qt
widget = networth_by_currency_table_qt()
widget.show()

## Examples & Screenshots

Below are example views and workflows of the application. Note the data shown is fictional for example purposes. 

### 1. Data analytics graphs
Visualizations including for weekly/monthly summaries and descriptive statistics (mean/median/mode).
![Data Analytics Graphs](docs/images/data_analytics_graphs.png)

---

### 2. Managing wallets
Create, edit, transfer between, and inspect wallet balances.
![Managing Wallets](docs/images/managing_wallets.png)

---

### 3. Profile view (import/export)
User profile and settings, with import/export features for backup and restore.
![Profile View - Import/Export](docs/images/profile_import_export.png)

---

### 4. Overview / Dashboard
High-level summary showing net worth by currency, recent transactions, and active goals.
![Overview Dashboard](docs/images/overview_dashboard.png)

## Analytics & Reports

The application includes several functions to analyze financial data:

from backend.high_level.analysis import weekly_expenses
print(weekly_expenses(4))
# Example output: {'2025-W37': 120.50, '2025-W36': 98.20, '2025-W35': 140.00} 
Returns a dictionary of weekly totals for the last n weeks.

from backend.high_level.analysis import month_comparasion
print(month_comparasion())
# Example output: (450.0, 520.0, 70.0)
Compares expenses of the current month with the previous month

from backend.high_level.analysis import calc_descriptive_stats_per_month
print(calc_descriptive_stats_per_month("07-2025"))
# Example output: {'mean': 23.45, 'median': 19.99, 'mode': 'Coffee'}
Provides mean, median, and mode (most repeated expense name) for a given month.

## Building a Windows exe

To distribute the application as a standalone executable, use PyInstaller.

### one file build
pyinstaller --noconfirm --onefile main.py

### one folder build
pyinstaller --noconfirm --onedir main.py

Since the project already includes the necessary icon files, make sure to add them when building:
pyinstaller --noconfirm --onefile main.py \
  --add-data "path/to/icons;icons"

Replace path/to/icons with the correct relative path inside your project.
The ;icons part ensures the files are placed into an icons/ folder alongside the executable.


## Contributing

Contributions, issues, and feature requests are welcome!  

If you would like to contribute:  
1. Fork the repository.  
2. Create a new branch (`git checkout -b feature/your-feature`).  
3. Commit your changes with clear messages.  
4. Push to your branch (`git push origin feature/your-feature`).  
5. Open a Pull Request.  

Please ensure code follows PEP 8 style guidelines and includes meaningful docstrings.  


## License

This project is licensed under the MIT License.  
You are free to use, modify, and distribute this software, provided that the original copyright notice is included in all copies or substantial portions of the software.

See the [LICENSE](LICENSE) file for details.

### Acknowledgments

- [PySide6](https://wiki.qt.io/Qt_for_Python) for the Qt-based UI components.  
- [SQLite](https://www.sqlite.org/) for the lightweight, embedded database.  
- [Python](https://www.python.org/) for being the foundation of the project.  
- The open-source community for inspiration and best practices.  

```bash