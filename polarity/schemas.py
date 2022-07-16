import asyncio
import datetime as dt

import aiohttp
from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String
from sqlalchemy.sql.schema import Column

from .utils import Base, db_engine, db_session


class LostSectorPostSettings(Base):
    __tablename__ = "lostsectorpostsettings"
    __mapper_args__ = {"eager_defaults": True}
    id = Column("id", Integer, primary_key=True)
    autoannounce_enabled = Column(
        "autoannounce_enabled", Boolean, default=True, server_default="t"
    )

    def __init__(self, id, autoannounce_enabled=True):
        self.id = id
        self.autoannounce_enabled = autoannounce_enabled


class XurPostSettings(Base):
    __tablename__ = "xurpostsettings"
    __mapper_args__ = {"eager_defaults": True}
    id = Column("id", Integer, primary_key=True)
    url = Column("url", String, nullable=False, default="https://kyber3000.com/Xur")
    url_redirect_target = Column("redirect_target", String)
    url_last_modified = Column("last_modified", DateTime)
    url_last_checked = Column("last_checked", DateTime)
    autoannounce_enabled = Column(
        "autoannounce_enabled", Boolean, default=True, server_default="t"
    )
    # ToDo: Look for all armed url watchers at startup and start them again
    url_watcher_armed = Column(
        "watcher_armed", Boolean, default=False, server_default="f"
    )

    def __init__(
        self,
        id: int,
        url: str,
        autoannounce_enabled: bool = True,
    ):
        self.id = id
        self.url = url
        self.autoannounce_enabled = autoannounce_enabled

    async def initialise_url_params(self):
        """
        Initialise the Url's redirect_target, last_modified and last_checked properties
        if they are set to None
        """
        if not (
            self.url_redirect_target == None
            or self.url_last_checked == None
            or self.url_last_modified == None
        ):
            return
        async with aiohttp.ClientSession() as session:
            async with session.get(self.url, allow_redirects=False) as resp:
                self.url_redirect_target = resp.headers["Location"]
                self.url_last_checked = dt.datetime.now()
                self.url_last_modified = dt.datetime.now()

    async def wait_for_url_update(self, db_session):
        async with db_session.begin():
            self.url_watcher_armed = True
        check_interval = 10
        async with aiohttp.ClientSession() as session:
            while True:
                async with session.get(self.url, allow_redirects=False) as resp:
                    if resp.headers["Location"] != self.url_redirect_target:
                        async with db_session.begin():
                            self.url_redirect_target = resp.headers["Location"]
                            self.url_last_modified = dt.datetime.now()
                            self.url_watcher_armed = False
                        return self
                    await asyncio.sleep(check_interval)


class LostSectorAutopostChannel(Base):
    __tablename__ = "lostsectorautopostchannel"
    __mapper_args__ = {"eager_defaults": True}
    id = Column("id", BigInteger, primary_key=True)
    # Note: if server_id is -1 then this is a dm channel
    server_id = Column("server_id", BigInteger)
    enabled = Column("enabled", Boolean)

    def __init__(self, id: int, server_id: int, enabled: bool):
        self.id = id
        self.server_id = server_id
        self.enabled = enabled


class Commands(Base):
    __tablename__ = "commands"
    __mapper_args__ = {"eager_defaults": True}
    name = Column("name", String, primary_key=True)
    description = Column("description", String)
    response = Column("response", String)

    def __init__(self, name, description, response):
        super().__init__()
        self.name = name
        self.description = description
        self.response = response
