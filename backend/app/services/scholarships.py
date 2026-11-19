import re
from datetime import date
from decimal import Decimal
from math import isfinite
from urllib.parse import urlparse


LEVELS = {"school", "undergraduate", "postgraduate", "doctoral", "other"}
CATEGORIES = {"open", "obc", "sc", "st", "vjnt", "sbc", "ews", "minority"}
SCHOLARSHIP_FIELDS = {
    "title",
    "description",
    "provider",
    "education_level",
    "categories",
    "eligibility_summary",
    "eligibility",
    "award_amount",
    "payout_amount",
    "deadline",
    "official_url",
    "application_url",
    "documents",
    "faqs",
    "status",
    "translations",
}
ELIGIBILITY_FIELDS = {
    "categories",
    "minority",
    "divyang",
    "maharashtra_domicile",
    "income_max",
    "minimum_percentage",
    "courses",
    "study_years",
    "districts",
}


def normalize_scholarship(data, existing=None):
    if not isinstance(data, dict):
        raise ValueError("Request body must be a JSON object")
    unknown = set(data) - SCHOLARSHIP_FIELDS
    if unknown:
        raise ValueError(f"Unknown scholarship fields: {', '.join(sorted(unknown))}")

    scholarship = dict(existing or {})
    scholarship.update(data)
    for field in (
        "title",
        "description",
        "provider",
        "education_level",
        "categories",
        "eligibility_summary",
        "eligibility",
    ):
        if field not in scholarship:
            raise ValueError(f"{field} is required")
    scholarship.setdefault("status", "active")
    scholarship.setdefault("faqs", [])
    scholarship.setdefault("documents", [])
    scholarship.setdefault("award_amount", None)
    scholarship.setdefault("payout_amount", None)
    scholarship.setdefault("deadline", None)
    scholarship.setdefault("official_url", None)
    scholarship.setdefault("application_url", None)
    scholarship.setdefault("translations", {})

    for field, maximum in (("title", 160), ("provider", 160), ("eligibility_summary", 2000)):
        value = scholarship[field]
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
            raise ValueError(f"{field} must be a non-empty string of at most {maximum} characters")
        scholarship[field] = value.strip()

    description = scholarship["description"]
    if not isinstance(description, str) or not description.strip() or len(description.strip()) > 10000:
        raise ValueError("description must be a non-empty string of at most 10000 characters")
    scholarship["description"] = description.strip()

    if not isinstance(scholarship["education_level"], str) or scholarship[
        "education_level"
    ] not in LEVELS:
        raise ValueError(f"education_level must be one of: {', '.join(sorted(LEVELS))}")
    scholarship["categories"] = validate_categories(scholarship["categories"], "categories")
    if not isinstance(scholarship["status"], str) or scholarship["status"] not in {
        "active",
        "inactive",
    }:
        raise ValueError("status must be active or inactive")

    eligibility = scholarship["eligibility"]
    if not isinstance(eligibility, dict):
        raise ValueError("eligibility must be an object")
    unknown_eligibility = set(eligibility) - ELIGIBILITY_FIELDS
    if unknown_eligibility:
        raise ValueError(
            f"Unknown eligibility fields: {', '.join(sorted(unknown_eligibility))}"
        )
    eligibility_categories = eligibility.get("categories", [])
    eligibility["categories"] = validate_categories(
        eligibility_categories,
        "eligibility.categories",
    )
    domicile = eligibility.get("maharashtra_domicile")
    if domicile is not None and not isinstance(domicile, bool):
        raise ValueError("eligibility.maharashtra_domicile must be true, false, or null")
    for field in ("minority", "divyang"):
        value = eligibility.get(field)
        if value is not None and not isinstance(value, bool):
            raise ValueError(f"eligibility.{field} must be true, false, or null")
    income_max = eligibility.get("income_max")
    if income_max is not None and (
        isinstance(income_max, bool)
        or not isinstance(income_max, (int, float))
        or not isfinite(income_max)
        or income_max < 0
    ):
        raise ValueError("eligibility.income_max must be a non-negative number or null")
    minimum_percentage = eligibility.get("minimum_percentage")
    if minimum_percentage is not None and (
        isinstance(minimum_percentage, bool)
        or not isinstance(minimum_percentage, (int, float))
        or not isfinite(minimum_percentage)
        or not 0 <= minimum_percentage <= 100
    ):
        raise ValueError("eligibility.minimum_percentage must be between 0 and 100 or null")
    courses = eligibility.get("courses", [])
    if not isinstance(courses, list) or any(
        not isinstance(course, str) or not course.strip() or len(course.strip()) > 120
        for course in courses
    ):
        raise ValueError("eligibility.courses must be a list of non-empty course names")
    eligibility["courses"] = [course.strip() for course in courses]
    study_years = eligibility.get("study_years", [])
    if not isinstance(study_years, list) or any(
        isinstance(year, bool) or not isinstance(year, int) or not 1 <= year <= 12
        for year in study_years
    ):
        raise ValueError("eligibility.study_years must contain integers from 1 to 12")
    eligibility["study_years"] = list(dict.fromkeys(study_years))
    districts = eligibility.get("districts", [])
    if not isinstance(districts, list) or any(
        not isinstance(district, str) or not district.strip() or len(district.strip()) > 100
        for district in districts
    ):
        raise ValueError("eligibility.districts must contain non-empty district names")
    eligibility["districts"] = list(dict.fromkeys(district.strip() for district in districts))
    scholarship["eligibility"] = eligibility

    award_amount = scholarship.get("award_amount")
    if award_amount is not None and (
        not isinstance(award_amount, str) or len(award_amount.strip()) > 120
    ):
        raise ValueError("award_amount must be a string of at most 120 characters or null")
    scholarship["award_amount"] = award_amount.strip() if award_amount else None
    payout_amount = scholarship.get("payout_amount")
    if payout_amount is not None:
        if (
            isinstance(payout_amount, bool)
            or not isinstance(payout_amount, (str, int, float))
            or not re.fullmatch(r"(?:0|[1-9]\d{0,11})(?:\.\d{1,2})?", str(payout_amount).strip())
            or Decimal(str(payout_amount).strip()) <= 0
        ):
            raise ValueError("payout_amount must be a positive fixed INR amount with up to 2 decimal places or null")
        payout_amount = f"{Decimal(str(payout_amount).strip()):.2f}"
    scholarship["payout_amount"] = payout_amount

    deadline = scholarship.get("deadline")
    if deadline is not None:
        if not isinstance(deadline, str):
            raise ValueError("deadline must use YYYY-MM-DD format or be null")
        try:
            parsed_deadline = date.fromisoformat(deadline)
        except ValueError as error:
            raise ValueError("deadline must use YYYY-MM-DD format or be null") from error
        if parsed_deadline.isoformat() != deadline:
            raise ValueError("deadline must use YYYY-MM-DD format or be null")
    scholarship["deadline"] = deadline

    for field in ("official_url", "application_url"):
        url = scholarship.get(field)
        if url is not None:
            if not isinstance(url, str) or not valid_http_url(url.strip()):
                raise ValueError(f"{field} must be a valid http or https URL or null")
            scholarship[field] = url.strip()
    scholarship.setdefault("application_url", None)

    documents = scholarship["documents"]
    if not isinstance(documents, list) or any(
        not isinstance(item, str) or not item.strip() or len(item.strip()) > 200
        for item in documents
    ):
        raise ValueError("documents must be a list of non-empty checklist item names")
    scholarship["documents"] = [item.strip() for item in documents]

    faqs = scholarship["faqs"]
    if not isinstance(faqs, list):
        raise ValueError("faqs must be a list")
    normalized_faqs = []
    for faq in faqs:
        if not isinstance(faq, dict) or set(faq) != {"question", "answer"}:
            raise ValueError("Each FAQ must contain only question and answer")
        question, answer = faq["question"], faq["answer"]
        if (
            not isinstance(question, str)
            or not question.strip()
            or len(question.strip()) > 500
            or not isinstance(answer, str)
            or not answer.strip()
            or len(answer.strip()) > 3000
        ):
            raise ValueError("FAQ question and answer must be non-empty and within length limits")
        normalized_faqs.append({"question": question.strip(), "answer": answer.strip()})
    scholarship["faqs"] = normalized_faqs
    translations = scholarship["translations"]
    if not isinstance(translations, dict) or set(translations) - {"en", "hi", "mr"}:
        raise ValueError("translations may contain only en, hi, and mr")
    normalized_translations = {}
    for language, translation in translations.items():
        if not isinstance(translation, dict) or set(translation) - {
            "title",
            "description",
            "eligibility_summary",
        }:
            raise ValueError(f"translations.{language} contains unsupported fields")
        normalized_translations[language] = {}
        for field, value in translation.items():
            maximum = 160 if field == "title" else 10000 if field == "description" else 2000
            if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
                raise ValueError(f"translations.{language}.{field} is invalid")
            normalized_translations[language][field] = value.strip()
    scholarship["translations"] = normalized_translations
    return scholarship


def validate_categories(value, field):
    if not isinstance(value, list) or any(
        not isinstance(category, str) or category.lower() not in CATEGORIES
        for category in value
    ):
        raise ValueError(f"{field} must be a list of supported categories")
    return list(dict.fromkeys(category.lower() for category in value))


def valid_http_url(value):
    parsed = urlparse(value)
    return (
        len(value) <= 2048
        and parsed.scheme in {"http", "https"}
        and bool(parsed.netloc)
        and not re.search(r"\s", value)
    )
