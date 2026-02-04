import sqlite3
from typing import List, Dict

import config

DB_PATH = config.DATABASE_PATH


def get_conn():
    return sqlite3.connect(DB_PATH)


def init_db():
    conn = get_conn()
    c = conn.cursor()
    # expenses table
    c.execute("""
    CREATE TABLE IF NOT EXISTS expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT,
        vendor TEXT,
        amount REAL,
        currency TEXT,
        category TEXT,
        source TEXT,
        notes TEXT,
        email_id TEXT UNIQUE
    )
    """)
    # budgets table
    c.execute("""
    CREATE TABLE IF NOT EXISTS budgets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        category TEXT UNIQUE,
        amount REAL,
        period TEXT DEFAULT 'monthly'
    )
    """)
    # sync state table
    c.execute("""
    CREATE TABLE IF NOT EXISTS sync_state (
        id INTEGER PRIMARY KEY,
        last_sync_timestamp TEXT,
        last_history_id TEXT
    )
    """)
    conn.commit()
    conn.close()


def save_expense(exp: Dict):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
    INSERT INTO expenses (date, vendor, amount, currency, category, source, notes, email_id)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        exp.get("date"),
        exp.get("vendor"),
        float(exp.get("amount") or 0),
        exp.get("currency"),
        exp.get("category"),
        exp.get("source"),
        exp.get("notes"),
        exp.get("email_id")
    ))
    conn.commit()
    conn.close()


def set_budget(category: str, amount: float, period: str = "monthly"):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
    INSERT INTO budgets (category, amount, period) VALUES (?, ?, ?)
    ON CONFLICT(category) DO UPDATE SET amount=excluded.amount, period=excluded.period
    """, (category, amount, period))
    conn.commit()
    conn.close()


def get_budgets() -> List[Dict]:
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT category, amount, period FROM budgets")
    rows = c.fetchall()
    conn.close()
    return [{"category": r[0], "amount": r[1], "period": r[2]} for r in rows]


def list_categories() -> List[str]:
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT DISTINCT category FROM expenses WHERE category IS NOT NULL")
    rows = c.fetchall()
    conn.close()
    return [r[0] for r in rows if r[0]]


def get_expenses_between(start_date: str, end_date: str) -> List[Dict]:
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
    SELECT id, date, vendor, amount, currency, category, source, notes
    FROM expenses
    WHERE date BETWEEN ? AND ?
    ORDER BY date ASC
    """, (start_date, end_date))
    rows = c.fetchall()
    conn.close()
    return [
        {"id": r[0], "date": r[1], "vendor": r[2], "amount": r[3],
         "currency": r[4], "category": r[5], "source": r[6], "notes": r[7]}
        for r in rows
    ]


def aggregate_by_field(start_date: str, end_date: str, field: str = "category"):
    if field not in ("category", "vendor"):
        field = "category"
    conn = get_conn()
    c = conn.cursor()
    q = f"""
    SELECT {field}, SUM(amount) as total, COUNT(*) as count
    FROM expenses
    WHERE date BETWEEN ? AND ?
    GROUP BY {field}
    ORDER BY total DESC
    """
    c.execute(q, (start_date, end_date))
    rows = c.fetchall()
    conn.close()
    return [{"field": r[0] or "Uncategorized", "total": r[1], "count": r[2]} for r in rows]


def total_spent(start_date: str, end_date: str) -> float:
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT SUM(amount) FROM expenses WHERE date BETWEEN ? AND ?", (start_date, end_date))
    row = c.fetchone()
    conn.close()
    return float(row[0] or 0)


def assign_category_to_expense(expense_id: int, category: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE expenses SET category = ? WHERE id = ?", (category, expense_id))
    conn.commit()
    conn.close()


def get_sync_state() -> Dict:
    """Get the last sync state for Gmail."""
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT last_sync_timestamp, last_history_id FROM sync_state WHERE id = 1")
    row = c.fetchone()
    conn.close()
    if row:
        return {"last_sync_timestamp": row[0], "last_history_id": row[1]}
    return {"last_sync_timestamp": None, "last_history_id": None}


def set_sync_state(timestamp: str = None, history_id: str = None):
    """Update the sync state for Gmail."""
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
    INSERT INTO sync_state (id, last_sync_timestamp, last_history_id)
    VALUES (1, ?, ?)
    ON CONFLICT(id) DO UPDATE SET
        last_sync_timestamp = COALESCE(excluded.last_sync_timestamp, last_sync_timestamp),
        last_history_id = COALESCE(excluded.last_history_id, last_history_id)
    """, (timestamp, history_id))
    conn.commit()
    conn.close()


def email_already_processed(email_id: str) -> bool:
    """Check if an email has already been processed."""
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT 1 FROM expenses WHERE email_id = ?", (email_id,))
    row = c.fetchone()
    conn.close()
    return row is not None
