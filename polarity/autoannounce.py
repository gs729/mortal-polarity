import logging

import hikari
import lightbulb
from aiohttp import web

from . import cfg


app = web.Application()

# Event that dispatches itself when a destiny 2 daily reset occurs.
# When a destiny 2 reset occurs, the reset_signaller.py process
# will send a signal to this process, which will be passed on
# as a hikari.Event that is dispatched bot-wide
class ResetSignal(hikari.Event):
    qualifier: str

    def __init__(self, bot) -> None:
        super().__init__()
        self.bot: lightbulb.BotApp = bot

    @property
    def app(self) -> lightbulb.BotApp:
        return self.bot

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


async def arm(bot) -> None:
    DailyResetSignal(bot).arm()
    WeeklyResetSignal(bot).arm()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "localhost", cfg.port)
    await site.start()
