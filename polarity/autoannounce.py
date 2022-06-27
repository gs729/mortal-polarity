import logging

import hikari
import lightbulb
from aiohttp import web
from sqlalchemy import Boolean, Integer
from sqlalchemy.sql.schema import Column
from . import cfg
from .utils import Base as db_base_class

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


class LostSectorSignal(BaseCustomEvent, db_base_class):
    __tablename__ = "lostsectorsignal"
    __mapper_args__ = {"eager_defaults": True}
    name = Column("id", Integer, primary_key=True)
    description = Column(
        "autoannounce_enabled", Boolean, default=True, server_default="t"
    )

    def __init__(
        self, bot: lightbulb.BotApp, id: int = 0, autoannounce_enabled: bool = True
    ) -> None:
        super().__init__()
        self.id = id
        # Need to create or get this
        self.autoannounce_enabled = autoannounce_enabled
        self.bot = bot

    def conditional_daily_reset_repeater(self, event: DailyResetSignal) -> None:
        if self.autoannounce_enabled:
            event.bot.dispatch(self)


async def lost_sector(event: LostSectorSignal):
    for channel_id in []:
        channel = await event.bot.rest.fetch_channel(channel_id)
        # Can add hikari.GuildNewsChannel for announcement channel support
        # could be useful if we automate more stuff for Kyber
        if isinstance(channel, hikari.GuildTextChannel):
            await channel.send(
                "Lost sector! Please check the website for more information."
            )


def _wire_listeners(bot: lightbulb.BotApp) -> None:
    """Connects all listener coroutines to the bot"""
    for handler in [
        lost_sector,
    ]:
        bot.listen()(handler)


async def arm(bot: lightbulb.BotApp) -> None:
    # Arm all signals
    DailyResetSignal(bot).arm()
    WeeklyResetSignal(bot).arm()
    # Connect listeners to the bot
    _wire_listeners(bot)
    # Start the web server for periodic signals from apscheduler
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "localhost", cfg.port)
    await site.start()
