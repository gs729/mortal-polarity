import datetime as dt
import logging
from calendar import month_name as month

import aiohttp
import hikari
import lightbulb
import uvloop
from pytz import utc
from sector_accounting import Rotation
from sqlalchemy.sql.expression import delete, select

from . import cfg
from .schemas import Commands
from .utils import RefreshCmdListEvent, db_command_to_lb_user_command, db_session

uvloop.install()
command_registry = {}
bot: lightbulb.BotApp = lightbulb.BotApp(**cfg.lightbulb_params)


@bot.command
@lightbulb.add_checks(lightbulb.checks.has_roles(cfg.admin_role))
@lightbulb.option("response", "Response to post when this command is used", type=str)
@lightbulb.option(
    "description", "Description of what the command posts or does", type=str
)
@lightbulb.option("name", "Name of the command to add", type=str)
@lightbulb.command(
    "add",
    "Add a command to the bot",
    auto_defer=True,
    guilds=(cfg.kyber_discord_server_id,),
)
@lightbulb.implements(lightbulb.SlashCommand)
async def add_command(ctx: lightbulb.Context) -> None:
    name = ctx.options.name.lower()
    description = ctx.options.description
    text = ctx.options.response

    async with db_session() as session:
        async with session.begin():
            additional_commands = (await session.execute(select(Commands))).fetchall()
            additional_commands = (
                [] if additional_commands is None else additional_commands
            )
            additional_commands = [command[0].name for command in additional_commands]
            # ToDo: Update hardcoded command names
            if name in ["add", "edit", "delete"] + additional_commands:
                await ctx.respond("A command with that name already exists")
                return

            command = Commands(
                name,
                description,
                text,
            )
            session.add(command)

            command_registry[command.name] = db_command_to_lb_user_command(command)
            bot.command(command_registry[command.name])
            logging.info(command.name + " command registered")
            RefreshCmdListEvent(bot).dispatch()

    await ctx.respond("Command added")


@bot.command
@lightbulb.add_checks(lightbulb.checks.has_roles(cfg.admin_role))
@lightbulb.option(
    "name",
    "Name of the command to delete",
    type=str,
    # Note: This does not work at the start since command_registry
    # isn't populated until the bot starts
    # This is left in in case we modify command_registry in the future
    choices=[cmd for cmd in command_registry.keys()],
)
@lightbulb.command(
    "delete",
    "Delete a command from the bot",
    auto_defer=True,
    guilds=(cfg.kyber_discord_server_id,),
)
@lightbulb.implements(lightbulb.SlashCommand)
async def del_command(ctx: lightbulb.Context) -> None:
    name = ctx.options.name.lower()

    async with db_session() as session:
        try:
            command_to_delete = command_registry.pop(name)
        except KeyError:
            await ctx.respond("No such command found")
        else:
            async with session.begin():
                await session.execute(delete(Commands).where(Commands.name == name))
                bot.remove_command(command_to_delete)
                await ctx.respond("{} command deleted".format(name))
    # Trigger a refresh of the choices in the delete command
    RefreshCmdListEvent(bot).dispatch()


@bot.command
@lightbulb.add_checks(lightbulb.checks.has_roles(cfg.admin_role))
@lightbulb.option(
    "new_description",
    "Description of the command to edit",
    type=str,
    default="",
)
@lightbulb.option(
    "new_response",
    "Replace the response field in the command with this",
    type=str,
    default="",
)
@lightbulb.option(
    "new_name",
    "Replace the name of the command with this",
    type=str,
    default="",
)
@lightbulb.option(
    "name",
    "Name of the command to edit",
    type=str,
    # Note: This does not work at the start since command_registry
    # isn't populated until the bot starts
    # This is left in in case we modify command_registry in the future
    choices=[cmd for cmd in command_registry.keys()],
)
@lightbulb.command(
    "edit",
    "Edit a command",
    auto_defer=True,
    guilds=(cfg.kyber_discord_server_id,),
)
@lightbulb.implements(lightbulb.SlashCommand)
async def edit_command(ctx: lightbulb.Context):
    async with db_session() as session:
        async with session.begin():
            command: Commands = (
                await session.execute(
                    select(Commands).where(Commands.name == ctx.options.name.lower())
                )
            ).fetchone()[0]

        if (
            ctx.options.new_name is None
            and ctx.options.new_response is None
            and ctx.options.new_description is None
        ):
            await ctx.respond(
                "The name for this command is currently: {}\n".format(command.name)
                + "The description for this command is currently: {}\n".format(
                    command.description
                )
                + "The response for this command is currently: {}".format(
                    command.response
                )
            )
        else:
            if ctx.options.new_name not in [None, ""]:
                async with session.begin():
                    old_name = command.name
                    new_name = ctx.options.new_name.lower()
                    command.name = new_name
                    session.add(command)
                    # Lightbulb doesn't like changing this:
                    # bot.get_slash_command(ctx.options.name).name = command.name
                    # Need to delete and readd the command instead
                    # -x-x-x-x-
                    # Remove and unregister the old command
                    bot.remove_command(command_registry.pop(old_name))
                    # Register new command with bot and registry dict
                    command_registry[new_name] = db_command_to_lb_user_command(command)
                    bot.command(command_registry[new_name])
            if ctx.options.new_response not in [None, ""]:
                async with session.begin():
                    command.response = ctx.options.new_response
                    session.add(command)
            if ctx.options.new_description not in [None, ""]:
                async with session.begin():
                    command.description = ctx.options.new_description
                    session.add(command)
                    # Lightbulb doesn't like changing this:
                    # bot.get_slash_command(
                    #     ctx.options.name
                    # ).description = command.description
                    # Need to delete and readd the command instead
                    bot.remove_command(command_registry.pop(command.name))
                    command_registry[command.name] = db_command_to_lb_user_command(
                        command
                    )
                    bot.command(command_registry[command.name])

            if ctx.options.new_description not in [
                None,
                "",
            ] or ctx.options.new_name not in [
                None,
                "",
            ]:
                # If either the description or name of a command is changed
                # we will need to have discord update its commands server side
                RefreshCmdListEvent(bot).dispatch()

            await ctx.respond("Command updated")


@bot.command
@lightbulb.command("lstoday", "Find out about today's lost sector", auto_defer=True)
@lightbulb.implements(lightbulb.SlashCommand)
async def ls_command(ctx: lightbulb.Context):
    buffer = 1  # Minute
    discord_ls_post_string = (
        "**Daily Lost Sector for {month} {day}**\n"
        + "\n"
        + "<:LS:849727805994565662> **{sector.name}**:\n"
        + "• Exotic Reward (If Solo): {sector.reward}\n"
        + "• Champs: {sector.champions}\n"
        + "• Shields: {sector.shields}\n"
        + "• Burn: {sector.burn}\n"
        + "• Modifiers: {sector.modifiers}\n"
        + "\n"
        + "**More Info:** <https://kyber3000.com/LS>"
        + "[ ]({ls_url})"
    )

    date = dt.datetime.now(tz=utc) - dt.timedelta(hours=16, minutes=60 - buffer)
    rot = Rotation.from_gspread_url(
        cfg.sheets_ls_url, cfg.gsheets_credentials, buffer=buffer
    )()

    # Follow the hyperlink to have the newest image embedded
    async with aiohttp.ClientSession() as session:
        async with session.get(rot.shortlink_gfx) as response:
            ls_gfx_url = str(response.url)

    await ctx.respond(
        discord_ls_post_string.format(
            month=month[date.month], day=date.day, sector=rot, ls_url=ls_gfx_url
        )
    )


@bot.listen(RefreshCmdListEvent)
async def command_options_updater(event: RefreshCmdListEvent):
    choices = [cmd for cmd in command_registry.keys()]
    del_command.options.get("name").choices = choices
    edit_command.options.get("name").choices = choices
    if event.sync:
        await bot.sync_application_commands()


@bot.listen(hikari.StartingEvent)
async def register_commands_on_startup(event: hikari.StartingEvent):
    """Register additional text commands from db."""
    logging.info("Registering commands")
    async with db_session() as session:
        async with session.begin():
            command_list = (await session.execute(select(Commands))).fetchall()
            command_list = [] if command_list is None else command_list
            command_list = [command[0] for command in command_list]
            for command in command_list:
                command_registry[command.name] = db_command_to_lb_user_command(command)
                bot.command(command_registry[command.name])
                logging.info(command.name + " registered")

    # Trigger a refresh of the options in the delete command
    # Don't sync since the bot has not started yet and
    # Will sync on its own for startup
    RefreshCmdListEvent(bot, sync=False).dispatch()


@bot.listen(lightbulb.CommandErrorEvent)
async def on_error(event: lightbulb.CommandErrorEvent):
    if isinstance(event.exception, lightbulb.errors.MissingRequiredRole):
        await event.context.respond("Permission denied")
        logging.warning(
            "Note: privlidged command access attempt by uid: {}, name: {}#{}".format(
                event.context.user.id,
                event.context.user.username,
                event.context.user.discriminator,
            )
        )
    else:
        raise event.exception.__cause__ or event.exception


bot.run()
