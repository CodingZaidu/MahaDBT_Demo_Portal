from datetime import date


APPLICATION_STATUSES = (
    "draft",
    "submitted",
    "college_verified",
    "correction_required",
    "approved",
    "rejected",
    "paid",
)
ALLOWED_TRANSITIONS = {
    "draft": {"draft", "submitted"},
    "submitted": {"submitted", "college_verified", "correction_required", "rejected"},
    "college_verified": {"college_verified", "approved", "rejected"},
    "correction_required": {"correction_required", "submitted"},
    "approved": {"approved", "paid", "rejected"},
    "rejected": {"rejected"},
    "paid": {"paid"},
}
APPLICATION_FIELDS = {
    "official_application_id",
    "application_date",
    "status",
    "rejection_reason",
    "reminder_date",
    "notes",
    "checklist",
    "application_form",
}
APPLICATION_FORM_FIELDS = {
    "full_name": 120,
    "mobile": 20,
    "district": 80,
    "category": 40,
    "family_income_range": 80,
    "course": 120,
    "year_of_study": 40,
    "college": 160,
    "previous_percentage": 20,
}


def normalize_application_form(value):
    if not isinstance(value, dict) or set(value) - APPLICATION_FORM_FIELDS.keys():
        raise ValueError("application_form must contain supported application fields")
    normalized = {}
    for field, maximum_length in APPLICATION_FORM_FIELDS.items():
        item = value.get(field, "")
        if field == "year_of_study" and isinstance(item, int) and not isinstance(item, bool):
            item = str(item)
        if not isinstance(item, str) or len(item.strip()) > maximum_length:
            raise ValueError(f"{field} must be a string of at most {maximum_length} characters")
        normalized[field] = item.strip()
    required = ("full_name", "mobile", "district", "category", "course", "college")
    if any(not normalized[field] for field in required):
        raise ValueError(f"Complete these application fields: {', '.join(required)}")
    return normalized


def validate_application_update(data, existing, creating=False):
    if not isinstance(data, dict):
        raise ValueError("Request body must be a JSON object")
    unknown = set(data) - APPLICATION_FIELDS - ({"scholarship_id"} if creating else set())
    if unknown:
        raise ValueError(f"Unknown application fields: {', '.join(sorted(unknown))}")

    updated = dict(existing or {})
    for field in APPLICATION_FIELDS - {"checklist"}:
        if field in data:
            updated[field] = data[field]
    if "application_form" in data:
        updated["application_form"] = normalize_application_form(data["application_form"])
    else:
        updated.setdefault("application_form", {})

    status = updated.get("status", "draft")
    if not isinstance(status, str) or status not in APPLICATION_STATUSES:
        raise ValueError(f"status must be one of: {', '.join(APPLICATION_STATUSES)}")
    if not creating and status not in ALLOWED_TRANSITIONS[existing["status"]]:
        raise ValueError(
            f"Cannot change status from {existing['status']} to {status}"
        )
    updated["status"] = status

    for field in ("application_date", "reminder_date"):
        value = updated.get(field)
        if value is not None:
            if not isinstance(value, str):
                raise ValueError(f"{field} must use YYYY-MM-DD format or be null")
            try:
                parsed = date.fromisoformat(value)
            except ValueError as error:
                raise ValueError(f"{field} must use YYYY-MM-DD format or be null") from error
            if parsed.isoformat() != value:
                raise ValueError(f"{field} must use YYYY-MM-DD format or be null")
    updated.setdefault("application_date", date.today().isoformat())
    updated.setdefault("reminder_date", None)

    application_id = updated.get("official_application_id")
    if application_id is not None and (
        not isinstance(application_id, str) or len(application_id.strip()) > 120
    ):
        raise ValueError("official_application_id must be at most 120 characters or null")
    updated["official_application_id"] = (
        application_id.strip() if application_id else None
    )

    reason = updated.get("rejection_reason")
    if reason is not None and (
        not isinstance(reason, str) or len(reason.strip()) > 2000
    ):
        raise ValueError("rejection_reason must be at most 2000 characters or null")
    updated["rejection_reason"] = reason.strip() if reason else None
    if status == "rejected" and not updated["rejection_reason"]:
        raise ValueError("rejection_reason is required when status is rejected")

    notes = updated.get("notes", "")
    if not isinstance(notes, str) or len(notes.strip()) > 4000:
        raise ValueError("notes must be at most 4000 characters")
    updated["notes"] = notes.strip()

    if "checklist" in data:
        checklist = data["checklist"]
        if not isinstance(checklist, list):
            raise ValueError("checklist must be a list")
        by_name = {item["name"]: item for item in existing.get("checklist", [])}
        normalized = []
        seen = set()
        for item in checklist:
            if (
                not isinstance(item, dict)
                or set(item) != {"name", "completed"}
                or not isinstance(item["name"], str)
                or not isinstance(item["completed"], bool)
            ):
                raise ValueError("Each checklist item must contain name and boolean completed")
            name = item["name"].strip()
            if name not in by_name or name in seen:
                raise ValueError("Checklist items must match unique items for this scheme")
            seen.add(name)
            normalized.append({"name": name, "completed": item["completed"]})
        if seen != set(by_name):
            raise ValueError("Include every checklist item when updating the checklist")
        updated["checklist"] = normalized

    return updated
