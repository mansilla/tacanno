import logging
from datetime import datetime, timezone
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

import config
from db import init_db, set_budget, get_budgets, list_categories
from extractor import extract_from_receipt_image
from gmail_agent import pull_and_process_emails
from expense_agent import run_expense_agent
from reports import monthly_text_summary, plot_weekly_spend, plot_vendor_top

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ---------------- Message Handler (Agent-based) ----------------

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all text messages using the expense agent."""
    user_message = update.message.text

    try:
        response = await run_expense_agent(user_message)
        await update.message.reply_text(response)
    except Exception as e:
        logger.exception("Agent error")
        await update.message.reply_text(
            "Sorry, I encountered an error processing your message. Please try again."
        )


# ---------------- Command Handlers ----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome to Expense Bot!\n\n"
        "I can help you track and understand your expenses.\n\n"
        "Just talk to me naturally:\n"
        "- \"I spent $15 on lunch at Chipotle\"\n"
        "- \"How much did I spend this month?\"\n"
        "- \"What's my biggest expense category?\"\n"
        "- \"Am I over budget on Food?\"\n\n"
        "Commands:\n"
        "/pull_gmail - Import expenses from Gmail\n"
        "/report - Get monthly report with charts\n"
        "/set_budget <category> <amount> - Set a budget\n"
        "/help - See all commands"
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "Commands:\n"
        "/pull_gmail - Pull Gmail and extract expenses\n"
        "/report [YYYY-MM] - Monthly report with charts\n"
        "/set_budget <category> <amount> - Set monthly budget\n"
        "/list_budgets - Show all budgets\n"
        "/categories - List known categories\n\n"
        "Or just chat with me:\n"
        "- Send receipt photos\n"
        "- Tell me about expenses: \"Coffee $5 at Starbucks\"\n"
        "- Ask questions: \"How much did I spend on food?\""
    )
    await update.message.reply_text(help_text)


async def pull_gmail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pull emails from Gmail and process with AI classification."""
    await update.message.reply_text("Pulling new emails from Gmail...")

    try:
        result = await pull_and_process_emails()
        await update.message.reply_text(
            f"Processed {result['emails_checked']} emails.\n"
            f"Found {result['expenses_found']} expense-related emails.\n"
            f"Saved {result['expenses_saved']} new expenses."
        )
    except FileNotFoundError as e:
        await update.message.reply_text(f"Gmail setup required: {e}")
    except Exception as e:
        logger.exception("Gmail pull failed")
        await update.message.reply_text(f"Failed to pull Gmail: {e}")


async def image_expense(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle receipt image uploads."""
    photo = update.message.photo[-1]
    file = await photo.get_file()
    img_bytes = await file.download_as_bytearray()

    try:
        data = extract_from_receipt_image(img_bytes)
    except Exception as e:
        logger.exception("Receipt extraction failed")
        await update.message.reply_text("Couldn't extract receipt. Try a clearer photo.")
        return

    if not data or not data.get("amount"):
        await update.message.reply_text("No amount found on the receipt.")
        return

    # Use agent to record the expense
    expense_desc = f"Receipt: {data.get('vendor', 'Unknown')} ${data.get('amount')} {data.get('category', '')}"
    response = await run_expense_agent(expense_desc)
    await update.message.reply_text(response)


async def set_budget_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Usage: /set_budget <category> <amount>")
        return

    category = args[0]
    try:
        amount = float(args[1])
    except ValueError:
        await update.message.reply_text("Amount should be a number. Example: /set_budget Food 300")
        return

    set_budget(category, amount)
    await update.message.reply_text(f"Budget set: {category} = {amount:.2f}/month")


async def list_budgets_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    budgets = get_budgets()
    if not budgets:
        await update.message.reply_text("No budgets set. Use /set_budget <category> <amount>")
        return

    lines = ["Your budgets:"]
    for b in budgets:
        lines.append(f"  {b['category']}: {b['amount']:.2f}/{b['period']}")
    await update.message.reply_text("\n".join(lines))


async def categories_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cats = list_categories()
    if not cats:
        await update.message.reply_text("No categories yet. Add some expenses first!")
        return
    await update.message.reply_text("Categories:\n" + "\n".join(f"  {c}" for c in sorted(cats)))


async def report_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Parse optional YYYY-MM
    if context.args:
        try:
            ym = context.args[0]
            year, month = map(int, ym.split("-"))
        except ValueError:
            await update.message.reply_text("Format: /report YYYY-MM (e.g. /report 2025-11)")
            now = datetime.now(timezone.utc)
            year, month = now.year, now.month
    else:
        now = datetime.now(timezone.utc)
        year, month = now.year, now.month

    await update.message.reply_text(f"Generating report for {year}-{month:02d}...")

    text = monthly_text_summary(year, month)
    await update.message.reply_text(text)

    # Weekly chart
    weekly_bio = plot_weekly_spend(year, month)
    if weekly_bio:
        weekly_bio.seek(0)
        await update.message.reply_photo(photo=weekly_bio, caption="Weekly spending")

    # Vendor chart
    vendor_bio = plot_vendor_top(year, month, top_n=10)
    if vendor_bio:
        vendor_bio.seek(0)
        await update.message.reply_photo(photo=vendor_bio, caption="Top vendors")


# ---------------- Main ----------------

def main():
    init_db()
    app = ApplicationBuilder().token(config.TELEGRAM_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("pull_gmail", pull_gmail))
    app.add_handler(CommandHandler("report", report_cmd))
    app.add_handler(CommandHandler("set_budget", set_budget_cmd))
    app.add_handler(CommandHandler("list_budgets", list_budgets_cmd))
    app.add_handler(CommandHandler("categories", categories_cmd))

    # Message handlers
    app.add_handler(MessageHandler(filters.PHOTO, image_expense))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Expense Bot running...")
    app.run_polling()


if __name__ == "__main__":
    main()
