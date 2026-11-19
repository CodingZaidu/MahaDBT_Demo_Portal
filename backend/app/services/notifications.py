from uuid import uuid4

from flask import current_app
from pymongo.errors import DuplicateKeyError

from app.services.auth import send_email


def ensure_notification_indexes(database):
    if current_app.extensions.get("notification_indexes_ready"):
        return
    database.notifications.create_index("id", unique=True)
    database.notifications.create_index("idempotency_key", unique=True)
    database.notifications.create_index([("status", 1), ("channel", 1)])
    current_app.extensions["notification_indexes_ready"] = True


def enqueue_notification(
    database,
    idempotency_key,
    recipient,
    subject,
    body,
):
    ensure_notification_indexes(database)
    existing = database.notifications.find_one({"idempotency_key": idempotency_key})
    if existing:
        return existing
    notification = {
        "id": str(uuid4()),
        "idempotency_key": idempotency_key,
        "channel": "email",
        "recipient": recipient,
        "subject": subject,
        "body": body,
        "status": "pending",
        "attempts": 0,
    }
    try:
        database.notifications.insert_one(notification)
    except DuplicateKeyError:
        existing = database.notifications.find_one({"idempotency_key": idempotency_key})
        if existing is None:
            raise
        return existing
    return notification


def dispatch_notification(notification):
    if notification["channel"] != "email":
        raise RuntimeError("Only SMTP email notifications are supported")
    send_email(
        notification["recipient"],
        notification["subject"],
        notification["body"],
    )
