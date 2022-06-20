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

test_env = int(_getenv("TEST_ENV")) if str(_getenv("TEST_ENV")) != "false" else False

admin_role = int(_getenv("ADMIN_ROLE"))
