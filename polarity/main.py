import logging
import re

import aiohttp
import hikari
import lightbulb
import uvloop
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql.expression import delete, select

from . import cfg
from .schemas import Commands

url_regex = re.compile(
    "http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+"
)


db_engine = create_async_engine(cfg.db_url_async)
db_session = sessionmaker(db_engine, **cfg.db_session_kwargs)

uvloop.install()

if cfg.test_env:
    # Only use the test env for testing if it is specified
    bot = lightbulb.BotApp(token=cfg.main_token, default_enabled_guilds=cfg.test_env)
else:
    # Test env isn't specified in production
    bot = lightbulb.BotApp(token=cfg.main_token)

controller = lightbulb.Plugin(
    "controller", default_enabled_guilds=cfg.kyber_discord_server_id
)
controller.add_checks(lightbulb.checks.has_roles(cfg.admin_role))
command_registry = {}


@controller.command
@lightbulb.option("link", "Link to post when this command is used", type=str)
@lightbulb.option(
    "description", "Description of what the command posts or does", type=str
)
@lightbulb.option("name", "Name of the command to add", type=str)
@lightbulb.command("add", "Add a link to the bot", auto_defer=True)
@lightbulb.implements(lightbulb.SlashCommand)
async def add_command(ctx: lightbulb.Context) -> None:
    name = ctx.options.name.lower()
    description = ctx.options.description
    text = ctx.options.link

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

            command_registry[command.name] = lightbulb.command(
                command.name, command.description, auto_defer=True
            )(lightbulb.implements(lightbulb.SlashCommand)(user_command))
            bot.command(command_registry[command.name])
            logging.info(command.name + " command registered")
            bot.event_manager.dispatch(RefreshCmdList())

    await ctx.respond("Command added")


class RefreshCmdList(hikari.Event):
    def __init__(self, sync: bool = True):
        super().__init__()
        # Whether to run the sync_application_commands method of the app
        self.sync = sync

    def app(self):
        return bot


@controller.command
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
    bot.event_manager.dispatch(RefreshCmdList())


@bot.listen(RefreshCmdList)
async def del_command_updater(event: RefreshCmdList):
    del_command.options.get("name").choices = [cmd for cmd in command_registry.keys()]
    if event.sync:
        await bot.sync_application_commands()


async def user_command(ctx: lightbulb.Context):
    async with db_session() as session:
        async with session.begin():
            command = (
                await session.execute(
                    select(Commands).where(Commands.name == ctx.command.name)
                )
            ).fetchone()[0]
    text = command.text.strip()
    # Follow the redirects, check the extension, download only if it is a jgp
    # Above to be implemented
    links = url_regex.findall(text)
    redirected_links = []
    redirected_text = url_regex.sub("{}", text)
    async with aiohttp.ClientSession() as session:
        for link in links:
            async with session.get(link) as response:
                redirected_links.append(response.url)
                logging.info(
                    "Replacing link: {} with redirect: {}".format(
                        link, redirected_links[-1]
                    )
                )
    redirected_text = redirected_text.format(*redirected_links)

    await ctx.respond(redirected_text)


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

                command_registry[command.name] = lightbulb.command(
                    command.name, command.description, auto_defer=True
                )(lightbulb.implements(lightbulb.SlashCommand)(user_command))

                bot.command(command_registry[command.name])
                logging.info(command.name + " registered")

    # Trigger a refresh of the options in the delete command
    # Don't sync since the bot has not started yet and
    # Will sync on its own for startup
    bot.event_manager.dispatch(RefreshCmdList(sync=False))


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


bot.add_plugin(controller)
bot.run()
