import io
import re
import smtplib
from datetime import datetime, timezone
from functools import wraps
from uuid import uuid4

from cryptography.fernet import InvalidToken
from flask import Blueprint, current_app, g, jsonify, request, send_file
from pymongo.errors import DuplicateKeyError
from werkzeug.security import generate_password_hash

from app.extensions import get_database
from app.routes.applications import document_cipher
from app.routes.auth import authenticated, ensure_indexes as ensure_auth_indexes
from app.routes.scholarships import admin_authenticated
from app.services.auth import normalize_email
from app.services.notifications import dispatch_notification, enqueue_notification



colleges_bp = Blueprint("colleges", __name__)


def ensure_college_indexes(database):
    if current_app.extensions.get("college_indexes_ready"):
        return
    database.colleges.create_index("id", unique=True)
    database.colleges.create_index("code", unique=True)
    database.colleges.create_index("normalized_name", unique=True)
    database.applications.create_index([("college_id", 1), ("status", 1), ("updated_at", -1)])
    current_app.extensions["college_indexes_ready"] = True


def college_verifier_only(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.current_user.get("role") != "college_verifier":
            return jsonify(error="College verifier access is required"), 403
        return view(*args, **kwargs)

    return wrapped


def college_authenticated(view):
    return authenticated(college_verifier_only(view))


@colleges_bp.get("/list")
@authenticated
def list_registered_colleges():
    database = get_database()
    ensure_college_indexes(database)
    colleges = list(database.colleges.find({"verified": True}))
    colleges = [
        item for item in colleges
        if item.get("active", True)
    ]
    colleges.sort(key=lambda item: item["name"].casefold())
    return jsonify(colleges=[{"id": item["id"], "name": item["name"], "code": item["code"]} for item in colleges])


@colleges_bp.get("/admin")
@admin_authenticated
def admin_colleges():
    database = get_database()
    ensure_college_indexes(database)
    results = []
    for college in database.colleges.find({}):
        verifier = database.users.find_one({"user_id": college.get("verifier_user_id")}) or {}
        results.append({
            "id": college["id"],
            "name": college["name"],
            "code": college["code"],
            "verified": college.get("verified", False),
            "active": college.get("active", True),
            "verifier": {
                "user_id": verifier.get("user_id"),
                "full_name": verifier.get("full_name"),
                "email": verifier.get("email"),
            } if verifier else None,
        })
    results.sort(key=lambda item: item["name"].casefold())
    return jsonify(colleges=results)


@colleges_bp.post("/admin")
@admin_authenticated
def create_college_and_verifier():
    data = request.get_json(silent=True)
    required = {"name", "code", "verifier_name", "verifier_email", "verifier_password"}
    if not isinstance(data, dict) or set(data) != required:
        return jsonify(error=f"Required fields: {', '.join(sorted(required))}"), 400

    name = data["name"].strip() if isinstance(data["name"], str) else ""
    code = data["code"].strip().upper() if isinstance(data["code"], str) else ""
    verifier_name = data["verifier_name"].strip() if isinstance(data["verifier_name"], str) else ""
    password = data["verifier_password"]
    if not 2 <= len(name) <= 160:
        return jsonify(error="College name must be between 2 and 160 characters"), 400
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9-]{2,23}", code):
        return jsonify(error="College code must be 3 to 24 letters, numbers, or hyphens"), 400
    if not 2 <= len(verifier_name) <= 120:
        return jsonify(error="Verifier name must be between 2 and 120 characters"), 400
    if not isinstance(password, str) or not 10 <= len(password) <= 128:
        return jsonify(error="Verifier password must be between 10 and 128 characters"), 400
    try:
        email = normalize_email(data["verifier_email"])
    except ValueError as error:
        return jsonify(error=str(error)), 400

    database = get_database()
    ensure_auth_indexes(database)
    ensure_college_indexes(database)
    normalized_name = " ".join(name.casefold().split())
    if database.colleges.find_one({"code": code}) or database.colleges.find_one({"normalized_name": normalized_name}):
        return jsonify(error="A college with this name or code already exists"), 409
    if database.users.find_one({"email": email}):
        return jsonify(error="An account with this email already exists"), 409

    now = datetime.now(timezone.utc)
    college_id = str(uuid4())
    verifier_id = f"CV-{uuid4().hex[:12].upper()}"
    college = {
        "id": college_id,
        "name": name,
        "normalized_name": normalized_name,
        "code": code,
        "verified": True,
        "active": True,
        "created_by": g.current_user["user_id"],
        "created_at": now,
        "verifier_user_id": verifier_id,
    }
    verifier = {
        "user_id": verifier_id,
        "full_name": verifier_name,
        "email": email,
        "mobile": "",
        "password_hash": generate_password_hash(password),
        "email_verified": True,
        "role": "college_verifier",
        "college_id": college_id,
        "college_name": name,
        "created_at": now,
    }
    try:
        database.colleges.insert_one(college)
        database.users.insert_one(verifier)
    except DuplicateKeyError:
        database.colleges.delete_one({"id": college_id})
        return jsonify(error="The college code, college name, or verifier email is already in use"), 409
    return jsonify(
        message="Verified college and verifier account created.",
        college={"id": college_id, "name": name, "code": code, "verified": True},
        verifier={"user_id": verifier_id, "full_name": verifier_name, "email": email},
    ), 201


@colleges_bp.delete("/admin/<college_id>")
@admin_authenticated
def delete_college_verifier(college_id):
    database = get_database()
    college = database.colleges.find_one({"id": college_id})
    if college is None:
        return jsonify(error="College was not found"), 404
    if not college.get("active", True):
        return jsonify(error="This college is already inactive"), 409

    verifier_user_id = college.get("verifier_user_id")
    linked_applications = database.applications.count_documents({"college_id": college_id})
    if linked_applications == 0:
        if verifier_user_id:
            database.users.delete_one({"user_id": verifier_user_id})
        database.colleges.delete_one({"id": college_id})
        return jsonify(
            message="College and verifier account deleted.",
            college_id=college_id,
            deleted=True,
            verifier_access_removed=bool(verifier_user_id),
        )

    now = datetime.now(timezone.utc)
    college["active"] = False
    college["verified"] = False
    college["deactivated_at"] = now
    college["deactivated_by"] = g.current_user["user_id"]
    database.colleges.replace_one({"id": college_id}, college)
    if verifier_user_id:
        database.users.delete_one({"user_id": verifier_user_id})

    return jsonify(
        message="College deactivated and verifier access removed. Existing applications remain available to the administrator.",
        college_id=college_id,
        deleted=False,
        linked_applications=linked_applications,
        verifier_access_removed=bool(verifier_user_id),
    )


@colleges_bp.get("/applications")
@college_authenticated
def verifier_application_queue():
    database = get_database()
    college_id = g.current_user.get("college_id")
    college = database.colleges.find_one({"id": college_id, "verified": True})
    if college is None:
        return jsonify(error="This verifier is not linked to an active verified college"), 403
    applications = [
        application
        for application in database.applications.find({
            "college_id": college_id,
            "status": {"$in": ["submitted", "correction_required"]},
        })
        if application.get("status") != "correction_required"
        or application.get("correction_requested_by") != "admin"
    ]
    applications.sort(
        key=lambda item: item.get("updated_at") or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    results = []
    for application in applications:
        student = database.users.find_one({"user_id": application.get("user_id")}) or {}
        results.append({
            **{
                key: value
                for key, value in application.items()
                if key not in {"_id", "bank_details_encrypted"}
            },
            "student": {
                "user_id": student.get("user_id"),
                "full_name": student.get("full_name", ""),
                "email": student.get("email", ""),
                "mobile": student.get("mobile", ""),
            },
        })
    return jsonify(college={"id": college["id"], "name": college["name"], "code": college["code"]}, applications=results)


@colleges_bp.post("/applications/<application_id>/review")
@college_authenticated
def review_college_application(application_id):
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or set(data) - {"status", "note"}:
        return jsonify(error="Provide a status and only the supported review fields"), 400
    status = data.get("status")
    if not isinstance(status, str) or status not in {"college_verified", "correction_required", "rejected"}:
        return jsonify(error="status must be college_verified, correction_required, or rejected"), 400
    note = data.get("note", "")
    if not isinstance(note, str) or len(note.strip()) > 2000:
        return jsonify(error="Review note must be at most 2000 characters"), 400
    note = note.strip()
    if status in {"correction_required", "rejected"} and not note:
        return jsonify(error="A note is required when requesting corrections or rejecting an application"), 400

    database = get_database()
    college_id = g.current_user.get("college_id")
    college = database.colleges.find_one({"id": college_id, "verified": True})
    if college is None:
        return jsonify(error="This verifier is not linked to an active verified college"), 403
    application = database.applications.find_one({"id": application_id, "college_id": college_id})
    if application is None:
        return jsonify(error="Application was not found for this college"), 404
    if application.get("status") not in {"submitted", "correction_required"}:
        return jsonify(error="Only submitted applications can be reviewed by the college"), 409

    now = datetime.now(timezone.utc)
    previous_status = application["status"]
    application["status"] = status
    application["college_note"] = note
    application["college_reviewed_by"] = g.current_user["email"]
    application["college_reviewed_at"] = now.isoformat()
    application["updated_at"] = now
    if status != previous_status:
        application.setdefault("status_history", []).append({
            "status": status,
            "at": now.isoformat(),
            "actor": g.current_user["email"],
            "role": "college_verifier",
        })
    if status == "correction_required":
        application["correction_requested_by"] = "college"
    elif status != previous_status:
        application.pop("correction_requested_by", None)
    database.applications.replace_one({"id": application_id, "college_id": college_id}, application)
    student = database.users.find_one({"user_id": application.get("user_id")}) or {}
    email_status = None
    if student.get("email") and status != previous_status:
        body = (
            f"Your application for {application['scholarship_title']} was "
            f"{status.replace('_', ' ')} by {college['name']}.\n\n"
            f"Application ID: {application_id}"
        )
        if status == "college_verified":
            body += "\nIt has been forwarded to the department administrator for review."
        elif status == "correction_required":
            body += f"\nPlease make the requested corrections and resubmit:\n{note}"
        elif status == "rejected":
            body += f"\nReason: {note}"
        notification = enqueue_notification(
            database,
            f"college-application-status:{application_id}:{status}:{now.isoformat()}",
            student["email"],
            f"Scholarship application update: {application['scholarship_title']}",
            body,
        )
        try:
            dispatch_notification(notification)
        except (RuntimeError, OSError, smtplib.SMTPException) as error:
            notification["status"] = "failed"
            notification["attempts"] = notification.get("attempts", 0) + 1
            notification["last_error"] = str(error)[:500]
            current_app.logger.exception(
                "Could not immediately send college application status email for %s",
                application_id,
            )
            email_status = "failed"
        else:
            notification["status"] = "sent"
            notification["attempts"] = notification.get("attempts", 0) + 1
            notification["sent_at"] = datetime.now(timezone.utc)
            notification.pop("last_error", None)
            email_status = "sent"
        database.notifications.replace_one({"id": notification["id"]}, notification)
    return jsonify(application={
        key: value
        for key, value in application.items()
        if key not in {"_id", "bank_details_encrypted"}
    }, email_status=email_status)


@colleges_bp.get("/applications/<application_id>/documents/<document_id>")
@college_authenticated
def download_college_application_document(application_id, document_id):
    database = get_database()
    application = database.applications.find_one({
        "id": application_id,
        "college_id": g.current_user.get("college_id"),
    })
    if application is None:
        return jsonify(error="Application was not found for this college"), 404
    metadata = next(
        (item for item in application.get("documents", []) if item["id"] == document_id),
        None,
    )
    if metadata is None:
        return jsonify(error="Application document was not found"), 404
    stored = database.application_documents.find_one({
        "id": document_id,
        "application_id": application_id,
    })
    if stored is None:
        return jsonify(error="Stored application document was not found"), 404
    try:
        raw = document_cipher().decrypt(stored["encrypted_data"])
    except RuntimeError as error:
        current_app.logger.error("College document decryption is unavailable: %s", error)
        return jsonify(error="Secure document storage is unavailable. Contact the administrator."), 503
    except InvalidToken:
        current_app.logger.exception("Could not decrypt college application document %s", document_id)
        return jsonify(error="This document could not be opened; contact the administrator"), 500
    response = send_file(
        io.BytesIO(raw),
        mimetype=metadata["mime_type"],
        as_attachment=True,
        download_name=metadata["filename"],
        conditional=False,
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response
