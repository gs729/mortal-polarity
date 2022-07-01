import re

import hikari
from tortoise import Tortoise


from . import cfg

_DB_INITIALISED = False

url_regex = re.compile(
    "http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+"
)


class RefreshCmdListEvent(hikari.Event):
    def __init__(self, bot: hikari.GatewayBot, sync: bool = True):
        super().__init__()
        # Whether to run the sync_application_commands method of the app
        self.bot = bot
        self.sync = sync

    @property
    def app(self):
        return self.bot

    def dispatch(self):
        self.bot.event_manager.dispatch(self)


async def init_db_session():
    """Coroutine that initialises a db session if one has not been initialised already"""
    await Tortoise.init(
        db_url=cfg.db_url,
        modules={"models": ["polarity.user_commands", "polarity.autoannounce"]},
    )
