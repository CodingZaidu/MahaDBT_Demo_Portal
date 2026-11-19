import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify
from pymongo.errors import PyMongoError

from app.routes.auth import auth_bp
from app.routes.applications import applications_bp
from app.routes.admin import admin_bp, survey_bp
from app.routes.profiles import profiles_bp
from app.routes.scholarships import scholarships_bp
from app.routes.support import support_bp
from app.routes.colleges import colleges_bp


def create_app(config=None):
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.getenv("SECRET_KEY"),
        AADHAAR_ENCRYPTION_KEY=os.getenv("AADHAAR_ENCRYPTION_KEY"),
        DOCUMENT_ENCRYPTION_KEY=os.getenv("DOCUMENT_ENCRYPTION_KEY"),
        BANK_DETAILS_ENCRYPTION_KEY=os.getenv("BANK_DETAILS_ENCRYPTION_KEY"),
        MONGO_URI=os.getenv("MONGO_URI", "mongodb://localhost:27017"),
        MONGO_DB_NAME=os.getenv("MONGO_DB_NAME", "scholarship_support"),
        SMTP_HOST=os.getenv("SMTP_HOST"),
        SMTP_PORT=int(os.getenv("SMTP_PORT", "587")),
        SMTP_USERNAME=os.getenv("SMTP_USERNAME"),
        SMTP_PASSWORD=os.getenv("SMTP_PASSWORD"),
        SMTP_FROM=os.getenv("SMTP_FROM"),
        SMTP_USE_TLS=os.getenv("SMTP_USE_TLS", "true").lower() == "true",
        OTP_TTL_SECONDS=600,
        OTP_MAX_ATTEMPTS=5,
        AUTH_TOKEN_TTL_SECONDS=86400,
        ADMIN_EMAILS=[
            email.strip()
            for email in os.getenv("ADMIN_EMAILS", "").split(",")
            if email.strip()
        ],
        FINANCE_ADMIN_EMAILS=[
            email.strip()
            for email in os.getenv("FINANCE_ADMIN_EMAILS", "").split(",")
            if email.strip()
        ],
        MAX_CONTENT_LENGTH=9 * 1024 * 1024,
    )
    if config:
        app.config.update(config)

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(applications_bp, url_prefix="/api/applications")
    app.register_blueprint(profiles_bp, url_prefix="/api/profile")
    app.register_blueprint(scholarships_bp, url_prefix="/api/scholarships")
    app.register_blueprint(support_bp, url_prefix="/api")
    app.register_blueprint(admin_bp, url_prefix="/api/admin")
    app.register_blueprint(survey_bp, url_prefix="/api/surveys")
    app.register_blueprint(colleges_bp, url_prefix="/api/colleges")

    @app.errorhandler(PyMongoError)
    def handle_database_error(error):
        app.logger.exception("Scholarship database request failed")
        return jsonify(error="Database is temporarily unavailable"), 503

    @app.route("/")
    def home():
        return {
            "message": "Scholarship Support API is running",
            "status": "success",
        }

    return app
