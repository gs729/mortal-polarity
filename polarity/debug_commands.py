import lightbulb

from . import autoannounce, cfg


@lightbulb.command(
    name="trigger_daily_reset",
    description="Sends a daily reset signal",
    guilds=(cfg.test_env,),
)
@lightbulb.implements(lightbulb.SlashCommand)
async def daily_reset(ctx: lightbulb.Context) -> None:
    ctx.bot.dispatch(autoannounce.DailyResetSignal(ctx.bot))
    await ctx.respond("Daily reset signal sent")


def register_all(bot: lightbulb.BotApp) -> None:
    bot.command(daily_reset)
