import contextlib
import datetime as dt
import logging
import re
from typing import Tuple

import aiohttp
import hikari
from pytz import utc
from sqlalchemy import update
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from . import cfg

url_regex = re.compile(
    "http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+"
)


Base = declarative_base()
db_engine = create_async_engine(cfg.db_url_async)
db_session = sessionmaker(db_engine, **cfg.db_session_kwargs)


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


async def _create_or_get(cls, id, **kwargs):
    async with db_session() as session:
        async with session.begin():
            instance = await session.get(cls, id)
            if instance is None:
                instance = cls(id, **kwargs)
                session.add(instance)
    return instance


@contextlib.contextmanager
def operation_timer(op_name):
    start_time = dt.datetime.now()
    logging.info("{name} started".format(name=op_name))
    yield
    end_time = dt.datetime.now()
    time_delta = end_time - start_time
    minutes = time_delta.seconds // 60
    seconds = time_delta.seconds % 60
    logging.info(
        "{name} finished in {mins} minutes and {secs} seconds".format(
            name=op_name, mins=minutes, secs=seconds
        )
    )


def weekend_period(today: dt.datetime = None) -> Tuple[dt.datetime, dt.datetime]:
    if today is None:
        today = dt.datetime.now()
    today = dt.datetime(today.year, today.month, today.day, tzinfo=utc)
    monday = today - dt.timedelta(days=today.weekday())
    # Weekend is friday 1700 UTC to Tuesday 1700 UTC
    friday = monday + dt.timedelta(days=4) + dt.timedelta(hours=17)
    tuesday = friday + dt.timedelta(days=4)
    return friday, tuesday


def week_period(today: dt.datetime = None) -> Tuple[dt.datetime, dt.datetime]:
    if today is None:
        today = dt.datetime.now()
    today = dt.datetime(today.year, today.month, today.day, tzinfo=utc)
    monday = today - dt.timedelta(days=today.weekday())
    start = monday + dt.timedelta(days=1) + dt.timedelta(hours=17)
    end = start + dt.timedelta(days=7)
    return start, end


def day_period(today: dt.datetime = None) -> Tuple[dt.datetime, dt.datetime]:
    if today is None:
        today = dt.datetime.now()
    today = dt.datetime(today.year, today.month, today.day, 17, tzinfo=utc)
    today_end = today + dt.timedelta(days=1)
    return today, today_end


async def follow_link_single_step(url: str) -> str:
    async with aiohttp.ClientSession() as session:
        async with session.get(url, allow_redirects=False) as resp:
            try:
                return resp.headers["Location"]
            except KeyError:
                # If we can't find the location key, warn and return the
                # provided url itself
                logging.warning(
                    "Could not find redirect for url "
                    + "{}, returning as is".format(url)
                )
                return url


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
