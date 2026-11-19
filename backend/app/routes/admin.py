from datetime import datetime, timezone
from urllib.parse import urlparse
from uuid import uuid4

import smtplib
from flask import Blueprint, current_app, g, jsonify, request

from app.extensions import get_database
from app.routes.scholarships import admin_authenticated
from app.services.notifications import (
    dispatch_notification,
    enqueue_notification,
    ensure_notification_indexes,
)


admin_bp = Blueprint("admin", __name__)
survey_bp = Blueprint("survey_results", __name__)


def ensure_admin_indexes(database):
    if current_app.extensions.get("admin_indexes_ready"):
        return
    database.surveys.create_index("id", unique=True)
    ensure_notification_indexes(database)
    current_app.extensions["admin_indexes_ready"] = True


@admin_bp.get("/analytics")
@admin_authenticated
def analytics():
    database = get_database()
    applications = list(database.applications.find({}))
    scholarships = list(database.scholarships.find({}))
    users_count = sum(
        user.get("role", "student") == "student"
        for user in database.users.find({"email_verified": True})
    )
    tickets = list(database.support_tickets.find({}))
    grievances = list(database.grievances.find({}))
    feedback = list(database.feedback.find({}))
    approved_feedback = [
        item
        for item in feedback
        if item.get("moderation_status", "approved") == "approved"
    ]
    ratings = {
        rating: sum(item.get("rating") == rating for item in approved_feedback)
        for rating in range(1, 6)
    }
    application_statuses = {
        status: sum(item.get("status") == status for item in applications)
        for status in ("draft", "submitted", "college_verified", "correction_required", "approved", "rejected", "paid")
    }
    scheme_counts = {}
    for application in applications:
        scheme_id = application.get("scholarship_id")
        scheme_counts[scheme_id] = scheme_counts.get(scheme_id, 0) + 1
    scheme_titles = {
        scheme["id"]: scheme.get("title", "Scholarship")
        for scheme in scholarships
    }
    return jsonify(
        generated_at=datetime.now(timezone.utc),
        students=users_count,
        scholarships={
            "total": len(scholarships),
            "active": sum(scheme.get("status") == "active" for scheme in scholarships),
            "verified": sum(bool(scheme.get("verified_at")) for scheme in scholarships),
        },
        applications={
            "total": len(applications),
            "by_status": application_statuses,
        },
        most_tracked_scholarships=[
            {
                "scholarship_id": scheme_id,
                "title": scheme_titles.get(scheme_id, "Archived scholarship"),
                "applications": count,
            }
            for scheme_id, count in sorted(
                scheme_counts.items(),
                key=lambda entry: (-entry[1], entry[0]),
            )[:10]
        ],
        support={
            "open_tickets": sum(ticket.get("status") in {"open", "in_progress"} for ticket in tickets),
            "open_grievances": sum(
                grievance.get("status") in {"received", "under_review"}
                for grievance in grievances
            ),
        },
        feedback={
            "count": len(approved_feedback),
            "pending": sum(item.get("moderation_status", "approved") == "pending" for item in feedback),
            "average_rating": (
                round(sum(item["rating"] for item in approved_feedback) / len(approved_feedback), 2)
                if approved_feedback
                else None
            ),
            "rating_distribution": ratings,
        },
    )


@admin_bp.post("/surveys")
@admin_authenticated
def create_survey_result():
    body = request.get_json(silent=True)
    required = {
        "title",
        "question",
        "language",
        "respondents",
        "options",
        "source_url",
        "survey_date",
        "status",
    }
    if not isinstance(body, dict) or set(body) != required:
        return jsonify(error=f"Required fields: {', '.join(sorted(required))}"), 400
    title, question, language = body["title"], body["question"], body["language"]
    if (
        not isinstance(title, str)
        or not title.strip()
        or len(title.strip()) > 160
        or not isinstance(question, str)
        or not question.strip()
        or len(question.strip()) > 500
        or not isinstance(language, str)
        or language not in {"en", "hi", "mr"}
    ):
        return jsonify(error="title, question, or language is invalid"), 400
    respondents = body["respondents"]
    if isinstance(respondents, bool) or not isinstance(respondents, int) or respondents < 1:
        return jsonify(error="respondents must be a positive integer"), 400
    options = body["options"]
    if not isinstance(options, list) or not 2 <= len(options) <= 20:
        return jsonify(error="options must contain between 2 and 20 results"), 400
    labels, counts = set(), 0
    normalized_options = []
    for option in options:
        if not isinstance(option, dict) or set(option) != {"label", "count"}:
            return jsonify(error="Each option must contain label and count"), 400
        label, count = option["label"], option["count"]
        if (
            not isinstance(label, str)
            or not label.strip()
            or len(label.strip()) > 160
            or label.strip() in labels
            or isinstance(count, bool)
            or not isinstance(count, int)
            or count < 0
        ):
            return jsonify(error="Survey option labels and counts must be valid and unique"), 400
        labels.add(label.strip())
        counts += count
        normalized_options.append({"label": label.strip(), "count": count})
    if counts > respondents:
        return jsonify(error="Option counts cannot exceed the respondent count"), 400
    source_url = body["source_url"]
    parsed_url = urlparse(source_url) if isinstance(source_url, str) else None
    if parsed_url is None or parsed_url.scheme not in {"https", "http"} or not parsed_url.netloc:
        return jsonify(error="source_url must be a valid http or https URL"), 400
    try:
        survey_date = datetime.strptime(body["survey_date"], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return jsonify(error="survey_date must use YYYY-MM-DD format"), 400
    if survey_date.isoformat() != body["survey_date"]:
        return jsonify(error="survey_date must use YYYY-MM-DD format"), 400
    if not isinstance(body["status"], str) or body["status"] not in {"draft", "published"}:
        return jsonify(error="status must be draft or published"), 400

    database = get_database()
    ensure_admin_indexes(database)
    survey = {
        "id": str(uuid4()),
        "title": title.strip(),
        "question": question.strip(),
        "language": language,
        "respondents": respondents,
        "options": normalized_options,
        "source_url": source_url.strip(),
        "survey_date": body["survey_date"],
        "status": body["status"],
        "created_by": g.current_user["user_id"],
        "created_at": datetime.now(timezone.utc),
    }
    database.surveys.insert_one(survey)
    return jsonify(survey=survey), 201


@survey_bp.get("/results")
def survey_results():
    database = get_database()
    ensure_admin_indexes(database)
    surveys = list(database.surveys.find({"status": "published"}))
    surveys.sort(key=lambda item: item.get("survey_date", ""), reverse=True)
    return jsonify(
        results=[
            {
                "id": survey["id"],
                "title": survey["title"],
                "question": survey["question"],
                "language": survey["language"],
                "respondents": survey["respondents"],
                "survey_date": survey["survey_date"],
                "source_url": survey["source_url"],
                "chart": {
                    "labels": [item["label"] for item in survey["options"]],
                    "values": [item["count"] for item in survey["options"]],
                },
            }
            for survey in surveys
        ],
        note="Only published survey data with an administrator-provided source is returned.",
    )


@admin_bp.post("/notifications/dispatch")
@admin_authenticated
def dispatch_notifications():
    channel = request.args.get("channel", "email")
    if channel != "email":
        return jsonify(error="Only SMTP email notifications are supported"), 400
    database = get_database()
    ensure_admin_indexes(database)
    today = datetime.now(timezone.utc).date().isoformat()
    queued_reminders = 0
    if channel == "email":
        for application in database.applications.find({}):
            reminder_date = application.get("reminder_date")
            user = database.users.find_one({"user_id": application["user_id"]})
            if user is None:
                current_app.logger.error(
                    "Skipping reminder for missing user on application %s",
                    application["id"],
                )
                continue
            if (
                reminder_date
                and reminder_date <= today
                and application.get("status") != "paid"
                and application.get("reminder_queued_for") != reminder_date
            ):
                enqueue_notification(
                    database,
                    f"reminder:{application['id']}:{reminder_date}",
                    user["email"],
                    f"Scholarship application reminder: {application['scholarship_title']}",
                    (
                        f"Your tracker reminder for {application['scholarship_title']} is due.\n"
                        f"Current status: {application['status'].replace('_', ' ').title()}.\n"
                        "Check the official scholarship portal for deadlines and required actions."
                    ),
                )
                application["reminder_queued_for"] = reminder_date
                database.applications.replace_one({"id": application["id"]}, application)
                queued_reminders += 1

            if application.get("status") == "paid":
                continue
            scheme = database.scholarships.find_one(
                {"id": application["scholarship_id"], "status": "active"}
            )
            deadline = scheme.get("deadline") if scheme else None
            if not deadline or deadline < today:
                continue
            days_remaining = (
                datetime.strptime(deadline, "%Y-%m-%d").date()
                - datetime.now(timezone.utc).date()
            ).days
            if days_remaining > 7:
                continue
            deadline_key = f"deadline:{application['id']}:{deadline}"
            if not database.notifications.find_one({"idempotency_key": deadline_key}):
                enqueue_notification(
                    database,
                    deadline_key,
                    user["email"],
                    f"Scholarship deadline approaching: {application['scholarship_title']}",
                    (
                        f"The listed deadline for {application['scholarship_title']} is "
                        f"{deadline} ({days_remaining} days remaining).\n"
                        "Confirm the deadline and submission requirements on the official scheme portal."
                    ),
                )
                queued_reminders += 1

    queued_statuses = {"pending", "failed"}
    pending = [
        notification
        for notification in database.notifications.find({"channel": channel})
        if notification.get("status") in queued_statuses
    ][:100]
    sent, failed = 0, 0
    for notification in pending:
        try:
            dispatch_notification(notification)
        except (RuntimeError, OSError, smtplib.SMTPException) as error:
            notification["status"] = "failed"
            notification["attempts"] = notification.get("attempts", 0) + 1
            notification["last_error"] = str(error)[:500]
            failed += 1
        else:
            notification["status"] = "sent"
            notification["attempts"] = notification.get("attempts", 0) + 1
            notification["sent_at"] = datetime.now(timezone.utc)
            notification.pop("last_error", None)
            sent += 1
        database.notifications.replace_one({"id": notification["id"]}, notification)
    return jsonify(
        queued_reminders=queued_reminders,
        attempted=len(pending),
        sent=sent,
        failed=failed,
        retryable_failures=failed,
    )


@admin_bp.get("/notifications")
@admin_authenticated
def list_notifications():
    database = get_database()
    ensure_admin_indexes(database)
    notifications = list(database.notifications.find({}))
    notifications.sort(key=lambda item: item.get("attempts", 0))
    return jsonify(
        notifications=[
            {
                "id": item["id"],
                "channel": item["channel"],
                "status": item["status"],
                "attempts": item["attempts"],
                "subject": item.get("subject", ""),
                "last_error": item.get("last_error"),
            }
            for item in notifications
        ]
    )
