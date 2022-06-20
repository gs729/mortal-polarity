import logging

import hikari
import lightbulb
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql.expression import delete, select

from . import cfg
from .schemas import Commands

db_engine = create_async_engine(cfg.db_url_async)
db_session = sessionmaker(db_engine, **cfg.db_session_kwargs)

COMMAND_GUILD_ID = cfg.test_env if cfg.test_env else hikari.UNDEFINED
bot = lightbulb.BotApp(token=cfg.main_token, default_enabled_guilds=COMMAND_GUILD_ID)
command_registry = {}


@bot.command
@lightbulb.option("link", "Link to post when this command is used", type=str)
@lightbulb.option(
    "description", "Description of what the command posts or does", type=str
)
@lightbulb.option("name", "Name of the command to add", type=str)
@lightbulb.command(
    "add", "Add a link to the bot, only usable by Kyber et al", auto_defer=True
)
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
            print(name, description, text)
            session.add(command)

            command_registry[command.name] = lightbulb.command(
                command.name, command.description, auto_defer=True
            )(lightbulb.implements(lightbulb.SlashCommand)(user_command))
            bot.command(command_registry[command.name])
            logging.info(command.name + " command registered")
            await bot.sync_application_commands()

    await ctx.respond("Command added")


@bot.command
@lightbulb.option("name", "Name of the command to delete", type=str)
@lightbulb.command(
    "delete",
    "Delete a command from the bot, only usable by Kyber et al",
    auto_defer=True,
)
@lightbulb.implements(lightbulb.SlashCommand)
async def del_command(ctx: lightbulb.Context) -> None:
    name = ctx.options.name.lower()

    async with db_session() as session:
        try:
            command_registry.pop(name)
        except KeyError:
            await ctx.respond("No such command found")
            return
        async with session.begin():
            await session.execute(delete(Commands).where(Commands.name == name))

    bot.remove_command(command_registry[name])
    await bot.sync_application_commands()
    await ctx.respond("`{}`command deleted".format(name))


async def user_command(ctx: lightbulb.Context):
    async with db_session() as session:
        async with session.begin():
            command = (
                await session.execute(
                    select(Commands.text).where(Commands.name == ctx.command.name)
                )
            ).fetchone()[0]
    await ctx.respond(command)


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


bot.run()
