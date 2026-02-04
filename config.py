import yaml
from pathlib import Path

# Load config from YAML
_config_path = Path(__file__).parent / "config.yaml"
with open(_config_path) as f:
    _config = yaml.safe_load(f)

TELEGRAM_TOKEN = _config["telegram_token"]
OPENAI_API_KEY = _config["openai_api_key"]

GMAIL_CREDENTIALS_FILE = _config.get("gmail_credentials_file", "credentials.json")
GMAIL_TOKEN_FILE = _config.get("gmail_token_file", "token.json")

DATABASE_PATH = _config.get("database_path", "expenses.db")
