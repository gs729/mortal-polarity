import asyncio
import datetime as dt
import logging

import hikari
import lightbulb
from aiohttp import web
from sqlalchemy import BigInteger, Boolean, Integer, select
from sqlalchemy.sql.schema import Column

from . import cfg
from .user_commands import get_lost_sector_text
from .utils import Base as db_base_class
from .utils import _create_or_get, db_session

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


class LostSectorAutopostChannel(db_base_class):
    __tablename__ = "lostsectorautopostchannel"
    __mapper_args__ = {"eager_defaults": True}
    id = Column("id", BigInteger, primary_key=True)
    server_id = Column("server_id", BigInteger)
    enabled = Column("enabled", Boolean)

    def __init__(self, id: int, server_id: int, enabled: bool):
        self.id = id
        self.server_id = server_id
        self.enabled = enabled


async def lost_sector_announcer(event: LostSectorSignal):
    async with db_session() as session:
        async with session.begin():
            channel_id_list = (
                await session.execute(
                    select(LostSectorAutopostChannel).where(
                        LostSectorAutopostChannel.enabled == True
                    )
                )
            ).fetchall()
            channel_id_list = [] if channel_id_list is None else channel_id_list
            channel_id_list = [channel[0].id for channel in channel_id_list]

    logging.info("Announcing lost sectors to {} channels".format(len(channel_id_list)))
    start_time = dt.datetime.now()
    embed = await get_lost_sector_text()

    async def _send_embed_if_guild_channel(channel_id: int) -> None:
        channel = await event.bot.rest.fetch_channel(channel_id)
        # Can add hikari.GuildNewsChannel for announcement channel support
        # could be useful if we automate more stuff for Kyber
        if isinstance(channel, hikari.GuildTextChannel):
            await channel.send(embed=embed)

    await asyncio.gather(
        *[_send_embed_if_guild_channel(channel_id) for channel_id in channel_id_list]
    )

    end_time = dt.datetime.now()
    time_delta = end_time - start_time
    minutes = time_delta.seconds // 60
    seconds = time_delta.seconds % 60
    logging.info(
        "Announcement completed in {} minutes and {} seconds".format(minutes, seconds)
    )


@lightbulb.command("autopost", "Server autopost management")
@lightbulb.implements(lightbulb.SlashCommandGroup)
async def autopost_cmd_group(ctx: lightbulb.Context) -> None:
    await ctx.respond(
        "Server autopost management commands, please use the subcommands here to manage autoposts"
    )


@autopost_cmd_group.child
@lightbulb.option(
    "option",
    "Enabled or disabled",
    type=str,
    choices=["Enabled", "Disabled"],
    required=True,
)
@lightbulb.command(
    "lostsector",
    "Lost sector auto posts",
    auto_defer=True,
    guilds=cfg.kyber_discord_server_id,
)
@lightbulb.implements(lightbulb.SlashSubCommand)
async def lost_sector_auto(ctx: lightbulb.Context) -> None:
    channel_id: int = ctx.channel_id
    server_id: int = ctx.guild_id
    option: bool = True if ctx.options.option.lower() == "enabled" else False
    async with db_session() as session:
        async with session.begin():
            channel = await session.get(LostSectorAutopostChannel, channel_id)
            if channel is None:
                channel = LostSectorAutopostChannel(channel_id, server_id, option)
                session.add(channel)
            else:
                channel.enabled = option
    await ctx.respond(
        "Lost sector autoposts {}".format("enabled" if option else "disabled")
    )


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
    # Connect commands
    bot.command(autopost_cmd_group)
    # Start the web server for periodic signals from apscheduler
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "localhost", cfg.port)
    await site.start()
