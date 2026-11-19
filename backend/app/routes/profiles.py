from datetime import datetime, timezone

from flask import Blueprint, g, jsonify, request

from app.extensions import get_database
from app.routes.auth import authenticated
from app.routes.scholarships import public_scholarship
from app.services.profiles import assess_eligibility, normalize_profile


profiles_bp = Blueprint("profiles", __name__)


@profiles_bp.get("")
@authenticated
def get_profile():
    profile = g.current_user.get("profile", {})
    return jsonify(profile=profile)


@profiles_bp.patch("")
@authenticated
def update_profile():
    try:
        existing = g.current_user.get("profile", {})
        profile = normalize_profile(request.get_json(silent=True), existing=existing)
    except ValueError as error:
        return jsonify(error=str(error)), 400
    profile["updated_at"] = datetime.now(timezone.utc)
    get_database().users.update_one(
        {"user_id": g.current_user["user_id"]},
        {"$set": {"profile": profile}},
    )
    return jsonify(profile=profile)


@profiles_bp.post("/eligibility")
def check_eligibility():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="Request body must be a JSON object"), 400
    scholarship_id = data.get("scholarship_id")
    if not isinstance(scholarship_id, str) or not scholarship_id.strip():
        return jsonify(error="scholarship_id is required"), 400
    try:
        profile = normalize_profile(data.get("profile", {}))
    except ValueError as error:
        return jsonify(error=str(error)), 400
    scholarship = get_database().scholarships.find_one(
        {"id": scholarship_id, "status": "active"}
    )
    if scholarship is None:
        return jsonify(error="Scholarship was not found"), 404
    result = assess_eligibility(scholarship, profile)
    return jsonify(
        scholarship_id=scholarship_id,
        result=result,
        disclaimer="This is a guidance estimate. Confirm all criteria in the official scheme guidelines.",
    )


@profiles_bp.get("/recommendations")
@authenticated
def recommendations():
    profile = g.current_user.get("profile", {})
    missing = [
        field
        for field in ("category", "education_level", "maharashtra_domicile")
        if profile.get(field) is None
    ]
    if missing:
        return jsonify(
            recommendations=[],
            missing_profile_fields=missing,
            notice="Complete more of your profile to get personalized recommendations.",
        )

    database = get_database()
    candidates = []
    for scholarship in database.scholarships.find({"status": "active"}):
        result = assess_eligibility(scholarship, profile)
        if result["status"] == "not_eligible":
            continue
        score = len(result["matched_criteria"]) * 10 - len(result["missing_information"]) * 2
        candidates.append(
            {
                "scholarship": public_scholarship(scholarship),
                "eligibility": result,
                "match_score": max(0, min(score, 100)),
            }
        )
    candidates.sort(
        key=lambda item: (
            item["eligibility"]["status"] != "eligible",
            -item["match_score"],
            item["scholarship"].get("deadline") or "9999-12-31",
        )
    )
    try:
        limit = int(request.args.get("limit", "10"))
    except ValueError:
        return jsonify(error="limit must be an integer"), 400
    if not 1 <= limit <= 50:
        return jsonify(error="limit must be between 1 and 50"), 400
    return jsonify(
        recommendations=candidates[:limit],
        notice="Recommendations are guidance only; verify eligibility using official scheme guidelines.",
    )


@profiles_bp.get("/compare")
def compare_scholarships():
    ids = request.args.getlist("id")
    if not 2 <= len(ids) <= 3 or len(set(ids)) != len(ids):
        return jsonify(error="Provide 2 or 3 distinct id query parameters"), 400
    database = get_database()
    scholarships = []
    for scholarship_id in ids:
        scholarship = database.scholarships.find_one(
            {"id": scholarship_id, "status": "active"}
        )
        if scholarship is None:
            return jsonify(error=f"Scholarship {scholarship_id} was not found"), 404
        scholarships.append(public_scholarship(scholarship))
    return jsonify(
        comparison=[
            {
                "id": item["id"],
                "title": item["title"],
                "provider": item["provider"],
                "education_level": item["education_level"],
                "categories": item["categories"],
                "eligibility_summary": item["eligibility_summary"],
                "eligibility": item["eligibility"],
                "award_amount": item.get("award_amount"),
                "deadline": item.get("deadline"),
                "documents": item.get("documents", []),
                "official_url": item["official_url"],
            }
            for item in scholarships
        ]
    )
