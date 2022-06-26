import lightbulb
import uvloop

from . import cfg, user_commands

uvloop.install()
bot: lightbulb.BotApp = lightbulb.BotApp(**cfg.lightbulb_params)


user_commands.register_all(bot)
bot.run()
