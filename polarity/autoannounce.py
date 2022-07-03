import logging

import hikari
import lightbulb
from aiohttp import web
from sqlalchemy import BigInteger, Boolean, Integer
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql.schema import Column

from . import cfg
from .user_commands import get_lost_sector_text
from .utils import Base as db_base_class
from .utils import _create_or_get

app = web.Application()


class BaseCustomEvent(hikari.Event):
    def __init__(self, bot) -> None:
        super().__init__()
        self.bot: lightbulb.BotApp = bot

    @property
    def app(self) -> lightbulb.BotApp:
        return self.bot


# Event that dispatches itself when a destiny 2 daily reset occurs.
# When a destiny 2 reset occurs, the reset_signaller.py process
# will send a signal to this process, which will be passed on
# as a hikari.Event that is dispatched bot-wide
class ResetSignal(BaseCustomEvent):
    qualifier: str

    def fire(self) -> None:
        self.bot.event_manager.dispatch(self)

    async def remote_fire(self, request: web.Request) -> web.Response:
        if str(request.remote) == "127.0.0.1":
            logging.info(
                "{self.qualifier} reset signal received and passed on".format(self=self)
            )
            self.fire()
            return web.Response(status=200)
        else:
            logging.warning(
                "{self.qualifier} reset signal received from non-local source, ignoring".format(
                    self=self
                )
            )
            return web.Response(status=401)

    def arm(self) -> None:
        # Run the hypercorn server to wait for the signal
        # This method is non-blocking
        app.add_routes(
            [
                web.post(
                    "/{self.qualifier}-reset-signal".format(self=self),
                    self.remote_fire,
                ),
            ]
        )


class DailyResetSignal(ResetSignal):
    qualifier = "daily"


class WeeklyResetSignal(ResetSignal):
    qualifier = "weekly"


class LostSectorPostSettings(db_base_class):
    __tablename__ = "lostsectorpostsettings"
    __mapper_args__ = {"eager_defaults": True}
    id = Column("id", Integer, primary_key=True)
    autoannounce_enabled = Column(
        "autoannounce_enabled", Boolean, default=True, server_default="t"
    )

    def __init__(self, id, autoannounce_enabled=True):
        self.id = id
        self.autoannounce_enabled = autoannounce_enabled


class LostSectorSignal(BaseCustomEvent):
    def __init__(self, bot: lightbulb.BotApp, id: int = 0) -> None:
        super().__init__(bot)
        self.id = id
        self.bot = bot

    async def conditional_daily_reset_repeater(self, event: DailyResetSignal) -> None:
        if await self.is_autoannounce_enabled():
            event.bot.dispatch(self)

    async def is_autoannounce_enabled(self):
        settings = await _create_or_get(
            LostSectorPostSettings, 0, autoannounce_enabled=True
        )
        return settings.autoannounce_enabled

    def arm(self) -> None:
        self.bot.listen()(self.conditional_daily_reset_repeater)


class AutopostServers(db_base_class):
    __tablename__ = "autopostservers"
    __mapper_args__ = {"eager_defaults": True}
    id = Column("id", BigInteger, primary_key=True)
    enabled = Column("enabled", Boolean, default=True, server_default="t")
    lost_sector_channels = relationship(
        "lostsectorautopostchannels", back_populates="autopostserver"
    )

    def __init__(self, id: int, enabled: bool = True):
        self.id = id
        self.enabled = enabled


class LostSectorAutopostChannels(db_base_class):
    __tablename__ = "lostsectorautopostchannels"
    __mapper_args__ = {"eager_defaults": True}
    id = Column("id", BigInteger, primary_key=True)
    server = relationship(
        "autopostservers", back_populates="lostsectorautopostchannels"
    )

    def __init__(self, id: int):
        self.id = id


async def lost_sector_announcer(event: LostSectorSignal):
    for channel_id in [
        # Test channel, not for prod
        986342568151379971,
    ]:
        channel = await event.bot.rest.fetch_channel(channel_id)
        # Can add hikari.GuildNewsChannel for announcement channel support
        # could be useful if we automate more stuff for Kyber
        if isinstance(channel, hikari.GuildTextChannel):
            await channel.send(embed=await get_lost_sector_text())


def _wire_listeners(bot: lightbulb.BotApp) -> None:
    """Connects all listener coroutines to the bot"""
    for handler in [
        lost_sector_announcer,
    ]:
        bot.listen()(handler)


async def arm(bot: lightbulb.BotApp) -> None:
    # Arm all signals
    DailyResetSignal(bot).arm()
    WeeklyResetSignal(bot).arm()
    LostSectorSignal(bot).arm()
    # Connect listeners to the bot
    _wire_listeners(bot)
    # Start the web server for periodic signals from apscheduler
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "localhost", cfg.port)
    await site.start()
