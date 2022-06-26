# This architecture for a periodic signal is used since
# apscheduler 3.x has quirks that make it difficult to
# work with in a single process with async without global state.
# These problems are expected to be solved by the release
# of apscheduler 4.x which will have a better async support
# This architecture uses aiohttps requests to a quart (async flask)
# server to send a signal from the scheduler to the reciever.
# The relevant tracking issue for apscheduler 4.x is:
# https://github.com/agronholm/apscheduler/issues/465

import aiohttp
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from pytz import utc

from . import cfg

# We use the AsyncIOScheduler since the discord client library
# runs mostly asynchronously
# This will be useful when this is run in a single process
# when apscheduler 4.x is released
_scheduler = AsyncIOScheduler(
    jobstores={"default": SQLAlchemyJobStore(url=cfg.db_url)},
    job_defaults={
        "coalesce": "true",
        "misfire_grace_time": 1800,
        "max_instances": 1,
    },
)


async def remote_daily_reset():
    print("Sending daily reset signal")
    async with aiohttp.ClientSession() as session:
        await session.post(
            "http://127.0.0.1:{}/daily-reset-signal".format(cfg.port), verify_ssl=False
        )


async def remote_weekly_reset():
    print("Sending daily reset signal")
    async with aiohttp.ClientSession() as session:
        await session.post(
            "http://127.0.0.1:{}/weekly-reset-signal".format(cfg.port), verify_ssl=False
        )


# This needs to be called at release
def add_remote_announce():
    # (Re)Add the scheduled job that signals destiny 2 reset
    _scheduler.add_job(
        remote_daily_reset,
        CronTrigger(
            hour=17,
            timezone=utc,
        ),
        replace_existing=True,
        id="0",
    )
    _scheduler.add_job(
        remote_weekly_reset,
        CronTrigger(
            day_of_week="tue",
            hour=17,
            timezone=utc,
        ),
        replace_existing=True,
        id="1",
    )

    # Start up then shut down the scheduler to commit changes to the DB
    _scheduler.start(paused=True)
    _scheduler.shutdown(wait=True)


def start():
    _scheduler.start()
