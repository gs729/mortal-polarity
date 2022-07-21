import asyncio
import datetime as dt
import re
from typing import Union

import aiohttp
import hikari
import lightbulb
from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String
from sqlalchemy.orm import declarative_mixin, declared_attr
from sqlalchemy.sql.schema import Column

from . import cfg
from .utils import Base, db_engine, db_session


@declarative_mixin
class BasePostSettings:
    @declared_attr
    def __tablename__(cls):
        return cls.__name__.lower()

    __mapper_args__ = {"eager_defaults": True}

    id = Column("id", Integer, primary_key=True)
    autoannounce_enabled = Column(
        "autoannounce_enabled", Boolean, default=True, server_default="t"
    )

    def __init__(self, id, autoannounce_enabled=True):
        self.id = id
        self.autoannounce_enabled = autoannounce_enabled


class LostSectorPostSettings(BasePostSettings, Base):
    pass


class XurPostSettings(BasePostSettings, Base):
    # url: the infographic url
    url = Column("url", String, nullable=False, default=cfg.defaults.xur.gfx_url)
    # post_url: hyperlink for the post title
    post_url = Column("post_url", String, default=cfg.defaults.xur.post_url)
    url_redirect_target = Column("url_redirect_target", String)
    url_last_modified = Column("url_last_modified", DateTime)
    url_last_checked = Column("url_last_checked", DateTime)
    # ToDo: Look for all armed url watchers at startup and start them again
    url_watcher_armed = Column(
        "url_watcher_armed", Boolean, default=False, server_default="f"
    )

    def __init__(
        self,
        id: int,
        url: str = cfg.defaults.xur.gfx_url,
        post_url: str = cfg.defaults.xur.post_url,
        autoannounce_enabled: bool = True,
    ):
        self.id = id
        self.url = url
        self.post_url = post_url
        self.autoannounce_enabled = autoannounce_enabled

    async def initialise_url_params(self):
        """
        Initialise the Url's redirect_target, last_modified and last_checked properties
        if they are set to None
        """
        if not (
            self.url_redirect_target == None
            or self.url_last_checked == None
            or self.url_last_modified == None
        ):
            return
        async with aiohttp.ClientSession() as session:
            async with session.get(self.url, allow_redirects=False) as resp:
                self.url_redirect_target = resp.headers["Location"]
                self.url_last_checked = dt.datetime.now()
                self.url_last_modified = dt.datetime.now()

    async def wait_for_url_update(self):
        async with db_session() as db_session_:
            async with db_session_.begin():
                self.url_watcher_armed = True
            check_interval = 10
            async with aiohttp.ClientSession() as session:
                while True:
                    async with session.get(self.url, allow_redirects=False) as resp:
                        if resp.headers["Location"] != self.url_redirect_target:
                            async with db_session_.begin():
                                self.url_redirect_target = resp.headers["Location"]
                                self.url_last_modified = dt.datetime.now()
                                self.url_watcher_armed = False
                            return self
                        await asyncio.sleep(check_interval)


@declarative_mixin
class BaseChannelRecord:
    @declared_attr
    def __tablename__(cls):
        return cls.__name__.lower()

    __mapper_args__ = {"eager_defaults": True}

    id = Column("id", BigInteger, primary_key=True)
    # Note: if server_id is -1 then this is a dm channel
    server_id = Column("server_id", BigInteger)
    last_msg_id = Column("last_msg_id", BigInteger)
    enabled = Column("enabled", Boolean)

    def __init__(self, id: int, server_id: int, enabled: bool):
        self.id = id
        self.server_id = server_id
        self.enabled = enabled

    @classmethod
    def make_autopost_ctrl_usr_cmd(cls, cmd_group: lightbulb.SlashCommandGroup):
        # Uses a LostSectorAutopostChannel or XurAutopostChannel like table
        # to make a command for the user to be able to control autoposts in their
        # server
        cls_name = cls.__name__
        name_list = re.findall("[A-Z][^A-Z]*", cls_name)
        name = " ".join(name_list[:-2])
        cmd_name = "".join(name_list[:-2])

        # Function creation
        @cmd_group.child
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
            if await cls._check_bot_has_message_perms(bot, channel_id):
                async with db_session() as session:
                    async with session.begin():
                        channel = await session.get(cls, channel_id)
                        if channel is None:
                            channel = cls(channel_id, server_id, option)
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

    @staticmethod
    async def _check_bot_has_message_perms(
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


class LostSectorAutopostChannel(BaseChannelRecord, Base):
    pass


class XurAutopostChannel(BaseChannelRecord, Base):
    pass


class Commands(Base):
    __tablename__ = "commands"
    __mapper_args__ = {"eager_defaults": True}
    name = Column("name", String, primary_key=True)
    description = Column("description", String)
    response = Column("response", String)

    def __init__(self, name, description, response):
        super().__init__()
        self.name = name
        self.description = description
        self.response = response
