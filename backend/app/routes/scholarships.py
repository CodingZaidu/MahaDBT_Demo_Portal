import re
from datetime import datetime, timezone
from functools import wraps
from uuid import uuid4

from flask import Blueprint, current_app, g, jsonify, request
from pymongo import ASCENDING, DESCENDING

from app.extensions import get_database
from app.routes.auth import authenticated
from app.services.scholarships import CATEGORIES, LEVELS, normalize_scholarship


scholarships_bp = Blueprint("scholarships", __name__)
SORT_OPTIONS = {"deadline": ("deadline", ASCENDING), "updated": ("updated_at", DESCENDING)}


def ensure_indexes(database):
    if current_app.extensions.get("scholarship_indexes_ready"):
        return
    database.scholarships.create_index("id", unique=True)
    database.scholarships.create_index([("status", ASCENDING), ("education_level", ASCENDING)])
    database.scholarships.create_index("categories")
    database.scholarships.create_index("deadline")
    current_app.extensions["scholarship_indexes_ready"] = True


def admin_only(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        allowed_emails = {
            email.strip().casefold()
            for email in current_app.config["ADMIN_EMAILS"]
            if isinstance(email, str) and email.strip()
        }
        finance_emails = {
            email.strip().casefold()
            for email in current_app.config.get("FINANCE_ADMIN_EMAILS", [])
            if isinstance(email, str) and email.strip()
        }
        current_email = g.current_user["email"].casefold()
        if current_email not in allowed_emails or current_email in finance_emails:
            return jsonify(error="Administrator access is required"), 403
        return view(*args, **kwargs)

    return wrapped


def admin_authenticated(view):
    return authenticated(admin_only(view))


def public_scholarship(document):
    return {key: value for key, value in document.items() if key != "_id"}


def parse_pagination():
    try:
        page = int(request.args.get("page", "1"))
        per_page = int(request.args.get("per_page", "20"))
    except ValueError as error:
        raise ValueError("page and per_page must be integers") from error
    if page < 1 or not 1 <= per_page <= 100:
        raise ValueError("page must be at least 1 and per_page must be between 1 and 100")
    return page, per_page


def date_filter(field):
    value = request.args.get(field)
    if value is None:
        return None
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as error:
        raise ValueError(f"{field} must use YYYY-MM-DD format") from error
    if parsed.isoformat() != value:
        raise ValueError(f"{field} must use YYYY-MM-DD format")
    return value


@scholarships_bp.get("")
def list_scholarships():
    try:
        page, per_page = parse_pagination()
        query = {"status": "active"}

        level = request.args.get("level")
        if level:
            level = level.strip().lower()
            if level not in LEVELS:
                raise ValueError(f"level must be one of: {', '.join(sorted(LEVELS))}")
            query["education_level"] = level

        category = request.args.get("category")
        if category:
            category = category.strip().lower()
            if category not in CATEGORIES:
                raise ValueError("category must be a supported scholarship category")
            query["categories"] = category

        eligibility = request.args.get("eligibility")
        if eligibility:
            if len(eligibility.strip()) > 120:
                raise ValueError("eligibility filter must be at most 120 characters")
            eligibility_pattern = re.escape(eligibility.strip())
            query["$or"] = [
                {"eligibility_summary": {"$regex": eligibility_pattern, "$options": "i"}},
                {"eligibility.courses": {"$regex": eligibility_pattern, "$options": "i"}},
            ]

        deadline_before = date_filter("deadline_before")
        deadline_after = date_filter("deadline_after")
        if deadline_before or deadline_after:
            deadline_query = {}
            if deadline_before:
                deadline_query["$lte"] = deadline_before
            if deadline_after:
                deadline_query["$gte"] = deadline_after
            query["deadline"] = deadline_query

        search = request.args.get("q")
        if search:
            search = search.strip()
            if len(search) > 120:
                raise ValueError("q must be at most 120 characters")
            text_filter = [
                {field: {"$regex": re.escape(search), "$options": "i"}}
                for field in ("title", "provider", "description")
            ]
            if "$or" in query:
                query["$and"] = [{"$or": query.pop("$or")}, {"$or": text_filter}]
            else:
                query["$or"] = text_filter

        sort = request.args.get("sort", "deadline")
        if sort not in SORT_OPTIONS:
            raise ValueError("sort must be deadline or updated")
        sort_field, sort_direction = SORT_OPTIONS[sort]
    except ValueError as error:
        return jsonify(error=str(error)), 400

    database = get_database()
    ensure_indexes(database)
    total = database.scholarships.count_documents(query)
    cursor = (
        database.scholarships.find(query)
        .sort(sort_field, sort_direction)
        .skip((page - 1) * per_page)
        .limit(per_page)
    )
    items = [public_scholarship(document) for document in cursor]
    return jsonify(
        items=items,
        pagination={
            "page": page,
            "per_page": per_page,
            "total": total,
            "pages": (total + per_page - 1) // per_page,
        },
    )


@scholarships_bp.get("/<scholarship_id>")
def get_scholarship(scholarship_id):
    database = get_database()
    ensure_indexes(database)
    document = database.scholarships.find_one({"id": scholarship_id, "status": "active"})
    if document is None:
        return jsonify(error="Scholarship was not found"), 404
    return jsonify(scholarship=public_scholarship(document))


@scholarships_bp.post("")
@admin_authenticated
def create_scholarship():
    try:
        scholarship = normalize_scholarship(request.get_json(silent=True))
    except ValueError as error:
        return jsonify(error=str(error)), 400

    now = datetime.now(timezone.utc)
    scholarship.update(
        id=str(uuid4()),
        created_at=now,
        updated_at=now,
        created_by=g.current_user["user_id"],
    )
    database = get_database()
    ensure_indexes(database)
    database.scholarships.insert_one(scholarship)
    return jsonify(scholarship=public_scholarship(scholarship)), 201


@scholarships_bp.patch("/<scholarship_id>")
@admin_authenticated
def update_scholarship(scholarship_id):
    database = get_database()
    ensure_indexes(database)
    existing = database.scholarships.find_one({"id": scholarship_id})
    if existing is None:
        return jsonify(error="Scholarship was not found"), 404
    try:
        scholarship = normalize_scholarship(request.get_json(silent=True), existing=existing)
    except ValueError as error:
        return jsonify(error=str(error)), 400

    scholarship.pop("verified_at", None)
    scholarship.pop("verified_by", None)
    scholarship["updated_at"] = datetime.now(timezone.utc)
    database.scholarships.replace_one({"id": scholarship_id}, scholarship)
    return jsonify(scholarship=public_scholarship(scholarship))


@scholarships_bp.delete("/<scholarship_id>")
@admin_authenticated
def archive_scholarship(scholarship_id):
    database = get_database()
    ensure_indexes(database)
    result = database.scholarships.update_one(
        {"id": scholarship_id},
        {"$set": {"status": "inactive", "updated_at": datetime.now(timezone.utc)}},
    )
    if result.matched_count == 0:
        return jsonify(error="Scholarship was not found"), 404
    return jsonify(message="Scholarship archived")


@scholarships_bp.post("/<scholarship_id>/verification")
@admin_authenticated
def verify_scholarship_source(scholarship_id):
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or set(body) != {"verified"} or body.get("verified") is not True:
        return jsonify(error="Set verified to true after checking the scheme details against official guidelines"), 400
    database = get_database()
    ensure_indexes(database)
    scholarship = database.scholarships.find_one({"id": scholarship_id})
    if scholarship is None:
        return jsonify(error="Scholarship was not found"), 404
    scholarship["verified_at"] = datetime.now(timezone.utc)
    scholarship["verified_by"] = g.current_user["user_id"]
    scholarship["updated_at"] = scholarship["verified_at"]
    database.scholarships.replace_one({"id": scholarship_id}, scholarship)
    return jsonify(
        message="Administrator review recorded",
        scholarship_id=scholarship_id,
        verified_at=scholarship["verified_at"],
        verified_by=scholarship["verified_by"],
    )


@scholarships_bp.get("/admin")
@admin_authenticated
def list_all_scholarships():
    try:
        page, per_page = parse_pagination()
    except ValueError as error:
        return jsonify(error=str(error)), 400
    database = get_database()
    ensure_indexes(database)
    total = database.scholarships.count_documents({})
    cursor = (
        database.scholarships.find({})
        .sort("updated_at", DESCENDING)
        .skip((page - 1) * per_page)
        .limit(per_page)
    )
    return jsonify(
        items=[public_scholarship(document) for document in cursor],
        pagination={
            "page": page,
            "per_page": per_page,
            "total": total,
            "pages": (total + per_page - 1) // per_page,
        },
    )
