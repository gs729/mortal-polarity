import asyncio
import hikari
import lightbulb
import uvloop

from . import cfg, user_commands, debug_commands
from .utils import Base
from .autoannounce import arm

uvloop.install()
bot: lightbulb.BotApp = lightbulb.BotApp(**cfg.lightbulb_params)


@bot.listen(hikari.StartedEvent)
async def on_ready(event: hikari.StartedEvent) -> None:
    await arm(bot)


if __name__ == "__main__":
    user_commands.register_all(bot)
    if cfg.test_env:
        debug_commands.register_all(bot)
    bot.run()
