# RUN WITH CAUTION
# DELETES ALL PUBLISHED COMMANDS FOR cfg.main_token GLOBALLY
import asyncio
import hikari

from . import cfg

rest = hikari.RESTApp()

TOKEN = cfg.main_token


async def main():
    async with rest.acquire(cfg.main_token, hikari.TokenType.BOT) as client:
        application = await client.fetch_application()

        await client.set_application_commands(
            application.id, (), guild=hikari.UNDEFINED
        )


asyncio.run(main())
