EXPENSEBOT – PROJECT DOCUMENTATION (PLAIN TEXT)

ExpenseBot is a Telegram-based personal finance assistant that helps you automatically track expenses from Gmail receipts, uploaded pictures of receipts, and text messages. It stores everything in a SQLite database and can generate reports.

ExpenseBot is a Telegram-based personal expense tracker that automatically collects and records your expenses from multiple sources. It can pull receipt emails from Gmail, extract information from photos of paper receipts using OCR and AI, and parse manually typed text messages describing expenses. All extracted data—such as amount, vendor, date, and category—is stored in a local SQLite database, allowing you to generate monthly summaries and analyze your spending later.

------------------------------------------------------------
FEATURES
------------------------------------------------------------

1. Pull expenses from Gmail
Use the /pull_gmail command.
The bot scans your Gmail for receipts, invoices, subscriptions, and payment confirmations.
It extracts date, vendor, amount, currency, category, and notes, then saves the expense into expenses.db.

2. Upload receipt photos
Send any picture of a receipt to the bot.
The bot uses OCR and AI to extract vendor, amount, currency, date, and category, then saves the expense.

3. Send text messages as expenses
Send a message like:
Starbucks coffee 4.80€
or:
Taxi 28 USD yesterday
The bot parses the text using an AI model and stores the expense.

4. Monthly and vendor-based reports
You can generate summaries by month, top vendors, category totals, and spending trends (if you enable reporting commands).

------------------------------------------------------------
ARCHITECTURE OVERVIEW
------------------------------------------------------------

Project structure:

expense-bot/
- bot.py              (Telegram bot logic)
- db.py               (database functions)
- extractor.py        (text and image extraction using AI/OCR)
- gmail_utils.py      (Gmail API integration)
- reports.py          (monthly summaries and charts)
- requirements.txt    (dependencies)
- credentials.json    (Gmail OAuth credentials)
- token.json          (generated after first Gmail login)
- README.md           (project documentation)

------------------------------------------------------------
FILE DESCRIPTIONS
------------------------------------------------------------

bot.py
This file contains all Telegram bot logic:
- /start command
- /pull_gmail command
- handling text messages as manual expenses
- handling uploaded images as receipt expenses
It uses extractor.py for parsing, db.py for saving, and gmail_utils.py for Gmail integration.

db.py
Handles local SQLite database:
- Creates expenses.db on startup
- Defines table fields: date, vendor, amount, currency, category, source, notes
- save_expense() inserts new expenses

extractor.py
Responsible for converting text or images into structured expense data.
- extract_from_text(): parses natural language text into expense fields
- extract_from_receipt_image(): extracts information from receipt photos using OCR + AI

gmail_utils.py
Handles Gmail fetching:
- Authenticates using credentials.json and token.json
- Searches for recent emails containing words like “receipt”, “invoice”, “payment”, “subscription”
- Returns subject and body for further processing

reports.py
Generates monthly summaries and optional charts.
Can produce:
- total spent by month
- spending by vendor
- spending by category
- optional plots (if enabled)

requirements.txt
List of required Python packages:
python-telegram-bot
google-api-python-client
google-auth
google-auth-oauthlib
openai
pillow
pytesseract (optional OCR)
matplotlib
pandas
python-dateutil

------------------------------------------------------------
SETUP INSTRUCTIONS
------------------------------------------------------------

1. Install dependencies:
pip install -r requirements.txt

2. Create a Telegram bot:
Talk to @BotFather on Telegram and create a bot.
Copy the bot token and set it as an environment variable:
export TELEGRAM_TOKEN="your-token"

3. Provide OpenAI API key:
export OPENAI_API_KEY="your-key"

4. Set up Gmail access:
Go to https://console.cloud.google.com/apis/credentials
Create an OAuth 2.0 Client ID of type "Desktop Application".
Download the JSON file and save it as:
credentials.json
On first run of /pull_gmail, the bot will open a browser for authentication.
token.json will be generated automatically.

5. Run the bot:
python bot.py

------------------------------------------------------------
NEXT STEPS / EXTENSIONS
------------------------------------------------------------

Possible upgrades:
- Add budgets and category limits
- Export expenses to Google Sheets
- Add multi-currency support
- Add commands like /stats, /top_vendors, /plot
- Deploy to a server using Docker and systemd
- Support multiple users

This documentation provides an overview of the system so you can maintain or extend it later.

