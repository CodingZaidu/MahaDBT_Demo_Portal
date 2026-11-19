from flask import current_app
from pymongo import MongoClient


def get_database():
    client = current_app.extensions.get("mongo_client")
    if client is None:
        client = MongoClient(
            current_app.config["MONGO_URI"],
            serverSelectionTimeoutMS=3000,
            tz_aware=True,
        )
        current_app.extensions["mongo_client"] = client
    return client[current_app.config["MONGO_DB_NAME"]]