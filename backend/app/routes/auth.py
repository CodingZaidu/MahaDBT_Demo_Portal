import re
import smtplib
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import Blueprint, current_app, g, jsonify, request
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import get_database
from app.services.auth import (
    generate_otp,
    make_auth_token,
    normalize_email,
    normalize_registration,
    password_matches,
    read_auth_token,
    send_otp_email,
    send_password_reset_otp_email,
    send_registration_email,
)


auth_bp = Blueprint("auth", __name__)


def ensure_indexes(database):
    if current_app.extensions.get("auth_indexes_ready"):
        return
    database.users.create_index("email", unique=True)
    database.users.create_index("user_id", unique=True)
    database.pending_users.create_index("email", unique=True)
    database.pending_users.create_index("expires_at", expireAfterSeconds=0)
    database.password_reset_requests.create_index("email", unique=True)
    database.password_reset_requests.create_index("expires_at", expireAfterSeconds=0)
    current_app.extensions["auth_indexes_ready"] = True


def json_body():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ValueError("Request body must be a JSON object")
    return body


def public_user(user):
    public = {
        "user_id": user["user_id"],
        "full_name": user["full_name"],
        "email": user["email"],
        "mobile": user.get("mobile", ""),
        "date_of_birth": user.get("date_of_birth", ""),
        "gender": user.get("gender", ""),
        "role": user.get("role", "student"),
    }
    if user.get("college_id"):
        public["college_id"] = user["college_id"]
        public["college_name"] = user.get("college_name", "")
    return public


def authenticated(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        scheme, _, token = header.partition(" ")
        try:
            user_id = read_auth_token(token) if scheme.lower() == "bearer" and token else None
        except RuntimeError:
            current_app.logger.exception("Authentication token secret is not configured")
            return jsonify(error="Authentication is temporarily unavailable"), 503
        if not user_id:
            return jsonify(error="A valid bearer token is required"), 401
        user = get_database().users.find_one({"user_id": user_id})
        if user is None:
            return jsonify(error="Account was not found"), 401
        g.current_user = user
        return view(*args, **kwargs)

    return wrapped


@auth_bp.post("/register")
def register():
    try:
        user_data = normalize_registration(json_body())
    except ValueError as error:
        return jsonify(error=str(error)), 400
    except RuntimeError:
        current_app.logger.exception("Aadhaar encryption is unavailable for registration")
        return jsonify(
            error="Optional Aadhaar encryption is not configured; remove Aadhaar or contact the administrator"
        ), 503

    database = get_database()
    ensure_indexes(database)
    if database.users.find_one({"email": user_data["email"]}):
        return jsonify(error="An account with this email already exists"), 409

    now = datetime.now(timezone.utc)
    database.pending_users.delete_one(
        {"email": user_data["email"], "expires_at": {"$lte": now}}
    )
    otp = generate_otp()
    pending_user = {
        **user_data,
        "otp_hash": generate_password_hash(otp),
        "otp_attempts": 0,
        "created_at": now,
        "consented_at": now,
        "expires_at": now + timedelta(seconds=current_app.config["OTP_TTL_SECONDS"]),
    }
    if "aadhaar_encrypted" in user_data:
        pending_user["aadhaar_consented_at"] = now
    try:
        database.pending_users.insert_one(pending_user)
    except DuplicateKeyError:
        return jsonify(error="A verification code was already sent to this email"), 409

    try:
        send_otp_email(user_data["email"], otp)
    except (RuntimeError, OSError, smtplib.SMTPException):
        current_app.logger.exception("Could not send registration verification email")
        database.pending_users.delete_one({"email": user_data["email"]})
        return jsonify(error="Could not send the verification email; please try again later"), 503

    return jsonify(
        message="Verification code sent. It expires in 10 minutes.",
        email=user_data["email"],
        otp_expires_in_seconds=current_app.config["OTP_TTL_SECONDS"],
        attempts_allowed=current_app.config["OTP_MAX_ATTEMPTS"],
    ), 202


@auth_bp.post("/verify-email")
def verify_email():
    try:
        body = json_body()
        email = normalize_email(body.get("email"))
        otp = body.get("otp")
        if not isinstance(otp, str) or len(otp) != 6 or not otp.isdigit():
            raise ValueError("OTP must be a 6-digit code")
    except ValueError as error:
        return jsonify(error=str(error)), 400

    database = get_database()
    ensure_indexes(database)
    now = datetime.now(timezone.utc)
    pending_user = database.pending_users.find_one_and_update(
        {
            "email": email,
            "expires_at": {"$gt": now},
            "otp_attempts": {"$lt": current_app.config["OTP_MAX_ATTEMPTS"]},
        },
        {"$inc": {"otp_attempts": 1}},
        return_document=ReturnDocument.AFTER,
    )
    if pending_user is None:
        pending_user = database.pending_users.find_one({"email": email})
        if pending_user is None:
            return jsonify(error="No active verification request was found"), 404
        if pending_user["expires_at"] <= now:
            database.pending_users.delete_one({"email": email})
            return jsonify(error="Verification code expired; please register again"), 410
        return jsonify(error="Maximum verification attempts reached; please register again"), 429

    if not check_password_hash(pending_user["otp_hash"], otp):
        attempts_left = max(
            0,
            current_app.config["OTP_MAX_ATTEMPTS"] - pending_user["otp_attempts"],
        )
        if attempts_left == 0:
            database.pending_users.delete_one({"email": email})
            return jsonify(error="Maximum verification attempts reached; please register again"), 429
        return jsonify(error="Incorrect verification code", attempts_left=attempts_left), 400

    sequence_name = f"student_id_{now.year}"
    counter = database.counters.find_one_and_update(
        {"_id": sequence_name},
        {"$inc": {"value": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    user_id = f"SS-{now.year}-{counter['value']:06d}"
    user = {
        key: value
        for key, value in pending_user.items()
        if key not in {"_id", "otp_hash", "otp_attempts", "expires_at"}
    }
    user.update(user_id=user_id, email_verified=True, created_at=now)
    try:
        database.users.insert_one(user)
    except DuplicateKeyError:
        database.pending_users.delete_one({"email": email})
        return jsonify(error="An account with this email already exists"), 409
    database.pending_users.delete_one({"email": email})

    try:
        send_registration_email(email, user_id)
    except (RuntimeError, OSError, smtplib.SMTPException):
        current_app.logger.exception("Account verified but confirmation email could not be sent")
        return jsonify(
            message="Registered successfully, but the confirmation email could not be sent.",
            email_notification="failed",
            user=public_user(user),
        ), 201

    return jsonify(
        message="Registered successfully. Use the password you chose during registration to log in.",
        email_notification="sent",
        user=public_user(user),
    ), 201


@auth_bp.post("/forgot-password")
def forgot_password():
    try:
        body = json_body()
        email = normalize_email(body.get("email"))
    except ValueError as error:
        return jsonify(error=str(error)), 400

    database = get_database()
    ensure_indexes(database)
    user = database.users.find_one({"email": email})
    if user is None:
        return jsonify(
            message="If an account exists for this email, a password reset code has been sent.",
            otp_expires_in_seconds=current_app.config["OTP_TTL_SECONDS"],
        ), 202

    now = datetime.now(timezone.utc)
    otp = generate_otp()
    database.password_reset_requests.delete_one({"email": email})
    try:
        database.password_reset_requests.insert_one(
            {
                "email": email,
                "otp_hash": generate_password_hash(otp),
                "otp_attempts": 0,
                "created_at": now,
                "expires_at": now + timedelta(seconds=current_app.config["OTP_TTL_SECONDS"]),
            }
        )
    except DuplicateKeyError:
        return jsonify(error="A password reset request is already being processed"), 409

    try:
        send_password_reset_otp_email(email, otp)
    except (RuntimeError, OSError, smtplib.SMTPException):
        current_app.logger.exception("Could not send password reset verification email")
        database.password_reset_requests.delete_one({"email": email})
        return jsonify(error="Could not send the verification email; please try again later"), 503

    return jsonify(
        message="If an account exists for this email, a password reset code has been sent.",
        otp_expires_in_seconds=current_app.config["OTP_TTL_SECONDS"],
    ), 202


@auth_bp.post("/reset-password")
def reset_password():
    try:
        body = json_body()
        email = normalize_email(body.get("email"))
        otp = body.get("otp")
        password = body.get("password")
        confirm_password = body.get("confirm_password")
        if not isinstance(otp, str) or len(otp) != 6 or not otp.isdigit():
            raise ValueError("OTP must be a 6-digit code")
        if not isinstance(password, str) or not 10 <= len(password) <= 128:
            raise ValueError("Password must be between 10 and 128 characters")
        if password != confirm_password:
            raise ValueError("Password and confirm password do not match")
    except ValueError as error:
        return jsonify(error=str(error)), 400

    database = get_database()
    ensure_indexes(database)
    now = datetime.now(timezone.utc)
    reset_request = database.password_reset_requests.find_one_and_update(
        {
            "email": email,
            "expires_at": {"$gt": now},
            "otp_attempts": {"$lt": current_app.config["OTP_MAX_ATTEMPTS"]},
        },
        {"$inc": {"otp_attempts": 1}},
        return_document=ReturnDocument.AFTER,
    )
    if reset_request is None:
        reset_request = database.password_reset_requests.find_one({"email": email})
        if reset_request is None:
            return jsonify(error="No active password reset request was found"), 404
        if reset_request["expires_at"] <= now:
            database.password_reset_requests.delete_one({"email": email})
            return jsonify(error="Verification code expired; request a new one"), 410
        return jsonify(error="Maximum verification attempts reached; request a new code"), 429

    if not check_password_hash(reset_request["otp_hash"], otp):
        attempts_left = max(
            0,
            current_app.config["OTP_MAX_ATTEMPTS"] - reset_request["otp_attempts"],
        )
        if attempts_left == 0:
            database.password_reset_requests.delete_one({"email": email})
            return jsonify(error="Maximum verification attempts reached; request a new code"), 429
        return jsonify(
            error="Incorrect verification code",
            attempts_left=attempts_left,
        ), 400

    result = database.users.update_one(
        {"email": email},
        {"$set": {"password_hash": generate_password_hash(password)}},
    )
    database.password_reset_requests.delete_one({"email": email})
    if result.matched_count == 0:
        return jsonify(error="Account was not found; request a new code"), 404
    return jsonify(message="Password reset successful. You can now sign in.")


@auth_bp.post("/login")
def login():
    try:
        body = json_body()
        identifier = body.get("identifier", body.get("email"))
        if not isinstance(identifier, str) or not identifier.strip():
            raise ValueError("Email address or student ID is required")
        identifier = identifier.strip()
        password = body.get("password")
        if not isinstance(password, str) or not password:
            raise ValueError("Password is required")
    except ValueError as error:
        return jsonify(error=str(error)), 400

    if re.fullmatch(r"(?:SS-\d{4}-\d{6}|CV-[A-F0-9]{12})", identifier, flags=re.IGNORECASE):
        user = get_database().users.find_one({"user_id": identifier.upper()})
    else:
        try:
            email = normalize_email(identifier)
        except ValueError as error:
            return jsonify(error=str(error)), 400
        user = get_database().users.find_one({"email": email})
    if user is None or not password_matches(user["password_hash"], password):
        return jsonify(error="Email or password is incorrect"), 401

    try:
        token = make_auth_token(user["user_id"])
    except RuntimeError:
        current_app.logger.exception("Authentication token secret is not configured")
        return jsonify(error="Login is temporarily unavailable"), 503
    return jsonify(
        message="Login successful",
        access_token=token,
        token_type="Bearer",
        expires_in_seconds=current_app.config["AUTH_TOKEN_TTL_SECONDS"],
        user=public_user(user),
    )


@auth_bp.get("/me")
@authenticated
def current_account():
    email = g.current_user["email"].casefold()
    admin_emails = {
        value.strip().casefold()
        for value in current_app.config.get("ADMIN_EMAILS", [])
        if isinstance(value, str) and value.strip()
    }
    finance_emails = {
        value.strip().casefold()
        for value in current_app.config.get("FINANCE_ADMIN_EMAILS", [])
        if isinstance(value, str) and value.strip()
    }
    return jsonify(
        user=public_user(g.current_user),
        permissions={
            "admin": email in admin_emails,
            "finance": email in finance_emails,
        },
    )
