import base64
import io
import json
import re
import smtplib
import warnings
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from functools import wraps
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken
from flask import Blueprint, current_app, g, jsonify, request, send_file
from PIL import Image, ImageFilter, UnidentifiedImageError
from PIL.ImageStat import Stat
from pymongo.errors import DuplicateKeyError
from werkzeug.utils import secure_filename

from app.extensions import get_database
from app.routes.auth import authenticated
from app.routes.scholarships import admin_authenticated
from app.services.applications import (
    APPLICATION_STATUSES,
    normalize_application_form,
    validate_application_update,
)
from app.services.notifications import dispatch_notification, enqueue_notification


applications_bp = Blueprint("applications", __name__)
MAX_DOCUMENT_BYTES = 8 * 1024 * 1024
ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG"}
MAX_IMAGE_PIXELS = 40_000_000
STAGE_GUIDANCE = {
    "draft": "Complete this website's application form and upload the scheme-specific documents.",
    "submitted": "Your application was sent to your college for verification.",
    "college_verified": "College verification was recorded; wait for the administrator's decision.",
    "correction_required": "A reviewer requested a correction. Update the application and resubmit it for review.",
    "approved": "Your application is approved. Fund distribution is pending; the administrator will update the status when the funds are disbursed.",
    "rejected": "Read the rejection reason, correct the issue, and check whether reapplication is allowed.",
    "paid": "The administrator recorded fund distribution. Check with the scholarship provider about the payment channel.",
}


def ensure_indexes(database):
    if current_app.extensions.get("application_indexes_ready"):
        return
    database.applications.create_index("id", unique=True)
    database.applications.create_index(
        [("user_id", 1), ("scholarship_id", 1)], unique=True
    )
    database.applications.create_index([("user_id", 1), ("reminder_date", 1)])
    database.application_documents.create_index("id", unique=True)
    database.application_documents.create_index(
        [("application_id", 1), ("user_id", 1)]
    )
    current_app.extensions["application_indexes_ready"] = True


def safe_application(document):
    return {
        key: value
        for key, value in document.items()
        if key not in {"_id", "bank_details_encrypted"}
    }


def finance_only(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        allowed_emails = {
            email.strip().casefold()
            for email in current_app.config.get("FINANCE_ADMIN_EMAILS", [])
            if isinstance(email, str) and email.strip()
        }
        if g.current_user["email"].casefold() not in allowed_emails:
            return jsonify(error="Finance administrator access is required"), 403
        return view(*args, **kwargs)

    return wrapped


def finance_authenticated(view):
    return authenticated(finance_only(view))


def normalize_bank_details(value):
    if not isinstance(value, dict) or set(value) != {"account_number", "ifsc"}:
        raise ValueError("Provide only account_number and IFSC")
    account_number = value["account_number"]
    if not isinstance(account_number, str):
        raise ValueError("Bank account number must contain 9 to 18 digits")
    account_number = account_number.strip().replace(" ", "")
    if not re.fullmatch(r"\d{9,18}", account_number):
        raise ValueError("Bank account number must contain 9 to 18 digits")
    ifsc = value["ifsc"]
    if not isinstance(ifsc, str):
        raise ValueError("IFSC code must be a valid 11-character code")
    ifsc = ifsc.strip().upper()
    if not re.fullmatch(r"[A-Z]{4}0[A-Z0-9]{6}", ifsc):
        raise ValueError("IFSC code must be a valid 11-character code")
    return {"account_number": account_number, "ifsc": ifsc}


def encrypt_bank_details(value):
    key = current_app.config.get("BANK_DETAILS_ENCRYPTION_KEY")
    if not isinstance(key, str) or not key:
        raise RuntimeError("BANK_DETAILS_ENCRYPTION_KEY is not configured")
    try:
        cipher = Fernet(key.encode("ascii"))
    except (UnicodeEncodeError, ValueError) as error:
        raise RuntimeError("BANK_DETAILS_ENCRYPTION_KEY is invalid") from error
    details = normalize_bank_details(value)
    return cipher.encrypt(json.dumps(details).encode("utf-8")).decode("ascii")


def decrypt_bank_details(value):
    key = current_app.config.get("BANK_DETAILS_ENCRYPTION_KEY")
    if not isinstance(key, str) or not key:
        raise RuntimeError("BANK_DETAILS_ENCRYPTION_KEY is not configured")
    try:
        cipher = Fernet(key.encode("ascii"))
        raw = cipher.decrypt(value.encode("ascii"))
        details = json.loads(raw.decode("utf-8"))
    except (UnicodeEncodeError, ValueError, InvalidToken, json.JSONDecodeError) as error:
        raise RuntimeError("Stored bank details could not be decrypted") from error
    return normalize_bank_details(details)


def normalize_distributed_amount(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError("distributed_amount is required and must be an INR amount")
    amount_text = str(value).strip()
    if not re.fullmatch(r"(?:0|[1-9]\d{0,11})(?:\.\d{1,2})?", amount_text):
        raise ValueError("distributed_amount must be a positive INR amount with up to 2 decimal places")
    try:
        amount = Decimal(amount_text)
    except InvalidOperation as error:
        raise ValueError("distributed_amount must be a valid INR amount") from error
    if amount <= 0:
        raise ValueError("distributed_amount must be greater than zero")
    return format(amount.quantize(Decimal("0.01")), "f")


def document_cipher():
    key = current_app.config.get("DOCUMENT_ENCRYPTION_KEY")
    if not isinstance(key, str) or not key:
        raise RuntimeError("DOCUMENT_ENCRYPTION_KEY is not configured")
    try:
        return Fernet(key.encode("ascii"))
    except (UnicodeEncodeError, ValueError) as error:
        raise RuntimeError("DOCUMENT_ENCRYPTION_KEY is invalid") from error


def validate_application_document(uploaded):
    filename = secure_filename(uploaded.filename or "")
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    raw = uploaded.stream.read(MAX_DOCUMENT_BYTES + 1)
    if len(raw) > MAX_DOCUMENT_BYTES:
        raise ValueError("File is larger than the 8 MB upload limit")
    if not raw:
        raise ValueError("The uploaded file is empty")
    if extension == "pdf" and raw.startswith(b"%PDF-"):
        return raw, "application/pdf", filename or "document.pdf"
    if extension not in {"jpg", "jpeg", "png"}:
        raise ValueError("Only PDF, JPG, and PNG files are allowed")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            image = Image.open(io.BytesIO(raw))
            if image.format not in ALLOWED_IMAGE_FORMATS:
                raise ValueError("File contents do not match a JPG or PNG image")
            if (extension == "png") != (image.format == "PNG"):
                raise ValueError("File extension does not match the image contents")
            if image.width < 100 or image.height < 100:
                raise ValueError("Image is too small to read; upload a clearer scan")
            if image.width * image.height > MAX_IMAGE_PIXELS:
                raise ValueError("Image dimensions are too large to process safely")
            image.load()
            gray = image.convert("L")
            edges = gray.filter(ImageFilter.FIND_EDGES)
            margin_x = max(1, image.width // 20)
            margin_y = max(1, image.height // 20)
            detail = edges.crop(
                (margin_x, margin_y, image.width - margin_x, image.height - margin_y)
            )
            if Stat(detail).stddev[0] < 12:
                raise ValueError("Image appears blurry; take a clear photo in good light and upload again")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise ValueError("The image is invalid, damaged, or too large to process") from error
    mime_type = "image/png" if extension == "png" else "image/jpeg"
    return raw, mime_type, filename


@applications_bp.post("")
@authenticated
def create_application():
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get("scholarship_id"), str):
        return jsonify(error="scholarship_id is required"), 400
    data = dict(data)
    if data.pop("document_consent", None) is not True:
        return jsonify(error="Consent to encrypted document storage and administrator review is required"), 400
    bank_details = data.pop("bank_details", None)
    bank_details_consent = data.pop("bank_details_consent", None)
    if bank_details is not None and bank_details_consent is not True:
        return jsonify(error="Consent to encrypted bank-detail storage and finance review is required"), 400
    database = get_database()
    ensure_indexes(database)
    scholarship_id = data["scholarship_id"].strip()
    scholarship = database.scholarships.find_one(
        {"id": scholarship_id, "status": "active"}
    )
    if scholarship is None:
        return jsonify(error="Active scholarship was not found"), 404
    deadline = scholarship.get("deadline")
    if deadline is not None:
        try:
            deadline_date = date.fromisoformat(deadline)
        except (TypeError, ValueError):
            current_app.logger.error(
                "Scholarship %s has an invalid application deadline", scholarship_id
            )
            return jsonify(error="Scholarship deadline is invalid. Contact the administrator."), 409
        if deadline_date < datetime.now(timezone.utc).date():
            return jsonify(error="The scholarship application deadline has passed"), 409
    existing_application = database.applications.find_one(
        {"user_id": g.current_user["user_id"], "scholarship_id": scholarship_id}
    )
    if existing_application:
        if existing_application.get("status") == "draft":
            return jsonify(
                application=safe_application(existing_application),
                resumed=True,
            ), 200
        return jsonify(error="An application tracker already exists for this scholarship"), 409
    now = datetime.now(timezone.utc)
    document = {
        "id": str(uuid4()),
        "user_id": g.current_user["user_id"],
        "scholarship_id": scholarship_id,
        "scholarship_title": scholarship["title"],
        "status": "draft",
        "official_application_id": None,
        "application_date": datetime.now(timezone.utc).date().isoformat(),
        "reminder_date": None,
        "rejection_reason": None,
        "notes": "",
        "application_form": {},
        "payout_amount": scholarship.get("payout_amount"),
        "documents": [],
        "document_consent_at": datetime.now(timezone.utc).isoformat(),
        "bank_details_consent_at": None,
        "bank_details_encrypted": None,
        "checklist": [
            {"name": name, "completed": False}
            for name in scholarship.get("documents", [])
        ],
        "status_history": [{"status": "draft", "at": now.isoformat()}],
        "created_at": now,
        "updated_at": now,
    }
    try:
        document = validate_application_update(data, document, creating=True)
    except ValueError as error:
        return jsonify(error=str(error)), 400
    if bank_details is not None:
        try:
            document["bank_details_encrypted"] = encrypt_bank_details(bank_details)
        except RuntimeError as error:
            current_app.logger.error("Bank-detail encryption is unavailable: %s", error)
            return jsonify(error="Encrypted bank-detail storage is not configured. Contact the administrator."), 503
        except ValueError as error:
            return jsonify(error=str(error)), 400
        document["bank_details_consent_at"] = datetime.now(timezone.utc).isoformat()
    document.update(
        id=str(uuid4()),
        user_id=g.current_user["user_id"],
        scholarship_id=scholarship_id,
        scholarship_title=scholarship["title"],
        status_history=[{"status": document["status"], "at": now.isoformat()}],
        created_at=now,
        updated_at=now,
    )
    if database.applications.find_one(
        {"user_id": g.current_user["user_id"], "scholarship_id": scholarship_id}
    ):
        return jsonify(error="An application tracker already exists for this scholarship"), 409
    try:
        database.applications.insert_one(document)
    except DuplicateKeyError:
        existing_application = database.applications.find_one(
            {"user_id": g.current_user["user_id"], "scholarship_id": scholarship_id}
        )
        if existing_application and existing_application.get("status") == "draft":
            return jsonify(
                application=safe_application(existing_application),
                resumed=True,
            ), 200
        return jsonify(error="An application tracker already exists for this scholarship"), 409
    return jsonify(application=safe_application(document)), 201


@applications_bp.post("/<application_id>/documents")
@authenticated
def upload_application_document(application_id):
    database = get_database()
    application = database.applications.find_one(
        {"id": application_id, "user_id": g.current_user["user_id"]}
    )
    if application is None:
        return jsonify(error="Application was not found"), 404
    if application.get("status") not in {"draft", "correction_required"}:
        return jsonify(error="Documents can only be uploaded before initial submission or while corrections are requested"), 409

    document_name = request.form.get("document_name", "").strip()
    if not document_name or len(document_name) > 200:
        return jsonify(error="document_name is required and must be at most 200 characters"), 400
    required_names = {item["name"] for item in application.get("checklist", [])}
    optional_names = {
        "Bank passbook",
        "Income certificate",
        "Domicile certificate",
        "Admission receipt",
    }
    if document_name not in required_names | optional_names:
        return jsonify(error="This document is not part of this application's checklist"), 400
    uploaded = request.files.get("file")
    if uploaded is None or not uploaded.filename:
        return jsonify(error="Choose a document file to upload"), 400
    try:
        raw, mime_type, filename = validate_application_document(uploaded)
        cipher = document_cipher()
    except RuntimeError as error:
        current_app.logger.error("Application document encryption is unavailable: %s", error)
        return jsonify(error="Secure document storage is not configured. Contact the administrator."), 503
    except ValueError as error:
        return jsonify(error=str(error)), 400

    document_id = str(uuid4())
    metadata = {
        "id": document_id,
        "name": document_name,
        "filename": filename,
        "mime_type": mime_type,
        "size_bytes": len(raw),
        "required": document_name in required_names,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    }
    encrypted_record = {
        "id": document_id,
        "application_id": application_id,
        "user_id": g.current_user["user_id"],
        "encrypted_data": cipher.encrypt(raw),
        "created_at": datetime.now(timezone.utc),
    }
    try:
        database.application_documents.insert_one(encrypted_record)
    except DuplicateKeyError:
        return jsonify(error="Document upload could not be saved; retry with a new upload"), 409

    previous = next(
        (item for item in application.get("documents", []) if item["name"] == document_name),
        None,
    )
    if previous:
        database.application_documents.delete_one(
            {"id": previous["id"], "user_id": g.current_user["user_id"]}
        )
    application["documents"] = [
        item for item in application.get("documents", []) if item["name"] != document_name
    ] + [metadata]
    if document_name in required_names:
        for item in application.get("checklist", []):
            if item["name"] == document_name:
                item["completed"] = True
    application["updated_at"] = datetime.now(timezone.utc)
    database.applications.replace_one(
        {"id": application_id, "user_id": g.current_user["user_id"]},
        application,
    )
    return jsonify(document=metadata, application=safe_application(application)), 201


@applications_bp.get("")
@authenticated
def list_applications():
    database = get_database()
    ensure_indexes(database)
    documents = list(
        database.applications.find({"user_id": g.current_user["user_id"]})
    )
    documents.sort(key=lambda item: item.get("updated_at", datetime.min), reverse=True)
    return jsonify(
        applications=[safe_application(document) for document in documents],
        totals={
            status: sum(document["status"] == status for document in documents)
            for status in APPLICATION_STATUSES
        },
    )


@applications_bp.get("/dashboard")
@authenticated
def application_dashboard():
    database = get_database()
    ensure_indexes(database)
    documents = list(
        database.applications.find({"user_id": g.current_user["user_id"]})
    )
    documents.sort(key=lambda item: item.get("updated_at", datetime.min), reverse=True)
    today = datetime.now(timezone.utc).date().isoformat()
    for document in documents:
        scholarship = database.scholarships.find_one({"id": document["scholarship_id"]})
        deadline = scholarship.get("deadline") if scholarship else None
        document["scheme_deadline"] = deadline
        document["deadline_days_remaining"] = (
            (datetime.fromisoformat(deadline).date() - datetime.now(timezone.utc).date()).days
            if deadline
            else None
        )
    upcoming = [
        safe_application(document)
        for document in documents
        if document.get("reminder_date") and document["reminder_date"] >= today
    ]
    return jsonify(
        applications=[safe_application(document) for document in documents],
        totals={
            status: sum(document["status"] == status for document in documents)
            for status in APPLICATION_STATUSES
        },
        due_reminders=upcoming,
    )


@applications_bp.get("/<application_id>")
@authenticated
def get_application(application_id):
    application = get_database().applications.find_one(
        {"id": application_id, "user_id": g.current_user["user_id"]}
    )
    if application is None:
        return jsonify(error="Application was not found"), 404
    return jsonify(application=safe_application(application))


@applications_bp.patch("/<application_id>")
@authenticated
def update_application(application_id):
    database = get_database()
    ensure_indexes(database)
    existing = database.applications.find_one(
        {"id": application_id, "user_id": g.current_user["user_id"]}
    )
    if existing is None:
        return jsonify(error="Application was not found"), 404
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="Request body must be a JSON object"), 400
    data = dict(data)
    bank_details = data.pop("bank_details", None)
    bank_details_consent = data.pop("bank_details_consent", None)
    if isinstance(data, dict) and "status" in data:
        if not isinstance(data["status"], str) or data["status"] not in {"draft", "submitted"}:
            return jsonify(error="Only administrators can approve, reject, or mark applications paid"), 403
    if existing.get("status") not in {"draft", "correction_required"}:
        protected_fields = set(data) - {"status", "reminder_date", "notes"}
        if protected_fields:
            return jsonify(error="Application details are locked until a reviewer requests corrections"), 409
    if existing.get("status") != "draft" and isinstance(data, dict) and (
        "application_form" in data or "checklist" in data
    ) and existing.get("status") != "correction_required":
        return jsonify(error="Submitted application details cannot be changed"), 409
    try:
        updated = validate_application_update(data, existing)
    except ValueError as error:
        return jsonify(error=str(error)), 400

    now = datetime.now(timezone.utc)
    if bank_details is not None:
        if existing.get("status") != "draft":
            return jsonify(error="Bank details cannot be changed after submitting the application"), 409
        if bank_details_consent is not True:
            return jsonify(error="Consent to encrypted bank-detail storage and finance review is required"), 400
        try:
            updated["bank_details_encrypted"] = encrypt_bank_details(bank_details)
        except RuntimeError as error:
            current_app.logger.error("Bank-detail encryption is unavailable: %s", error)
            return jsonify(error="Encrypted bank-detail storage is not configured. Contact the administrator."), 503
        except ValueError as error:
            return jsonify(error=str(error)), 400
        updated["bank_details_consent_at"] = now.isoformat()
    elif bank_details_consent is not None:
        return jsonify(error="Bank details must be provided with bank-detail consent"), 400

    correction_requested_by = existing.get("correction_requested_by")
    if updated["status"] == "submitted":
        if not updated.get("bank_details_encrypted"):
            return jsonify(error="Add bank account details and consent before submitting"), 400
        uploaded_names = {
            item["name"]
            for item in updated.get("documents", [])
            if item.get("required")
        }
        missing_documents = [
            item["name"]
            for item in updated.get("checklist", [])
            if item["name"] not in uploaded_names
        ]
        if missing_documents:
            return jsonify(error=f"Upload required documents before submitting: {', '.join(missing_documents)}"), 400
        try:
            updated["application_form"] = normalize_application_form(
                updated.get("application_form")
            )
        except ValueError as error:
            return jsonify(error=str(error)), 400
        college_name = " ".join(updated["application_form"]["college"].casefold().split())
        college = database.colleges.find_one({"normalized_name": college_name})
        returning_to_inactive_college = bool(
            college
            and existing.get("status") == "correction_required"
            and existing.get("college_id") == college.get("id")
            and not college.get("active", True)
        )
        if college is None or (
            not college.get("verified", False) and not returning_to_inactive_college
        ) or (
            not college.get("active", True) and not returning_to_inactive_college
        ):
            return jsonify(error="Select a college registered by the administrator before submitting"), 400
        updated["college_id"] = college["id"]
        updated["college_name"] = college["name"]
        if correction_requested_by == "admin" or not college.get("active", True):
            updated["status"] = "college_verified"
        else:
            updated.pop("college_note", None)
            updated.pop("college_reviewed_by", None)
            updated.pop("college_reviewed_at", None)
        updated.pop("correction_requested_by", None)
    history = list(existing.get("status_history", []))
    if updated["status"] != existing["status"]:
        history.append({"status": updated["status"], "at": now.isoformat(), "role": "student"})
    updated["status_history"] = history
    updated["updated_at"] = now
    database.applications.replace_one(
        {"id": application_id, "user_id": g.current_user["user_id"]},
        updated,
    )
    if updated["status"] != existing["status"]:
        message = (
            f"Your application for {updated['scholarship_title']} "
            f"is now: {updated['status'].replace('_', ' ').title()}.\n\n"
            f"Application ID: {updated['id']}\n"
            + (
                "Your corrected application has been returned to the department administrator for review."
                if correction_requested_by == "admin" and updated["status"] == "college_verified"
                else "It has been sent to the college verifier for review."
                if updated["status"] == "submitted"
                else "This is an internal application status update."
            )
        )
        enqueue_notification(
            database,
            f"status:{updated['id']}:{updated['status']}:{updated['updated_at'].isoformat()}",
            g.current_user["email"],
            f"Scholarship application update: {updated['scholarship_title']}",
            message,
        )
    return jsonify(application=safe_application(updated))


@applications_bp.get("/admin")
@admin_authenticated
def admin_applications():
    database = get_database()
    documents = [
        document
        for document in database.applications.find({})
        if document.get("status") != "draft"
    ]

    def updated_timestamp(application):
        value = application.get("updated_at")
        if isinstance(value, str):
            try:
                value = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return float("-inf")
        if not isinstance(value, datetime):
            return float("-inf")
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.timestamp()

    documents.sort(key=updated_timestamp, reverse=True)
    results = []
    for application in documents:
        student = database.users.find_one({"user_id": application.get("user_id")}) or {}
        college_record = database.colleges.find_one({"id": application.get("college_id")}) if application.get("college_id") else None
        results.append({
            **safe_application(application),
            "college_active": (
                bool(college_record and college_record.get("verified", False) and college_record.get("active", True))
                if application.get("college_id") else None
            ),
            "student": {
                "user_id": student.get("user_id", application.get("user_id")),
                "full_name": student.get("full_name", ""),
                "email": student.get("email", ""),
                "mobile": student.get("mobile", ""),
            },
        })
    return jsonify(applications=results)


@applications_bp.patch("/admin/<application_id>")
@admin_authenticated
def review_application(application_id):
    database = get_database()
    application = database.applications.find_one({"id": application_id})
    if application is None:
        return jsonify(error="Application was not found"), 404
    if application.get("status") == "draft":
        return jsonify(error="A draft application cannot be reviewed"), 409

    data = request.get_json(silent=True)
    if not isinstance(data, dict) or set(data) - {
        "status", "rejection_reason", "admin_note", "distributed_amount"
    }:
        return jsonify(error="Provide a status and only the supported review fields"), 400
    status = data.get("status")
    if not isinstance(status, str) or status not in {
        "college_verified", "correction_required", "approved", "rejected"
    }:
        return jsonify(error="status must be college_verified, correction_required, approved, or rejected"), 400
    previous_status = application.get("status")
    allowed = {
        "submitted": {"college_verified", "correction_required", "approved", "rejected"},
        "college_verified": {"college_verified", "correction_required", "approved", "rejected"},
        "approved": {"approved"},
        "rejected": {"rejected"},
        "paid": {"paid"},
    }
    college_record = database.colleges.find_one({"id": application["college_id"]}) if application.get("college_id") else None
    college_active = bool(
        college_record
        and college_record.get("verified", False)
        and college_record.get("active", True)
    )
    if application.get("college_id") and college_active and application.get("status") != "college_verified":
        return jsonify(error="The college must verify this application before department review"), 409
    if status not in allowed.get(application["status"], set()):
        return jsonify(error=f"Cannot change status from {application['status']} to {status}"), 400
    if status == "approved":
        if not application.get("bank_details_encrypted"):
            return jsonify(error="Encrypted bank details are required before approval"), 409
        scholarship = database.scholarships.find_one(
            {"id": application.get("scholarship_id")}
        )
        payout_amount = (
            scholarship.get("payout_amount") if scholarship else None
        ) or application.get("payout_amount")
        if not payout_amount:
            return jsonify(
                error="Set an exact fixed amount in Admin dashboard > Scholarships before approval",
                code="missing_fixed_payout_amount",
                scholarship_id=application.get("scholarship_id"),
            ), 409
        try:
            decrypt_bank_details(application["bank_details_encrypted"])
            application["payout_amount"] = normalize_distributed_amount(payout_amount)
        except (RuntimeError, ValueError) as error:
            current_app.logger.exception(
                "Application %s cannot be approved for finance review",
                application_id,
            )
            return jsonify(error="Encrypted bank details or the fixed scholarship amount are invalid or unavailable"), 409

    if "distributed_amount" in data:
        return jsonify(error="Fund distribution is recorded only by the finance workflow"), 400

    rejection_reason = data.get("rejection_reason", application.get("rejection_reason"))
    if rejection_reason is not None and (
        not isinstance(rejection_reason, str) or len(rejection_reason.strip()) > 2000
    ):
        return jsonify(error="rejection_reason must be at most 2000 characters or null"), 400
    rejection_reason = rejection_reason.strip() if rejection_reason else None
    if status == "rejected" and not rejection_reason:
        return jsonify(error="A rejection reason is required"), 400
    admin_note = data.get("admin_note", application.get("admin_note", ""))
    if not isinstance(admin_note, str) or len(admin_note.strip()) > 2000:
        return jsonify(error="admin_note must be at most 2000 characters"), 400
    admin_note = admin_note.strip()
    if status == "correction_required" and not admin_note:
        return jsonify(error="A note is required when requesting corrections"), 400

    now = datetime.now(timezone.utc)
    application["status"] = status
    application["rejection_reason"] = rejection_reason
    application["admin_note"] = admin_note
    application["reviewed_by"] = g.current_user["email"]
    application["updated_at"] = now
    if status == "correction_required":
        application["correction_requested_by"] = "admin"
    elif status != previous_status:
        application.pop("correction_requested_by", None)
    if status != previous_status:
        application.setdefault("status_history", []).append(
            {"status": status, "at": now.isoformat(), "actor": g.current_user["email"], "role": "admin"}
        )
    database.applications.replace_one({"id": application_id}, application)

    student = database.users.find_one({"user_id": application.get("user_id")})
    email_status = None
    if student and student.get("email") and status != previous_status:
        body = (
            f"Your application for {application['scholarship_title']} is now "
            f"{status.replace('_', ' ')}."
        )
        if status == "approved":
            body += (
                "\nFund distribution is pending. This portal records the status; "
                "it does not transfer funds."
            )
        elif status == "rejected" and rejection_reason:
            body += f"\nReason: {rejection_reason}"
        elif status == "correction_required":
            body += f"\nPlease update the following information and resubmit:\n{admin_note}"
        notification = enqueue_notification(
            database,
            f"application-status:{application_id}:{status}:{now.isoformat()}",
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
                "Could not immediately send application status email for %s",
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
    return jsonify(application=safe_application(application), email_status=email_status)


@applications_bp.get("/finance")
@finance_authenticated
def finance_queue():
    database = get_database()
    applications = [
        application
        for application in database.applications.find({"status": "approved"})
    ]
    items = []
    blocked_count = 0
    for application in applications:
        if not application.get("bank_details_encrypted") or not application.get("payout_amount"):
            blocked_count += 1
            continue
        try:
            bank_details = decrypt_bank_details(application["bank_details_encrypted"])
            payout_amount = normalize_distributed_amount(application["payout_amount"])
        except RuntimeError as error:
            current_app.logger.exception(
                "Could not decrypt bank details for finance item %s",
                application.get("id"),
            )
            return jsonify(error="Finance data is temporarily unavailable; check the bank encryption key"), 503
        except ValueError:
            blocked_count += 1
            continue
        items.append(
            {
                "id": application["id"],
                "scholarship_title": application["scholarship_title"],
                "payout_amount": payout_amount,
                "bank_account_number": bank_details["account_number"],
                "ifsc": bank_details["ifsc"],
            }
        )
    return jsonify(items=items, blocked_count=blocked_count, simulation_only=True)


@applications_bp.post("/finance/<application_id>/simulate-disbursement")
@finance_authenticated
def simulate_finance_disbursement(application_id):
    database = get_database()
    application = database.applications.find_one({"id": application_id})
    if application is None:
        return jsonify(error="Application was not found"), 404
    if application.get("status") != "approved":
        return jsonify(error="Only approved applications can enter the finance simulation"), 409
    if not application.get("bank_details_encrypted") or not application.get("payout_amount"):
        return jsonify(error="Encrypted bank details and an exact fixed amount are required"), 409
    try:
        decrypt_bank_details(application["bank_details_encrypted"])
        distributed_amount = normalize_distributed_amount(application["payout_amount"])
    except (RuntimeError, ValueError) as error:
        current_app.logger.exception(
            "Could not validate finance item %s",
            application_id,
        )
        return jsonify(error="Finance data is invalid or unavailable; contact the administrator"), 503

    student = database.users.find_one({"user_id": application.get("user_id")})
    if student is None or not student.get("email"):
        return jsonify(error="Student email is unavailable; simulated distribution was not recorded"), 409

    now = datetime.now(timezone.utc)
    application["status"] = "paid"
    application["distributed_amount"] = distributed_amount
    application["distribution_mode"] = "simulated"
    application["distributed_at"] = now
    application["distributed_by"] = g.current_user["email"]
    application["updated_at"] = now
    application.setdefault("status_history", []).append(
        {"status": "paid", "at": now.isoformat(), "mode": "simulated"}
    )
    database.applications.replace_one({"id": application_id}, application)
    notification = enqueue_notification(
        database,
        f"application-simulated-distribution:{application_id}",
        student["email"],
        f"Scholarship demo payment update: {application['scholarship_title']}",
        (
            f"A demo payment of ₹{distributed_amount} was recorded for your "
            f"{application['scholarship_title']} application.\n"
            "This is a simulation only. No money was transferred to your bank account."
        ),
    )
    try:
        dispatch_notification(notification)
    except (RuntimeError, OSError, smtplib.SMTPException) as error:
        notification["status"] = "failed"
        notification["attempts"] = notification.get("attempts", 0) + 1
        notification["last_error"] = str(error)[:500]
        current_app.logger.exception(
            "Could not immediately send simulated distribution email for %s",
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
    return jsonify(
        id=application_id,
        status="paid",
        distributed_amount=distributed_amount,
        distribution_mode="simulated",
        email_status=email_status,
    )


@applications_bp.get("/admin/<application_id>/documents/<document_id>")
@admin_authenticated
def download_admin_application_document(application_id, document_id):
    database = get_database()
    application = database.applications.find_one({"id": application_id})
    if application is None:
        return jsonify(error="Application was not found"), 404
    metadata = next(
        (item for item in application.get("documents", []) if item["id"] == document_id),
        None,
    )
    if metadata is None:
        return jsonify(error="Application document was not found"), 404
    stored = database.application_documents.find_one(
        {"id": document_id, "application_id": application_id}
    )
    if stored is None:
        return jsonify(error="Stored application document was not found"), 404
    try:
        raw = document_cipher().decrypt(stored["encrypted_data"])
    except RuntimeError as error:
        current_app.logger.error("Application document decryption is unavailable: %s", error)
        return jsonify(error="Secure document storage is unavailable. Contact the administrator."), 503
    except InvalidToken:
        current_app.logger.exception("Could not decrypt application document %s", document_id)
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


@applications_bp.get("/<application_id>/timeline")
@authenticated
def application_timeline(application_id):
    application = get_database().applications.find_one(
        {"id": application_id, "user_id": g.current_user["user_id"]}
    )
    if application is None:
        return jsonify(error="Application was not found"), 404
    history = application.get("status_history", [])
    return jsonify(
        application_id=application_id,
        current_status=application["status"],
        timeline=[
            {
                **stage,
                "guidance": STAGE_GUIDANCE[stage["status"]],
            }
            for stage in history
        ],
        payment_guidance=(
            "Approved applications are awaiting fund distribution. An administrator updates this tracker after the funds are disbursed; this portal does not transfer money."
        ),
    )


@applications_bp.post("/documents/check")
@authenticated
def check_document_upload():
    uploaded = request.files.get("file")
    if uploaded is None or not uploaded.filename:
        return jsonify(error="Choose a PDF, JPG, or PNG file to check"), 400
    raw = uploaded.stream.read(MAX_DOCUMENT_BYTES + 1)
    if len(raw) > MAX_DOCUMENT_BYTES:
        return jsonify(error="File is larger than the 8 MB upload limit"), 413
    if not raw:
        return jsonify(error="The uploaded file is empty"), 400

    if raw.startswith(b"%PDF-"):
        return jsonify(
            valid=True,
            file_type="application/pdf",
            size_bytes=len(raw),
            blurry=False,
            stored=False,
            guidance="PDF passed the format and size checks. It was not stored.",
            processed_file_base64=base64.b64encode(raw).decode("ascii"),
        )

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            image = Image.open(io.BytesIO(raw))
            if image.format not in ALLOWED_IMAGE_FORMATS:
                return jsonify(error="Only JPG, JPEG, PNG, and PDF files are allowed"), 415
            original_format = image.format
            width, height = image.size
            if width < 100 or height < 100:
                return jsonify(error="Image is too small to read; upload a clearer scan"), 400
            if width * height > MAX_IMAGE_PIXELS:
                return jsonify(error="Image dimensions are too large to process safely"), 413
            image.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        return jsonify(error="The image is invalid, damaged, or too large to process"), 400

    grayscale = image.convert("L")
    edge_image = grayscale.filter(ImageFilter.FIND_EDGES)
    edge_margin_x = max(1, width // 20)
    edge_margin_y = max(1, height // 20)
    interior_edges = edge_image.crop(
        (
            edge_margin_x,
            edge_margin_y,
            width - edge_margin_x,
            height - edge_margin_y,
        )
    )
    blurry = Stat(interior_edges).stddev[0] < 12
    resized = width > 2000 or height > 2000
    image.thumbnail((2000, 2000), Image.Resampling.LANCZOS)
    output = io.BytesIO()
    if original_format == "PNG":
        image.save(output, format="PNG", optimize=True)
        processed_type = "image/png"
    else:
        image.convert("RGB").save(output, format="JPEG", quality=82, optimize=True)
        processed_type = "image/jpeg"
    processed = output.getvalue()
    if len(processed) >= len(raw) and not resized:
        processed = raw
        processed_type = "image/jpeg" if original_format == "JPEG" else "image/png"
    return jsonify(
        valid=not blurry,
        file_type=processed_type,
        original_size_bytes=len(raw),
        processed_size_bytes=len(processed),
        dimensions={"width": image.width, "height": image.height},
        blurry=blurry,
        stored=False,
        guidance=(
            "Image appears blurry; take a clear photo in good light and upload again."
            if blurry
            else "Image passed the checks and was resized/compressed. It was not stored."
        ),
        processed_file_base64=base64.b64encode(processed).decode("ascii"),
    )


@applications_bp.get("/documents/upload-guide")
def upload_error_guide():
    return jsonify(
        allowed_types=["application/pdf", "image/jpeg", "image/png"],
        maximum_size_bytes=MAX_DOCUMENT_BYTES,
        errors=[
            {
                "code": "unsupported_type",
                "message": "Use PDF, JPG, or PNG; rename nahi, file ko supported format mein export karein.",
            },
            {
                "code": "too_large",
                "message": "Scan ko crop karein ya lower resolution par export karein; checker images compress bhi karta hai.",
            },
            {
                "code": "blurry",
                "message": "Document ko flat surface par, achhi roshni mein, poora frame karke dobara capture karein.",
            },
            {
                "code": "upload_failed",
                "message": "Internet connection check karke retry karein. This checker does not retain uploaded files.",
            },
        ],
    )
