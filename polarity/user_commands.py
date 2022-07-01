# End user facing command implementations for the bot

import datetime as dt
import logging
from calendar import month_name as month

import aiohttp
import hikari
import lightbulb
from pytz import utc
from sector_accounting import Rotation
from tortoise.models import Model
from tortoise import fields, Tortoise

from . import cfg
from .utils import (
    init_db_session,
    RefreshCmdListEvent,
    url_regex,
)

command_registry = {}


class Commands(Model):
    name = fields.CharField(pk=True, max_length=255)
    description = fields.CharField(max_length=255)
    response = fields.CharField(max_length=4096)


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
    response = ctx.options.response
    bot = ctx.bot

    additional_commands = await commands.all()
    additional_commands = [command.name for command in additional_commands]
    # ToDo: Update hardcoded command names
    if name in ["add", "edit", "delete"] + additional_commands:
        await ctx.respond("A command with that name already exists")
        return

    command = await commands.create(
        name=name,
        description=description,
        response=response,
    )

    command_registry[command.name] = db_command_to_lb_user_command(command)
    bot.command(command_registry[command.name])
    logging.info(command.name + " command registered")
    RefreshCmdListEvent(bot).dispatch()

    await ctx.respond("Command added")


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
    bot = ctx.bot
    name = ctx.options.name.lower()

    try:
        command_to_delete = command_registry.pop(name)
    except KeyError:
        await ctx.respond("No such command found")
    else:
        await commands.filter(name=name).delete()
        bot.remove_command(command_to_delete)
        await ctx.respond("{} command deleted".format(name))
    # Trigger a refresh of the choices in the delete command
    RefreshCmdListEvent(bot).dispatch()


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
    bot = ctx.bot
    command: commands = await commands.filter(name=ctx.options.name.lower()).first()

    if (
        ctx.options.new_name in [None, ""]
        and ctx.options.new_response in [None, ""]
        and ctx.options.new_description in [None, ""]
    ):
        await ctx.respond(
            "The name for this command is currently: {}\n".format(command.name)
            + "The description for this command is currently: {}\n".format(
                command.description
            )
            + "The response for this command is currently: {}".format(command.response)
        )
    else:
        if ctx.options.new_name not in [None, ""]:
            old_name = command.name
            new_name = ctx.options.new_name.lower()
            command.name = new_name
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
            command.response = ctx.options.new_response
        if ctx.options.new_description not in [None, ""]:
            command.description = ctx.options.new_description
            # Lightbulb doesn't like changing this:
            # bot.get_slash_command(
            #     ctx.options.name
            # ).description = command.description
            # Need to delete and readd the command instead
            bot.remove_command(command_registry.pop(command.name))
            command_registry[command.name] = db_command_to_lb_user_command(command)
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


async def command_options_updater(event: RefreshCmdListEvent):
    choices = [cmd for cmd in command_registry.keys()]
    del_command.options.get("name").choices = choices
    edit_command.options.get("name").choices = choices
    if event.sync:
        await event.app.sync_application_commands()


async def register_commands_on_startup(event: hikari.StartingEvent):
    """Register additional text commands from db."""
    await init_db_session()
    logging.info("Registering commands")

    command_list = await commands.all()
    command_list = [] if command_list.count(command_list) == 0 else command_list
    logging.warning("Len:" + str(len(command_list)))
    logging.warning("Count:" + str(command_list.count(command_list)))
    for command in command_list:
        command_registry[command.name] = db_command_to_lb_user_command(command)
        event.app.command(command_registry[command.name])
        logging.info(command.name + " registered")

    # Trigger a refresh of the options in the delete command
    # Don't sync since the bot has not started yet and
    # Will sync on its own for startup
    RefreshCmdListEvent(event.app, sync=False).dispatch()


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


def register_all(bot: lightbulb.BotApp):
    # Register all commands and listeners with the bot
    for command in [add_command, del_command, edit_command, ls_command]:
        bot.command(command)

    for event, handler in [
        (RefreshCmdListEvent, command_options_updater),
        (hikari.StartingEvent, register_commands_on_startup),
        (lightbulb.CommandErrorEvent, on_error),
    ]:
        bot.listen(event)(handler)


async def user_command(ctx: lightbulb.Context):
    command = await (await commands.filter(name=ctx.command.name)).first()
    text = command.response.strip()
    # Follow the redirects, check the extension, download only if it is a jgp
    # Above to be implemented
    links = url_regex.findall(text)
    redirected_links = []
    redirected_text = url_regex.sub("{}", text)
    async with aiohttp.ClientSession() as session:
        for link in links:
            async with session.get(link) as response:
                redirected_links.append(str(response.url))
                logging.debug(
                    "Replacing link: {} with redirect: {}".format(
                        link, redirected_links[-1]
                    )
                )
    redirected_text = redirected_text.format(*redirected_links)

    await ctx.respond(redirected_text)


def db_command_to_lb_user_command(command: commands):
    # Needs an open db session watching command
    return lightbulb.command(command.name, command.description, auto_defer=True)(
        lightbulb.implements(lightbulb.SlashCommand)(user_command)
    )
