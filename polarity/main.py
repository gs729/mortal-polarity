import hikari
import lightbulb
import uvloop

from . import cfg, controller, debug_commands, user_commands
from .autoannounce import arm
from .utils import Base

uvloop.install()
bot: lightbulb.BotApp = lightbulb.BotApp(**cfg.lightbulb_params)


@bot.listen(hikari.StartedEvent)
async def on_ready(event: hikari.StartedEvent) -> None:
    await arm(bot)


if __name__ == "__main__":
    user_commands.register_all(bot)
    controller.register_all(bot)
    if cfg.test_env:
        debug_commands.register_all(bot)
    bot.run()
