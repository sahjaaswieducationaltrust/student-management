"""Verify the MongoDB connection before starting the API.

    python -m app.check_db

Prints a clear diagnosis instead of a stack trace, which makes MongoDB Atlas
setup problems (wrong password, IP not allow-listed, typo in the URI) obvious.
"""

import asyncio
import re
import sys

from pymongo import AsyncMongoClient
from pymongo.errors import (
    ConfigurationError,
    OperationFailure,
    ServerSelectionTimeoutError,
)

from .config import settings


def _redact(uri: str) -> str:
    return re.sub(r"://([^:/@]+):([^@]+)@", r"://\1:****@", uri)


HINTS = {
    "auth": [
        "The username or password in MONGODB_URI is wrong.",
        "On Atlas: Database Access -> edit the user -> set a new password.",
        "If the password contains @ : / ? # [ ] or %, URL-encode it",
        "  (e.g. p@ss becomes p%40ss).",
    ],
    "network": [
        "Could not reach the server. Common causes:",
        "  - Atlas: your current IP is not in Network Access -> IP Access List.",
        "  - Atlas: the cluster is paused (free clusters pause after inactivity).",
        "  - Local: MongoDB is not running. Install it with:",
        "      winget install MongoDB.Server",
        "  - A typo in the host part of MONGODB_URI.",
    ],
    "config": [
        "The connection string itself is malformed.",
        "Atlas format:",
        "  mongodb+srv://USER:PASSWORD@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority",
        "Local format:",
        "  mongodb://localhost:27017",
    ],
}


def _fail(kind: str, error: Exception) -> None:
    print(f"\n  FAILED: {type(error).__name__}")
    print(f"  {str(error).splitlines()[0][:200]}\n")
    for line in HINTS[kind]:
        print(f"  {line}")
    print()


async def main() -> int:
    print(f"\nConnecting to : {_redact(settings.mongodb_uri)}")
    print(f"Database      : {settings.mongodb_db}")

    client = AsyncMongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=8000)
    try:
        info = await client.admin.command("ping")
        if not info.get("ok"):
            print("\n  FAILED: server did not acknowledge the ping.\n")
            return 1

        db = client[settings.mongodb_db]
        collections = await db.list_collection_names()
        users = await db.users.count_documents({}) if "users" in collections else 0
        students = await db.students.count_documents({}) if "students" in collections else 0

        print("\n  CONNECTED\n")
        print(f"  Collections : {', '.join(sorted(collections)) or '(empty database)'}")
        print(f"  Users       : {users}")
        print(f"  Children    : {students}")
        if users == 0:
            print(
                f"\n  No users yet — starting the API creates the admin account\n"
                f"  {settings.admin_email} / {settings.admin_password}"
            )
        if students == 0:
            print("\n  Tip: load demo data with  python -m app.seed")
        print()
        return 0

    except OperationFailure as exc:
        _fail("auth", exc)
    except ServerSelectionTimeoutError as exc:
        _fail("network", exc)
    except ConfigurationError as exc:
        _fail("config", exc)
    finally:
        await client.close()
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
