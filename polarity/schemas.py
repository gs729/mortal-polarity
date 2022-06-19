from sqlalchemy.orm import declarative_base
from sqlalchemy.sql.schema import Column
from sqlalchemy.sql.sqltypes import String

Base = declarative_base()


class Commands(Base):
    __tablename__ = "commands"
    __mapper_args__ = {"eager_defaults": True}
    name = Column("name", String, primary_key=True)
    description = Column("description", String)
    text = Column("text", String)

    def __init__(self, name, description, text):
        super().__init__()
        self.name = name
        self.description = description
        self.text = text
