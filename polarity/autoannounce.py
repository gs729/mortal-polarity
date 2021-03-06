import asyncio
import datetime as dt
import logging
from typing import Union

import hikari
import lightbulb
import re
from aiohttp import web
from sqlalchemy import select, update

from . import cfg, custom_checks
from .schemas import (
    LostSectorAutopostChannel,
    LostSectorPostSettings,
    XurAutopostChannel,
    XurPostSettings,
)
from .user_commands import get_lost_sector_text, get_xur_text
from .utils import _create_or_get, db_session, operation_timer

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


class WeekendResetSignal(ResetSignal):
    qualifier = "weekend"


class LostSectorSignal(BaseCustomEvent):
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


class XurSignal(BaseCustomEvent):
    async def conditional_weekend_reset_repeater(
        self, event: WeekendResetSignal
    ) -> None:
        if not await self.is_autoannounce_enabled():
            return

        settings: XurPostSettings = await _create_or_get(XurPostSettings, 0)

        # Debug code
        if cfg.test_env and cfg.trigger_without_url_update:
            event.bot.dispatch(self)

        await settings.wait_for_url_update()
        event.bot.dispatch(self)

    async def is_autoannounce_enabled(self):
        settings = await _create_or_get(XurPostSettings, 0, autoannounce_enabled=True)
        return settings.autoannounce_enabled

    def arm(self) -> None:
        self.bot.listen()(self.conditional_weekend_reset_repeater)

    async def wait_for_url_update(self):
        settings: XurPostSettings = await _create_or_get(XurPostSettings, 0)
        await settings.wait_for_url_update()


async def _send_embed_if_textable_channel(
    channel_id: int,
    event: hikari.Event,
    embed: hikari.Embed,
    channel_table,  # Must be the class of the channel, not an instance
) -> None:
    try:
        channel = await event.bot.rest.fetch_channel(channel_id)
        # Can add hikari.GuildNewsChannel for announcement channel support
        # could be useful if we automate more stuff for Kyber
        if isinstance(channel, hikari.TextableChannel):
            async with db_session() as session:
                async with session.begin():
                    channel_record = await session.get(channel_table, channel_id)
                    channel_record.last_msg_id = await channel.send(embed=embed)
    except (hikari.ForbiddenError, hikari.NotFoundError):
        logging.warning(
            "Channel {} not found or not messageable, disabling posts in {}".format(
                channel_id, str(channel_table.__class__.__name__)
            )
        )
        async with db_session() as session:
            async with session.begin():
                await session.execute(
                    update(channel_table)
                    .where(channel_table.id == channel_id)
                    .values(enabled=False)
                )


async def _edit_embedded_message(
    message_id: int,
    channel_id: int,
    bot: hikari.GatewayBot,
    embed: hikari.Embed,
) -> None:
    try:
        msg: hikari.Message = await bot.rest.fetch_message(channel_id, message_id)
        if isinstance(msg, hikari.Message):
            await msg.edit(content="", embed=embed)
    except (hikari.ForbiddenError, hikari.NotFoundError):
        logging.warning("Message {} not found or not editable".format(message_id))


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
    with operation_timer("Lost sector announce"):
        embed = await get_lost_sector_text()

        await asyncio.gather(
            *[
                _send_embed_if_textable_channel(
                    channel_id,
                    event,
                    embed,
                    LostSectorAutopostChannel,
                )
                for channel_id in channel_id_list
            ]
        )


async def xur_announcer(event: XurSignal):
    async with db_session() as session:
        async with session.begin():
            settings: XurPostSettings = await session.get(XurPostSettings, 0)
        async with session.begin():
            channel_id_list = (
                await session.execute(
                    select(XurAutopostChannel).where(XurAutopostChannel.enabled == True)
                )
            ).fetchall()
            channel_id_list = [] if channel_id_list is None else channel_id_list
            channel_id_list = [channel[0].id for channel in channel_id_list]

        logging.info("Announcing xur posts to {} channels".format(len(channel_id_list)))
        with operation_timer("Xur announce"):
            embed = await get_xur_text(settings.url, settings.post_url)

            await asyncio.gather(
                *[
                    _send_embed_if_textable_channel(
                        channel_id,
                        event,
                        embed,
                        XurAutopostChannel,
                    )
                    for channel_id in channel_id_list
                ]
            )


@lightbulb.add_checks(
    lightbulb.checks.dm_only
    | custom_checks.has_guild_permissions(hikari.Permissions.ADMINISTRATOR)
)
@lightbulb.command(
    "autopost", "Server autopost management, can be used by server administrators only"
)
@lightbulb.implements(lightbulb.SlashCommandGroup)
async def autopost_cmd_group(ctx: lightbulb.Context) -> None:
    await ctx.respond(
        "Server autopost management commands, please use the subcommands here to manage autoposts"
    )


def make_autoannounce_control_user_command(channel_table):
    # Uses a LostSectorAutopostChannel or XurAutopostChannel like table
    # to make a command for the user to be able to control autoposts in their
    # server
    cls_name = channel_table.__name__
    name_list = re.findall("[A-Z][^A-Z]*", cls_name)
    name = " ".join(name_list[:-2])
    cmd_name = "".join(name_list[:-2])

    # Function creation
    @autopost_cmd_group.child
    @lightbulb.option(
        "option",
        "Enabled or disabled",
        type=str,
        choices=["Enable", "Disable"],
        required=True,
    )
    @lightbulb.command(
        cmd_name.lower(),
        "Lost sector auto posts",
        auto_defer=True,
        guilds=cfg.kyber_discord_server_id,
        inherit_checks=True,
    )
    @lightbulb.implements(lightbulb.SlashSubCommand)
    async def generic_autopost_user_side_controller(ctx: lightbulb.Context) -> None:
        channel_id: int = ctx.channel_id
        server_id: int = ctx.guild_id if ctx.guild_id is not None else -1
        option: bool = True if ctx.options.option.lower() == "enable" else False
        bot = ctx.bot
        if await _bot_has_message_perms(bot, channel_id):
            async with db_session() as session:
                async with session.begin():
                    channel = await session.get(channel_table, channel_id)
                    if channel is None:
                        channel = channel_table(channel_id, server_id, option)
                        session.add(channel)
                    else:
                        channel.enabled = option
            await ctx.respond(
                name + " autoposts {}".format("enabled" if option else "disabled")
            )
        else:
            await ctx.respond(
                'The bot does not have the "Send Messages" or the'
                + ' "Send Messages in Threads" permission here'
            )

    # End of function creation
    return generic_autopost_user_side_controller


lost_sector_auto = make_autoannounce_control_user_command(LostSectorAutopostChannel)


xur_auto = make_autoannounce_control_user_command(XurAutopostChannel)


@autopost_cmd_group.set_error_handler
async def announcements_error_handler(
    event: lightbulb.MissingRequiredPermission,
) -> None:
    ctx = event.context
    await ctx.respond(
        "You cannot change this setting because you "
        + 'do not have "Administrator" permissions in this server'
    )


def _wire_listeners(bot: lightbulb.BotApp) -> None:
    """Connects all listener coroutines to the bot"""
    for handler in [lost_sector_announcer, xur_announcer]:
        bot.listen()(handler)


async def _bot_has_message_perms(
    bot: lightbulb.BotApp, channel: Union[hikari.TextableChannel, int]
) -> bool:
    if not isinstance(channel, hikari.TextableChannel):
        channel = await bot.rest.fetch_channel(channel)
    if isinstance(channel, hikari.TextableChannel):
        if isinstance(channel, hikari.TextableGuildChannel):
            guild = await channel.fetch_guild()
            self_member = await bot.rest.fetch_member(guild, bot.get_me())
            perms = lightbulb.utils.permissions_in(channel, self_member)
            # Check if we have the send messages permission in the channel
            # Refer to hikari.Permissions to see how / why this works
            # Note: Hikari doesn't recognize threads
            # Channel types 10, 11, 12 and 15 are thread types as specified in:
            # https://discord.com/developers/docs/resources/channel#channel-object-channel-types
            # If the channel is a thread, we need to check for the SEND_MESSAGES_IN_THREADS perm
            if channel.type in [10, 11, 12, 15]:
                return (
                    hikari.Permissions.SEND_MESSAGES_IN_THREADS & perms
                ) == hikari.Permissions.SEND_MESSAGES_IN_THREADS
            else:
                return (
                    hikari.Permissions.SEND_MESSAGES & perms
                ) == hikari.Permissions.SEND_MESSAGES
        else:
            return True


async def arm(bot: lightbulb.BotApp) -> None:
    # Arm all signals
    DailyResetSignal(bot).arm()
    WeeklyResetSignal(bot).arm()
    WeekendResetSignal(bot).arm()
    LostSectorSignal(bot).arm()
    XurSignal(bot).arm()
    # Connect listeners to the bot
    _wire_listeners(bot)
    # Connect commands
    bot.command(autopost_cmd_group)
    # Start the web server for periodic signals from apscheduler
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "localhost", cfg.port)
    await site.start()
