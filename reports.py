import io
from datetime import datetime, timedelta, date
import matplotlib.pyplot as plt
import pandas as pd
from db import get_expenses_between, aggregate_by_field, total_spent, get_budgets

plt.style.use("seaborn")

def iso_first_last_of_month(year: int, month: int):
    first = date(year, month, 1)
    if month == 12:
        last = date(year, 12, 31)
    else:
        last = date(year, month + 1, 1) - timedelta(days=1)
    return first.isoformat(), last.isoformat()

def monthly_text_summary(year: int, month: int) -> str:
    start, end = iso_first_last_of_month(year, month)
    total = total_spent(start, end)
    by_cat = aggregate_by_field(start, end, field="category")
    budgets = {b["category"]: b for b in get_budgets()}

    lines = []
    lines.append(f"📅 Monthly Report: {date(year, month, 1).strftime('%B %Y')}")
    lines.append(f"Total spent: {total:.2f}")
    lines.append("")
    lines.append("Top categories:")
    for item in by_cat[:8]:
        cat = item["field"] or "Uncategorized"
        total_cat = item["total"]
        budget = budgets.get(cat)
        if budget:
            lines.append(f"• {cat}: {total_cat:.2f} / budget {budget['amount']:.2f}")
        else:
            lines.append(f"• {cat}: {total_cat:.2f}")
    return "\n".join(lines)

def plot_weekly_spend(year:int, month:int):
    # build dataframe from daily totals for that month
    start, end = iso_first_last_of_month(year, month)
    expenses = get_expenses_between(start, end)
    if not expenses:
        return None

    df = pd.DataFrame(expenses)
    df['date'] = pd.to_datetime(df['date']).dt.date
    daily = df.groupby('date')['amount'].sum().reset_index()
    # resample to weekly by summing
    daily['date'] = pd.to_datetime(daily['date'])
    weekly = daily.set_index('date').resample('W-MON').sum().reset_index()  # weeks starting Monday

    fig, ax = plt.subplots(figsize=(8,4))
    ax.bar(weekly['date'].dt.strftime('%Y-%m-%d'), weekly['amount'], color='#2a9d8f')
    ax.set_title('Weekly spend')
    ax.set_xlabel('Week starting')
    ax.set_ylabel('Amount')
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()

    bio = io.BytesIO()
    fig.savefig(bio, format='png')
    plt.close(fig)
    bio.seek(0)
    return bio

def plot_vendor_top(year:int, month:int, top_n=10):
    start, end = iso_first_last_of_month(year, month)
    by_vendor = aggregate_by_field(start, end, field='vendor')
    if not by_vendor:
        return None
    df = pd.DataFrame(by_vendor)
    df = df[df['field'] != None]
    if df.empty:
        return None
    df = df.head(top_n)
    fig, ax = plt.subplots(figsize=(8,4))
    ax.barh(df['field'][::-1], df['total'][::-1], color='#e76f51')
    ax.set_title('Top vendors')
    ax.set_xlabel('Amount')
    plt.tight_layout()
    bio = io.BytesIO()
    fig.savefig(bio, format='png')
    plt.close(fig)
    bio.seek(0)
    return bio

