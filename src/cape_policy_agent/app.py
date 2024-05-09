import os

import sqlmodel
from dotenv import load_dotenv
from fastapi import FastAPI
from sqlalchemy import URL

# Note: need to import models so DB is initialized correctly
import cape_policy_agent.model  # type: ignore  # noqa: F401

load_dotenv()


def _get_url() -> URL:
    drivername = os.getenv("DB_DRIVER", "sqlite")

    if drivername == "sqlite":
        database = os.getenv("DB_DATABASE", "database.db")
        return URL.create(drivername=drivername, database=database)

    else:
        # Figure out the port number
        if drivername.startswith("postgres"):
            port = int(os.getenv("DB_PORT", 5432))
        elif drivername.startswith("mysql"):
            port = int(os.getenv("DB_PORT", 3306))
        else:
            port_str = os.getenv("DB_PORT")
            if port_str is None:
                raise RuntimeError("DB_PORT environment variable is not set")
            port = int(port_str)

        username = os.getenv("DB_USER", "")
        password = os.getenv("DB_PASSWORD", "")
        host = os.getenv("DB_HOST", "localhost")
        database = os.getenv("DB_DATABASE", "cape-policy-agent")

        return URL.create(
            drivername=drivername,
            username=username,
            password=password,
            host=host,
            port=port,
            database=database,
        )


# Database connection
url = _get_url()
engine = sqlmodel.create_engine(url)
sqlmodel.SQLModel.metadata.create_all(engine)

# API server
host = os.getenv("HOST", "localhost")
port = int(os.getenv("PORT", 8000))


description = """

"""


app = FastAPI(
    title="cape-policy-agent",
    description=description,
    version="0.1.0",
)
