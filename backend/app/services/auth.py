import re
import secrets
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage

from cryptography.fernet import Fernet
from email_validator import EmailNotValidError, validate_email
from flask import current_app
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash


GENDERS = {"female", "male", "other", "prefer_not_to_say"}


def encrypt_aadhaar(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{12}", value):
        raise ValueError("Aadhaar number must contain exactly 12 digits")
    key = current_app.config.get("AADHAAR_ENCRYPTION_KEY")
    if not isinstance(key, str) or not key:
        raise RuntimeError("AADHAAR_ENCRYPTION_KEY is not configured")
    try:
        cipher = Fernet(key.encode("ascii"))
    except (UnicodeEncodeError, ValueError) as error:
        raise RuntimeError("AADHAAR_ENCRYPTION_KEY is invalid") from error
    return cipher.encrypt(value.encode("ascii")).decode("ascii")


def normalize_registration(data):
    if not isinstance(data, dict):
        raise ValueError("Request body must be a JSON object")

    full_name = data.get("full_name")
    if not isinstance(full_name, str):
        raise ValueError("Full name must be between 2 and 120 characters")
    full_name = full_name.strip()
    if not 2 <= len(full_name) <= 120:
        raise ValueError("Full name must be between 2 and 120 characters")

    email = data.get("email")
    if not isinstance(email, str):
        raise ValueError("A valid email address is required")
    try:
        email = validate_email(email.strip(), check_deliverability=False).normalized
    except EmailNotValidError as error:
        raise ValueError("A valid email address is required") from error

    mobile = data.get("mobile")
    if not isinstance(mobile, str) or not re.fullmatch(r"\+?[0-9]{10,15}", mobile.strip()):
        raise ValueError("Mobile number must contain 10 to 15 digits")

    password = data.get("password")
    if not isinstance(password, str) or len(password) < 10 or len(password) > 128:
        raise ValueError("Password must be between 10 and 128 characters")
    if password != data.get("confirm_password"):
        raise ValueError("Password and confirm password do not match")

    date_of_birth = data.get("date_of_birth")
    if not isinstance(date_of_birth, str):
        raise ValueError("Date of birth must use YYYY-MM-DD format")
    try:
        parsed_dob = datetime.strptime(date_of_birth, "%Y-%m-%d").date()
    except ValueError as error:
        raise ValueError("Date of birth must use YYYY-MM-DD format") from error
    if parsed_dob.isoformat() != date_of_birth or parsed_dob > datetime.now(timezone.utc).date():
        raise ValueError("Date of birth must be a valid date that is not in the future")

    gender = data.get("gender")
    if not isinstance(gender, str) or gender not in GENDERS:
        raise ValueError("Gender must be female, male, other, or prefer_not_to_say")
    if data.get("consent") is not True:
        raise ValueError("Terms and privacy consent are required")

    user_data = {
        "full_name": full_name,
        "email": email,
        "mobile": mobile.strip(),
        "password_hash": generate_password_hash(password),
        "date_of_birth": date_of_birth,
        "gender": gender,
    }
    aadhaar = data.get("aadhaar")
    if aadhaar not in (None, ""):
        if data.get("aadhaar_consent") is not True:
            raise ValueError("Aadhaar consent is required when providing an Aadhaar number")
        user_data["aadhaar_encrypted"] = encrypt_aadhaar(aadhaar)
    return user_data


def normalize_email(value):
    if not isinstance(value, str):
        raise ValueError("A valid email address is required")
    try:
        return validate_email(value.strip(), check_deliverability=False).normalized
    except EmailNotValidError as error:
        raise ValueError("A valid email address is required") from error


def generate_otp():
    return f"{secrets.randbelow(1_000_000):06d}"


def make_auth_token(user_id):
    secret_key = current_app.config.get("SECRET_KEY")
    if not secret_key:
        raise RuntimeError("SECRET_KEY is not configured")
    serializer = URLSafeTimedSerializer(secret_key, salt="student-auth")
    return serializer.dumps({"user_id": user_id})


def read_auth_token(token):
    secret_key = current_app.config.get("SECRET_KEY")
    if not secret_key:
        raise RuntimeError("SECRET_KEY is not configured")
    serializer = URLSafeTimedSerializer(secret_key, salt="student-auth")
    try:
        payload = serializer.loads(
            token,
            max_age=current_app.config["AUTH_TOKEN_TTL_SECONDS"],
        )
    except (BadSignature, SignatureExpired):
        return None
    if not isinstance(payload, dict):
        return None
    user_id = payload.get("user_id")
    return user_id if isinstance(user_id, str) else None


def send_otp_email(email, otp):
    send_email(
        email,
        "Verify your Scholarship Support account",
        (
            f"Your email verification code is {otp}.\n\n"
            "This code expires in 10 minutes. Do not share it with anyone."
        ),
    )


def send_password_reset_otp_email(email, otp):
    send_email(
        email,
        "Reset your Scholarship Support password",
        (
            f"Your password reset code is {otp}.\n\n"
            "This code expires in 10 minutes and can be used once. "
            "Do not share it with anyone. If you did not request a password reset, "
            "you can ignore this email."
        ),
    )


def send_registration_email(email, user_id):
    send_email(
        email,
        "Scholarship Support registration successful",
        (
            f"Your account has been verified successfully.\n"
            f"Your unique student ID is {user_id}.\n\n"
            "Use the same password you created during registration to log in. "
            "For your security, we never send or store your password in plain text."
        ),
    )


def send_email(recipient, subject, body):
    host = current_app.config.get("SMTP_HOST")
    username = current_app.config.get("SMTP_USERNAME")
    password = current_app.config.get("SMTP_PASSWORD")
    sender = current_app.config.get("SMTP_FROM") or username
    if not all((host, username, password, sender)):
        raise RuntimeError("Email delivery is not configured")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = recipient
    message.set_content(body)

    with smtplib.SMTP(host, current_app.config["SMTP_PORT"], timeout=10) as server:
        server.ehlo()
        if current_app.config["SMTP_USE_TLS"]:
            server.starttls()
            server.ehlo()
        server.login(username, password)
        refused = server.send_message(message)
        if refused:
            raise smtplib.SMTPRecipientsRefused(refused)


def password_matches(password_hash, password):
    return check_password_hash(password_hash, password)
