from os import getenv as _getenv
from sqlalchemy.ext.asyncio import AsyncSession

# Discord API Token
main_token = _getenv("MAIN_TOKEN")
repeater_token = _getenv("MAIN_TOKEN")

# Url for the bot and scheduler db
# SQAlchemy doesn't play well with postgres://, hence we replace
# it with postgresql://
db_url = _getenv("DATABASE_URL")
if db_url.startswith("postgres"):
    repl_till = db_url.find("://")
    db_url = db_url[repl_till:]
    db_url_async = "postgresql+asyncpg" + db_url
    db_url = "postgresql" + db_url

# Async SQLAlchemy DB Session KWArg Parameters
db_session_kwargs = {"expire_on_commit": False, "class_": AsyncSession}

test_env = _getenv("TEST_ENV") or "false"
test_env = int(test_env) if test_env != "false" else False

admin_role = int(_getenv("ADMIN_ROLE"))

kyber_discord_server_id = int(_getenv("KYBER_DISCORD_SERVER_ID"))

lightbulb_params = (
    # Only use the test env for testing if it is specified
    {"token": main_token, "default_enabled_guilds": test_env}
    if test_env
    else {"token": main_token}  # Test env isn't specified in production
)

gsheets_credentials = {
    "type": "service_account",
    "project_id": _getenv("SHEETS_PROJECT_ID"),
    "private_key_id": _getenv("SHEETS_PRIVATE_KEY_ID"),
    "private_key": _getenv("SHEETS_PRIVATE_KEY").replace("\\n", "\n"),
    "client_email": _getenv("SHEETS_CLIENT_EMAIL"),
    "client_id": _getenv("SHEETS_CLIENT_ID"),
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": _getenv("SHEETS_CLIENT_X509_CERT_URL"),
}

sheets_ls_url = _getenv("SHEETS_LS_URL")

port = int(_getenv("PORT")) or 5000
