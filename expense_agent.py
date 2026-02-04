"""
Expense Agent using OpenAI Agents SDK.
Handles user queries about expenses and saves new expenses.
"""
import json
from datetime import datetime, timezone
from typing import Any
from agents import Agent, Runner, function_tool

import config
from db import (
    get_expenses_between, aggregate_by_field, total_spent,
    get_budgets, save_expense, list_categories
)
from reports import iso_first_last_of_month


# ============ Agent Tools ============

@function_tool
def get_monthly_summary(year: int = None, month: int = None) -> str:
    """
    Get a summary of expenses for a specific month.

    Args:
        year: The year (defaults to current year)
        month: The month 1-12 (defaults to current month)
    """
    now = datetime.now(timezone.utc)
    year = year or now.year
    month = month or now.month

    start, end = iso_first_last_of_month(year, month)
    total = total_spent(start, end)
    by_category = aggregate_by_field(start, end, field="category")
    by_vendor = aggregate_by_field(start, end, field="vendor")

    result = {
        "period": f"{year}-{month:02d}",
        "total_spent": round(total, 2),
        "by_category": [{"category": c["field"], "amount": round(c["total"], 2), "count": c["count"]}
                        for c in by_category[:10]],
        "top_vendors": [{"vendor": v["field"], "amount": round(v["total"], 2)}
                        for v in by_vendor[:5]]
    }
    return json.dumps(result, indent=2)


@function_tool
def get_budget_status() -> str:
    """
    Get the current budget status showing spending vs budget for each category.
    """
    now = datetime.now(timezone.utc)
    start, end = iso_first_last_of_month(now.year, now.month)
    by_category = aggregate_by_field(start, end, field="category")
    budgets = get_budgets()

    budget_map = {b["category"]: b["amount"] for b in budgets}
    spent_map = {c["field"]: c["total"] for c in by_category}

    status = []
    for category, budget in budget_map.items():
        spent = spent_map.get(category, 0)
        remaining = budget - spent
        status.append({
            "category": category,
            "budget": budget,
            "spent": round(spent, 2),
            "remaining": round(remaining, 2),
            "over_budget": remaining < 0
        })

    # Add categories with spending but no budget
    for cat_data in by_category:
        if cat_data["field"] not in budget_map:
            status.append({
                "category": cat_data["field"],
                "budget": None,
                "spent": round(cat_data["total"], 2),
                "remaining": None,
                "over_budget": False
            })

    return json.dumps(status, indent=2)


@function_tool
def get_recent_expenses(limit: int = 10) -> str:
    """
    Get the most recent expenses.

    Args:
        limit: Maximum number of expenses to return (default 10)
    """
    now = datetime.now(timezone.utc)
    start, end = iso_first_last_of_month(now.year, now.month)
    expenses = get_expenses_between(start, end)

    recent = expenses[-limit:] if len(expenses) > limit else expenses
    recent.reverse()  # Most recent first

    result = []
    for exp in recent:
        result.append({
            "date": exp["date"],
            "vendor": exp["vendor"] or "Unknown",
            "amount": exp["amount"],
            "category": exp["category"] or "Uncategorized",
            "currency": exp["currency"] or ""
        })

    return json.dumps(result, indent=2)


@function_tool
def get_category_spending(category: str, year: int = None, month: int = None) -> str:
    """
    Get detailed spending for a specific category.

    Args:
        category: The expense category to look up
        year: The year (defaults to current year)
        month: The month 1-12 (defaults to current month)
    """
    now = datetime.now(timezone.utc)
    year = year or now.year
    month = month or now.month

    start, end = iso_first_last_of_month(year, month)
    expenses = get_expenses_between(start, end)

    # Filter by category (case-insensitive)
    category_lower = category.lower()
    filtered = [e for e in expenses if (e["category"] or "").lower() == category_lower]

    total = sum(e["amount"] for e in filtered)

    return json.dumps({
        "category": category,
        "period": f"{year}-{month:02d}",
        "total": round(total, 2),
        "transaction_count": len(filtered),
        "transactions": [
            {"date": e["date"], "vendor": e["vendor"], "amount": e["amount"]}
            for e in filtered[-10:]  # Last 10
        ]
    }, indent=2)


@function_tool
def record_expense(amount: float, vendor: str = None, category: str = None,
                   date: str = None, currency: str = None, notes: str = None) -> str:
    """
    Record a new expense.

    Args:
        amount: The expense amount (required)
        vendor: The vendor/merchant name
        category: Expense category (e.g., Food, Transport, Entertainment)
        date: Date in YYYY-MM-DD format (defaults to today)
        currency: Currency code or symbol
        notes: Additional notes
    """
    if not date:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    expense_data = {
        "amount": amount,
        "vendor": vendor,
        "category": category or "Uncategorized",
        "date": date,
        "currency": currency,
        "notes": notes,
        "source": "chat"
    }

    save_expense(expense_data)

    return json.dumps({
        "status": "saved",
        "expense": expense_data
    }, indent=2)


@function_tool
def list_available_categories() -> str:
    """
    List all expense categories that have been used.
    """
    cats = list_categories()
    return json.dumps({"categories": sorted(cats)}, indent=2)


# ============ Agent Definition ============

expense_agent = Agent(
    name="ExpenseAssistant",
    instructions="""You are a helpful personal finance assistant. You help users track their expenses, understand their spending patterns, and stay within budget.

Your capabilities:
- Answer questions about spending (totals, categories, vendors, trends)
- Record new expenses when users tell you about purchases
- Check budget status and warn about overspending
- Provide insights and suggestions about spending habits

Guidelines:
- Be concise but friendly
- When recording expenses, confirm what was saved
- If a user mentions a purchase (e.g., "I spent $20 on lunch"), record it as an expense
- Use the tools to get accurate data - don't make up numbers
- Format currency amounts nicely
- If you don't have enough data to answer, say so honestly
""",
    model="gpt-4o-mini",
    tools=[
        get_monthly_summary,
        get_budget_status,
        get_recent_expenses,
        get_category_spending,
        record_expense,
        list_available_categories,
    ]
)


async def run_expense_agent(user_message: str) -> str:
    """
    Run the expense agent with a user message and return the response.
    """
    result = await Runner.run(expense_agent, user_message)
    return result.final_output
