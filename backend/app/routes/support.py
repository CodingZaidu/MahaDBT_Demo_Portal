import re
from datetime import datetime, timezone
from urllib.parse import urlparse
from uuid import uuid4

from flask import Blueprint, current_app, g, jsonify, request
from pymongo.errors import DuplicateKeyError

from app.extensions import get_database
from app.routes.auth import authenticated
from app.routes.scholarships import admin_authenticated, ensure_indexes as ensure_scholarship_indexes


support_bp = Blueprint("support", __name__)
LANGUAGE_MESSAGES = {
    "en": {
        "no_verified_schemes": "There are no administrator-reviewed scholarships in the directory yet. Please check back later or contact support.",
        "no_match": "I could not find a matching administrator-reviewed scheme in the directory. Try different keywords or check the official portal.",
        "disclaimer": "Answers use scholarship records reviewed by an administrator. Always confirm current details on the official scheme website.",
    },
    "hi": {
        "no_verified_schemes": "सूची में अभी प्रशासक द्वारा जाँची गई छात्रवृत्तियाँ नहीं हैं। कृपया बाद में फिर देखें या सहायता टीम से संपर्क करें।",
        "no_match": "सूची में इस सवाल से मेल खाती प्रशासक द्वारा जाँची गई योजना नहीं मिली। दूसरे शब्दों से खोजें या आधिकारिक पोर्टल देखें।",
        "disclaimer": "जवाब प्रशासक द्वारा जाँचे गए छात्रवृत्ति रिकॉर्ड पर आधारित हैं। मौजूदा जानकारी आधिकारिक योजना वेबसाइट पर अवश्य जाँचें।",
    },
    "mr": {
        "no_verified_schemes": "यादीत सध्या प्रशासकाने तपासलेल्या शिष्यवृत्ती नाहीत. कृपया नंतर पुन्हा पहा किंवा मदत कक्षाशी संपर्क साधा.",
        "no_match": "या प्रश्नाशी जुळणारी प्रशासकाने तपासलेली योजना यादीत सापडली नाही. वेगळे शब्द वापरून पहा किंवा अधिकृत पोर्टल पहा.",
        "disclaimer": "उत्तरे प्रशासकाने तपासलेल्या शिष्यवृत्ती नोंदींवर आधारित आहेत. सध्याची माहिती अधिकृत योजना संकेतस्थळावर तपासा.",
    },
}
TUTORIAL_LANGUAGES = {"en", "hi", "mr"}
TICKET_STATUSES = {"open", "in_progress", "resolved", "closed"}
GRIEVANCE_STATUSES = {"received", "under_review", "resolved", "closed"}
REJECTION_GUIDANCE = [
    {
        "key": "income",
        "contains": ("income", "utpanna"),
        "reason": "Income certificate may be missing, expired, or outside the scheme limit.",
        "fix": "Check the certificate year, issuing authority and scheme income limit; ask the college or official helpline before resubmitting.",
    },
    {
        "key": "document",
        "contains": ("document", "upload", "certificate", "marksheet"),
        "reason": "A required document may be unreadable, incomplete, or inconsistent with the form.",
        "fix": "Compare each uploaded document with the official checklist and replace unclear or outdated copies.",
    },
    {
        "key": "eligibility",
        "contains": ("eligibility", "category", "percentage", "domicile"),
        "reason": "The recorded profile or course may not meet a scheme criterion.",
        "fix": "Read the official scheme criteria and contact the college scholarship desk if profile information needs correction.",
    },
    {
        "key": "bank",
        "contains": ("bank", "dbt", "payment", "aadhaar"),
        "reason": "Payment or DBT details may need attention.",
        "fix": "Check account status and linkage through the official portal or bank. Never share account numbers or OTPs in this support system.",
    },
]


def ensure_support_indexes(database):
    if current_app.extensions.get("support_indexes_ready"):
        return
    database.support_tickets.create_index("id", unique=True)
    database.grievances.create_index("id", unique=True)
    database.feedback.create_index(
        [("user_id", 1), ("scholarship_id", 1)], unique=True
    )
    database.tutorials.create_index("id", unique=True)
    current_app.extensions["support_indexes_ready"] = True


def language_for_request():
    language = request.args.get("lang") or request.headers.get("Accept-Language", "en")
    language = language.split(",")[0].split("-")[0].strip().lower()
    return language if language in TUTORIAL_LANGUAGES else "en"


def clean_document(document):
    return {key: value for key, value in document.items() if key != "_id"}


def new_tracking_id(prefix):
    return f"{prefix}-{datetime.now(timezone.utc).year}-{uuid4().hex[:10].upper()}"


@support_bp.get("/chat")
def verified_scholarship_chat():
    query = request.args.get("q", "").strip()
    if not query or len(query) > 500:
        return jsonify(error="q is required and must be at most 500 characters"), 400
    language = language_for_request()
    messages = LANGUAGE_MESSAGES[language]
    terms = {term.casefold() for term in re.findall(r"[\w]{3,}", query)}
    database = get_database()
    ensure_scholarship_indexes(database)
    verified_schemes = list(
        database.scholarships.find(
            {"status": "active", "verified_at": {"$exists": True}}
        )
    )
    if not verified_schemes:
        active_scheme_count = database.scholarships.count_documents({"status": "active"})
        return jsonify(
            language=language,
            answer=messages["no_verified_schemes"],
            sources=[],
            disclaimer=messages["disclaimer"],
            review_pending_count=active_scheme_count,
        )

    matches = []
    for scheme in verified_schemes:
        searchable = " ".join(
            [
                scheme.get("title", ""),
                scheme.get("description", ""),
                scheme.get("eligibility_summary", ""),
                " ".join(scheme.get("categories", [])),
                " ".join(scheme.get("eligibility", {}).get("courses", [])),
            ]
        ).casefold()
        score = sum(term in searchable for term in terms)
        if score:
            matches.append((score, scheme))
    matches.sort(key=lambda result: result[0], reverse=True)
    if not matches:
        general_scheme_question = bool(
            terms
            & {
                "scholarship", "scholarships", "scheme", "schemes", "apply",
                "application", "eligibility", "eligible", "student", "students",
                "available", "maharashtra", "yojana", "yojanas", "shishyavrutti",
            }
        )
        if general_scheme_question:
            matches = [(0, scheme) for scheme in verified_schemes]
        else:
            return jsonify(
                language=language,
                answer=messages["no_match"],
                sources=[],
                disclaimer=messages["disclaimer"],
            )

    selected = matches[:3]
    if language != "en":
        missing_translation = any(
            not {"title", "description", "eligibility_summary"}.issubset(
                scheme.get("translations", {}).get(language, {})
            )
            for _, scheme in selected
        )
        if missing_translation:
            message = (
                "Is yojana ki Hindi verified details abhi nahi hain. Official source par details dekhein."
                if language == "hi"
                else "Ya yojanechi Marathi verified mahiti sadhya upalabdh nahi. Adhikrut source paha."
            )
            return jsonify(
                language=language,
                answer=message,
                scheme_ids=[scheme["id"] for _, scheme in selected],
                sources=[scheme["official_url"] for _, scheme in selected if scheme.get("official_url")],
                disclaimer=messages["disclaimer"],
            )

    schemes = []
    for _, scheme in selected:
        translation = scheme.get("translations", {}).get(language, {})
        schemes.append(
            {
                "id": scheme["id"],
                "title": translation.get("title", scheme["title"]),
                "description": translation.get("description", scheme["description"]),
                "eligibility_summary": translation.get(
                    "eligibility_summary",
                    scheme["eligibility_summary"],
                ),
                "deadline": scheme.get("deadline"),
                "official_url": scheme.get("official_url"),
                "verified_at": scheme["verified_at"],
            }
        )
    return jsonify(
        language=language,
        answer=schemes,
        sources=[scheme["official_url"] for scheme in schemes if scheme["official_url"]],
        disclaimer=messages["disclaimer"],
    )


@support_bp.get("/guides/rejection")
def rejection_guide():
    reason = request.args.get("reason", "").strip().casefold()
    matched = [
        {"reason": item["reason"], "fix": item["fix"]}
        for item in REJECTION_GUIDANCE
        if any(word in reason for word in item["contains"])
    ]
    return jsonify(
        guidance=matched or [
            {
                "reason": "The reason needs to be checked against the official rejection notice.",
                "fix": "Use the official portal or college scholarship desk to clarify the notice. Reapply only if official rules allow it.",
            }
        ],
        notice="Guidance is general; the official rejection notice and scheme rules take precedence.",
    )


@support_bp.get("/guides/payment")
def payment_guide():
    return jsonify(
        stages=[
            {
                "stage": "application_submitted",
                "guidance": "Confirm submission status and save the official application ID.",
            },
            {
                "stage": "college_verification",
                "guidance": "Ask the college scholarship desk whether verification is pending or returned for correction.",
            },
            {
                "stage": "department_review",
                "guidance": "Check the official portal for scrutiny updates or a document query.",
            },
            {
                "stage": "sanctioned",
                "guidance": "Approval does not always mean payment has reached the bank; monitor the official portal.",
            },
            {
                "stage": "dbt_processing",
                "guidance": "If payment is delayed, check official DBT/bank guidance. Do not share bank details or OTPs here.",
            },
            {
                "stage": "credited",
                "guidance": "Confirm the credit in your own bank statement and update your tracker.",
            },
        ],
        notice="The tracker does not access bank or MahaDBT transaction systems.",
    )


@support_bp.get("/guides/college-verification")
def college_verification_guide():
    return jsonify(
        stages=[
            {
                "stage": "submitted",
                "meaning": "Application has been submitted; college scrutiny may not have started.",
                "next_step": "Keep the application ID and check the portal status.",
            },
            {
                "stage": "under_college_scrutiny",
                "meaning": "The college is checking enrollment, course, documents, and scheme criteria.",
                "next_step": "Respond to any correction request through the official portal before its deadline.",
            },
            {
                "stage": "verified_or_forwarded",
                "meaning": "The college has forwarded the application for the next review stage.",
                "next_step": "Check the portal for department scrutiny; college verification is not final approval.",
            },
            {
                "stage": "sent_back",
                "meaning": "The college requires a correction or additional document.",
                "next_step": "Read the official remark, make the correction, and resubmit through the official portal.",
            },
        ],
        notice="Exact labels and steps can vary by scheme; the official portal status is authoritative.",
    )


@support_bp.get("/tutorials")
def list_tutorials():
    database = get_database()
    ensure_support_indexes(database)
    language = language_for_request()
    tutorials = list(
        database.tutorials.find({"status": "published", "language": language})
    )
    tutorials.sort(key=lambda item: item.get("order", 100))
    return jsonify(language=language, tutorials=[clean_document(item) for item in tutorials])


@support_bp.get("/admin/tutorials")
@admin_authenticated
def list_admin_tutorials():
    database = get_database()
    ensure_support_indexes(database)
    tutorials = list(database.tutorials.find({}))
    tutorials.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return jsonify(tutorials=[clean_document(item) for item in tutorials])


@support_bp.post("/admin/tutorials")
@admin_authenticated
def create_tutorial():
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or set(body) - {
        "title",
        "description",
        "language",
        "video_url",
        "status",
        "order",
    }:
        return jsonify(error="Tutorial contains unsupported fields"), 400
    title, description = body.get("title"), body.get("description")
    language, video_url = body.get("language"), body.get("video_url")
    parsed_url = urlparse(video_url) if isinstance(video_url, str) else None
    if (
        not isinstance(title, str)
        or not title.strip()
        or len(title.strip()) > 160
        or not isinstance(description, str)
        or not description.strip()
        or len(description.strip()) > 2000
        or not isinstance(language, str)
        or language not in TUTORIAL_LANGUAGES
        or parsed_url is None
        or parsed_url.scheme not in {"https", "http"}
        or not parsed_url.netloc
    ):
        return jsonify(error="Provide a title, description, supported language, and valid video URL"), 400
    status = body.get("status", "draft")
    if not isinstance(status, str) or status not in {"draft", "published"}:
        return jsonify(error="status must be draft or published"), 400
    order = body.get("order", 100)
    if isinstance(order, bool) or not isinstance(order, int) or not 0 <= order <= 10000:
        return jsonify(error="order must be an integer from 0 to 10000"), 400
    database = get_database()
    ensure_support_indexes(database)
    tutorial = {
        "id": str(uuid4()),
        "title": title.strip(),
        "description": description.strip(),
        "language": language,
        "video_url": video_url.strip(),
        "status": status,
        "order": order,
        "created_by": g.current_user["user_id"],
        "created_at": datetime.now(timezone.utc),
    }
    database.tutorials.insert_one(tutorial)
    return jsonify(tutorial=clean_document(tutorial)), 201


@support_bp.patch("/admin/tutorials/<tutorial_id>")
@admin_authenticated
def update_tutorial(tutorial_id):
    body = request.get_json(silent=True)
    fields = {"title", "description", "language", "video_url", "status", "order"}
    if not isinstance(body, dict) or not body or set(body) - fields:
        return jsonify(error="Provide one or more supported tutorial fields"), 400
    database = get_database()
    ensure_support_indexes(database)
    tutorial = database.tutorials.find_one({"id": tutorial_id})
    if tutorial is None:
        return jsonify(error="Tutorial was not found"), 404
    updated = dict(body)
    if "title" in updated and (
        not isinstance(updated["title"], str)
        or not updated["title"].strip()
        or len(updated["title"].strip()) > 160
    ):
        return jsonify(error="title must be a non-empty string of at most 160 characters"), 400
    if "description" in updated and (
        not isinstance(updated["description"], str)
        or not updated["description"].strip()
        or len(updated["description"].strip()) > 2000
    ):
        return jsonify(error="description must be a non-empty string of at most 2000 characters"), 400
    if "language" in updated and (
        not isinstance(updated["language"], str)
        or updated["language"] not in TUTORIAL_LANGUAGES
    ):
        return jsonify(error="language must be en, hi, or mr"), 400
    if "video_url" in updated:
        parsed_url = urlparse(updated["video_url"]) if isinstance(updated["video_url"], str) else None
        if parsed_url is None or parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            return jsonify(error="video_url must be a valid http or https URL"), 400
        updated["video_url"] = updated["video_url"].strip()
    if "status" in updated and (
        not isinstance(updated["status"], str)
        or updated["status"] not in {"draft", "published"}
    ):
        return jsonify(error="status must be draft or published"), 400
    if "order" in updated and (
        isinstance(updated["order"], bool)
        or not isinstance(updated["order"], int)
        or not 0 <= updated["order"] <= 10000
    ):
        return jsonify(error="order must be an integer from 0 to 10000"), 400
    for field in ("title", "description"):
        if field in updated:
            updated[field] = updated[field].strip()
    tutorial.update(updated)
    database.tutorials.replace_one({"id": tutorial_id}, tutorial)
    return jsonify(tutorial=clean_document(tutorial))


@support_bp.post("/tickets")
@authenticated
def create_support_ticket():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify(error="Request body must be a JSON object"), 400
    subject, message = body.get("subject"), body.get("message")
    if (
        not isinstance(subject, str)
        or not subject.strip()
        or len(subject.strip()) > 160
        or not isinstance(message, str)
        or not message.strip()
        or len(message.strip()) > 4000
    ):
        return jsonify(error="subject and message are required within the allowed length"), 400
    database = get_database()
    ensure_support_indexes(database)
    now = datetime.now(timezone.utc)
    ticket = {
        "id": new_tracking_id("HELP"),
        "user_id": g.current_user["user_id"],
        "subject": subject.strip(),
        "message": message.strip(),
        "status": "open",
        "created_at": now,
        "updated_at": now,
    }
    database.support_tickets.insert_one(ticket)
    return jsonify(ticket=clean_document(ticket)), 201


@support_bp.get("/tickets")
@authenticated
def list_own_tickets():
    database = get_database()
    ensure_support_indexes(database)
    tickets = list(
        database.support_tickets.find({"user_id": g.current_user["user_id"]})
    )
    tickets.sort(key=lambda item: item.get("created_at"), reverse=True)
    return jsonify(tickets=[clean_document(ticket) for ticket in tickets])


@support_bp.get("/tickets/<ticket_id>")
@authenticated
def get_own_ticket(ticket_id):
    ticket = get_database().support_tickets.find_one(
        {"id": ticket_id, "user_id": g.current_user["user_id"]}
    )
    if ticket is None:
        return jsonify(error="Support ticket was not found"), 404
    return jsonify(ticket=clean_document(ticket))


@support_bp.get("/admin/tickets")
@admin_authenticated
def admin_list_tickets():
    database = get_database()
    ensure_support_indexes(database)
    tickets = list(database.support_tickets.find({}))
    tickets.sort(key=lambda item: item.get("created_at"), reverse=True)
    return jsonify(tickets=[clean_document(ticket) for ticket in tickets])


@support_bp.patch("/admin/tickets/<ticket_id>")
@admin_authenticated
def admin_update_ticket(ticket_id):
    body = request.get_json(silent=True)
    if (
        not isinstance(body, dict)
        or set(body) - {"status", "admin_note"}
        or not isinstance(body.get("status"), str)
        or body.get("status") not in TICKET_STATUSES
    ):
        return jsonify(error="Provide a valid status and optional admin_note"), 400
    note = body.get("admin_note", "")
    if not isinstance(note, str) or len(note.strip()) > 2000:
        return jsonify(error="admin_note must be at most 2000 characters"), 400
    database = get_database()
    ensure_support_indexes(database)
    ticket = database.support_tickets.find_one({"id": ticket_id})
    if ticket is None:
        return jsonify(error="Support ticket was not found"), 404
    ticket.update(
        status=body["status"],
        admin_note=note.strip(),
        updated_at=datetime.now(timezone.utc),
    )
    database.support_tickets.replace_one({"id": ticket_id}, ticket)
    return jsonify(ticket=clean_document(ticket))


@support_bp.post("/grievances")
@authenticated
def create_grievance():
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or set(body) - {"subject", "description", "application_id"}:
        return jsonify(error="Provide subject, description, and optional application_id"), 400
    subject, description = body.get("subject"), body.get("description")
    if (
        not isinstance(subject, str)
        or not subject.strip()
        or len(subject.strip()) > 160
        or not isinstance(description, str)
        or not description.strip()
        or len(description.strip()) > 5000
    ):
        return jsonify(error="subject and description are required within the allowed length"), 400
    database = get_database()
    ensure_support_indexes(database)
    application_id = body.get("application_id")
    if application_id is not None:
        if not isinstance(application_id, str) or not database.applications.find_one(
            {"id": application_id, "user_id": g.current_user["user_id"]}
        ):
            return jsonify(error="Application was not found"), 404
    now = datetime.now(timezone.utc)
    grievance = {
        "id": new_tracking_id("GRV"),
        "user_id": g.current_user["user_id"],
        "subject": subject.strip(),
        "description": description.strip(),
        "application_id": application_id,
        "status": "received",
        "created_at": now,
        "updated_at": now,
    }
    database.grievances.insert_one(grievance)
    return jsonify(grievance=clean_document(grievance)), 201


@support_bp.get("/grievances")
@authenticated
def list_grievances():
    database = get_database()
    ensure_support_indexes(database)
    grievances = list(
        database.grievances.find({"user_id": g.current_user["user_id"]})
    )
    grievances.sort(key=lambda item: item.get("created_at"), reverse=True)
    return jsonify(grievances=[clean_document(item) for item in grievances])


@support_bp.get("/grievances/<grievance_id>")
@authenticated
def get_grievance(grievance_id):
    grievance = get_database().grievances.find_one(
        {"id": grievance_id, "user_id": g.current_user["user_id"]}
    )
    if grievance is None:
        return jsonify(error="Grievance was not found"), 404
    return jsonify(grievance=clean_document(grievance))


@support_bp.get("/admin/grievances")
@admin_authenticated
def admin_list_grievances():
    database = get_database()
    ensure_support_indexes(database)
    grievances = list(database.grievances.find({}))
    grievances.sort(key=lambda item: item.get("created_at"), reverse=True)
    return jsonify(grievances=[clean_document(item) for item in grievances])


@support_bp.patch("/admin/grievances/<grievance_id>")
@admin_authenticated
def admin_update_grievance(grievance_id):
    body = request.get_json(silent=True)
    if (
        not isinstance(body, dict)
        or set(body) != {"status", "resolution_note"}
        or not isinstance(body.get("status"), str)
        or body.get("status") not in GRIEVANCE_STATUSES
    ):
        return jsonify(error="Provide a valid status and resolution_note"), 400
    note = body["resolution_note"]
    if not isinstance(note, str) or len(note.strip()) > 2000:
        return jsonify(error="resolution_note must be at most 2000 characters"), 400
    database = get_database()
    ensure_support_indexes(database)
    grievance = database.grievances.find_one({"id": grievance_id})
    if grievance is None:
        return jsonify(error="Grievance was not found"), 404
    grievance.update(
        status=body["status"],
        resolution_note=note.strip(),
        updated_at=datetime.now(timezone.utc),
    )
    database.grievances.replace_one({"id": grievance_id}, grievance)
    return jsonify(grievance=clean_document(grievance))


@support_bp.post("/feedback")
@authenticated
def submit_feedback():
    body = request.get_json(silent=True)
    if (
        not isinstance(body, dict)
        or set(body) - {"scholarship_id", "rating", "comment"}
    ):
        return jsonify(error="Provide scholarship_id, rating, and optional comment"), 400
    scholarship_id, rating = body.get("scholarship_id"), body.get("rating")
    if (
        not isinstance(scholarship_id, str)
        or isinstance(rating, bool)
        or not isinstance(rating, int)
        or not 1 <= rating <= 5
    ):
        return jsonify(error="scholarship_id is required and rating must be an integer from 1 to 5"), 400
    comment = body.get("comment", "")
    if not isinstance(comment, str) or len(comment.strip()) > 1000:
        return jsonify(error="comment must be at most 1000 characters"), 400
    database = get_database()
    ensure_support_indexes(database)
    if not database.scholarships.find_one({"id": scholarship_id, "status": "active"}):
        return jsonify(error="Scholarship was not found"), 404
    feedback = {
        "id": str(uuid4()),
        "user_id": g.current_user["user_id"],
        "scholarship_id": scholarship_id,
        "rating": rating,
        "comment": comment.strip(),
        "moderation_status": "pending",
        "created_at": datetime.now(timezone.utc),
    }
    try:
        database.feedback.insert_one(feedback)
    except DuplicateKeyError:
        return jsonify(error="You have already rated this scholarship"), 409
    return jsonify(feedback={"id": feedback["id"], "rating": rating}), 201


@support_bp.get("/feedback/<scholarship_id>")
def scholarship_feedback(scholarship_id):
    database = get_database()
    ensure_support_indexes(database)
    ratings = [
        item["rating"]
        for item in database.feedback.find(
            {
                "scholarship_id": scholarship_id,
                "$or": [
                    {"moderation_status": "approved"},
                    {"moderation_status": {"$exists": False}},
                ],
            }
        )
    ]
    if not ratings:
        return jsonify(scholarship_id=scholarship_id, count=0, average_rating=None)
    return jsonify(
        scholarship_id=scholarship_id,
        count=len(ratings),
        average_rating=round(sum(ratings) / len(ratings), 2),
    )


@support_bp.get("/admin/feedback")
@admin_authenticated
def admin_feedback():
    database = get_database()
    ensure_support_indexes(database)
    feedback = list(database.feedback.find({}))
    return jsonify(
        feedback=[
            {
                "id": item["id"],
                "user_id": item["user_id"],
                "scholarship_id": item["scholarship_id"],
                "rating": item["rating"],
                "comment": item.get("comment", ""),
                "moderation_status": item.get("moderation_status", "approved"),
                "created_at": item["created_at"],
            }
            for item in feedback
        ]
    )


@support_bp.patch("/admin/feedback/<feedback_id>")
@admin_authenticated
def moderate_feedback(feedback_id):
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or set(body) != {"moderation_status"}:
        return jsonify(error="Provide a moderation_status of approved or rejected"), 400
    moderation_status = body["moderation_status"]
    if not isinstance(moderation_status, str) or moderation_status not in {"approved", "rejected"}:
        return jsonify(error="moderation_status must be approved or rejected"), 400
    database = get_database()
    ensure_support_indexes(database)
    feedback = database.feedback.find_one({"id": feedback_id})
    if feedback is None:
        return jsonify(error="Feedback was not found"), 404
    feedback["moderation_status"] = moderation_status
    feedback["moderated_by"] = g.current_user["user_id"]
    feedback["moderated_at"] = datetime.now(timezone.utc)
    database.feedback.replace_one({"id": feedback_id}, feedback)
    return jsonify(
        feedback={
            "id": feedback["id"],
            "moderation_status": feedback["moderation_status"],
            "moderated_at": feedback["moderated_at"],
        }
    )
