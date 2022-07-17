import lightbulb

from polarity.schemas import LostSectorPostSettings, XurPostSettings

from . import cfg
from .schemas import XurPostSettings, db_session


@lightbulb.add_checks(lightbulb.checks.has_roles(cfg.admin_role))
@lightbulb.command(
    "kyber",
    "Commands for Kyber",
    guilds=[
        cfg.kyber_discord_server_id,
    ],
)
@lightbulb.implements(lightbulb.SlashCommandGroup)
async def kyber():
    # Enables or disables lost sector announcements globally
    pass


@kyber.child
@lightbulb.option(
    "option",
    "Enable or disable",
    type=str,
    choices=["Enable", "Disable"],
    required=True,
)
@lightbulb.command(
    "ls_announcements",
    "Enable or disable all automatic lost sector announcements",
    auto_defer=True,
    # The following NEEDS to be included in all privledged commands
    inherit_checks=True,
)
@lightbulb.implements(lightbulb.SlashSubCommand)
async def ls_announcements(ctx: lightbulb.Context):
    option = True if ctx.options.option.lower() == "enable" else False
    async with db_session() as session:
        async with session.begin():
            settings = await session.get(LostSectorPostSettings, 0)
            if settings is None:
                settings = LostSectorPostSettings(0, option)
                session.add(settings)
            else:
                settings.autoannounce_enabled = option
    await ctx.respond(
        "Lost sector announcements {}".format("Enabled" if option else "Disabled")
    )


@kyber.child
@lightbulb.command(
    "xur_announcements",
    "Xur announcement management",
    guilds=[
        cfg.kyber_discord_server_id,
    ],
    inherit_checks=True,
)
@lightbulb.implements(lightbulb.SlashSubGroup)
async def xur_announcements():
    pass


@xur_announcements.child
@lightbulb.option(
    "option",
    "Enable or disable",
    type=str,
    choices=["Enable", "Disable"],
    required=True,
)
@lightbulb.command(
    "autoposts",
    "Enable or disable all automatic lost sector announcements",
    auto_defer=True,
    # The following NEEDS to be included in all privledged commands
    inherit_checks=True,
)
@lightbulb.implements(lightbulb.SlashSubCommand)
async def xur_autoposts(ctx: lightbulb.Context):
    option = True if ctx.options.option.lower() == "enable" else False
    async with db_session() as session:
        async with session.begin():
            settings = await session.get(XurPostSettings, 0)
            if settings is None:
                settings = XurPostSettings(0, option)
                session.add(settings)
            else:
                settings.autoannounce_enabled = option
    await ctx.respond(
        "Xur announcements {}".format("Enabled" if option else "Disabled")
    )


@xur_announcements.child
@lightbulb.option(
    "url",
    "The url to set",
    type=str,
    required=False,
)
@lightbulb.command(
    "infographic_url",
    "Set the Xur infographic url, to check and post",
    auto_defer=True,
    inherit_checks=True,
)
@lightbulb.implements(lightbulb.SlashSubCommand)
async def xur_gfx_url(ctx: lightbulb.Context):
    url = ctx.options.url.lower() if ctx.options.url is not None else None
    async with db_session() as session:
        async with session.begin():
            settings: XurPostSettings = await session.get(XurPostSettings, 0)
            if ctx.options.url is None:
                await ctx.respond(
                    (
                        "The current Xur Infographic url is <{}>\n"
                        + "The default Xur Infographic url is <{}>"
                    ).format(
                        "unset" if settings is None else settings.url,
                        cfg.defaults.xur.gfx_url,
                    )
                )
                return
            if settings is None:
                settings = XurPostSettings(0)
                settings.url = url
                await settings.initialise_url_params()
                session.add(settings)
            else:
                settings.url = url
    await ctx.respond("Xur Infographic url updated to <{}>".format(url))


@xur_announcements.child
@lightbulb.option(
    "url",
    "The url to set",
    type=str,
    required=False,
)
@lightbulb.command(
    "post_url",
    "Set the Xur infographic url, to check and post",
    auto_defer=True,
    inherit_checks=True,
)
@lightbulb.implements(lightbulb.SlashSubCommand)
async def xur_post_url(ctx: lightbulb.Context):
    url = ctx.options.url.lower() if ctx.options.url is not None else None
    async with db_session() as session:
        async with session.begin():
            settings: XurPostSettings = await session.get(XurPostSettings, 0)
            if ctx.options.url is None:
                await ctx.respond(
                    (
                        "The current Xur Post url is <{}>\n"
                        + "The default Xur Post url is <{}>"
                    ).format(
                        "unset" if settings is None else settings.post_url,
                        cfg.defaults.xur.post_url,
                    )
                )
                return
            if settings is None:
                settings = XurPostSettings(0)
                settings.post_url = url
                session.add(settings)
            else:
                settings.post_url = url
    await ctx.respond("Xur Post url updated to <{}>".format(url))


def register_all(bot: lightbulb.BotApp) -> None:
    bot.command(kyber)
