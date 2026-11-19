from app.services.scholarships import CATEGORIES, LEVELS


PROFILE_FIELDS = {
    "category",
    "minority",
    "divyang",
    "maharashtra_domicile",
    "family_income_range",
    "district",
    "preferred_language",
    "course",
    "education_level",
    "year_of_study",
    "college",
    "university",
    "previous_percentage",
}
INCOME_RANGES = {
    "below_1_lakh",
    "1_to_2_5_lakh",
    "2_5_to_5_lakh",
    "5_to_8_lakh",
    "above_8_lakh",
}
LANGUAGES = {"en", "hi", "mr"}


def normalize_profile(data, existing=None):
    if not isinstance(data, dict):
        raise ValueError("Request body must be a JSON object")
    unknown = set(data) - PROFILE_FIELDS
    if unknown:
        raise ValueError(f"Unknown profile fields: {', '.join(sorted(unknown))}")
    profile = dict(existing or {})
    profile.update(data)

    category = profile.get("category")
    if category is not None and (
        not isinstance(category, str) or category.lower() not in CATEGORIES
    ):
        raise ValueError(f"category must be one of: {', '.join(sorted(CATEGORIES))}")
    if category is not None:
        profile["category"] = category.lower()

    for field in ("minority", "divyang", "maharashtra_domicile"):
        value = profile.get(field)
        if value is not None and not isinstance(value, bool):
            raise ValueError(f"{field} must be true, false, or null")

    income = profile.get("family_income_range")
    if income is not None and (
        not isinstance(income, str) or income not in INCOME_RANGES
    ):
        raise ValueError(
            f"family_income_range must be one of: {', '.join(sorted(INCOME_RANGES))}"
        )
    language = profile.get("preferred_language")
    if language is not None and (
        not isinstance(language, str) or language not in LANGUAGES
    ):
        raise ValueError("preferred_language must be en, hi, or mr")

    level = profile.get("education_level")
    if level is not None and (
        not isinstance(level, str) or level not in LEVELS
    ):
        raise ValueError(f"education_level must be one of: {', '.join(sorted(LEVELS))}")
    year = profile.get("year_of_study")
    if year is not None and (
        isinstance(year, bool) or not isinstance(year, int) or not 1 <= year <= 12
    ):
        raise ValueError("year_of_study must be an integer between 1 and 12")
    percentage = profile.get("previous_percentage")
    if percentage is not None and (
        isinstance(percentage, bool)
        or not isinstance(percentage, (int, float))
        or not 0 <= percentage <= 100
    ):
        raise ValueError("previous_percentage must be between 0 and 100")
    for field, maximum in (
        ("district", 100),
        ("course", 120),
        ("college", 200),
        ("university", 200),
    ):
        value = profile.get(field)
        if value is not None:
            if not isinstance(value, str) or len(value.strip()) > maximum:
                raise ValueError(f"{field} must be at most {maximum} characters")
            profile[field] = value.strip()
    return profile


def income_bounds(income_range):
    return {
        "below_1_lakh": (0, 100000),
        "1_to_2_5_lakh": (100001, 250000),
        "2_5_to_5_lakh": (250001, 500000),
        "5_to_8_lakh": (500001, 800000),
        "above_8_lakh": (800001, None),
    }.get(income_range)


def assess_eligibility(scholarship, profile):
    criteria = scholarship.get("eligibility", {})
    matches = []
    unmet = []
    unknown = []

    eligible_categories = criteria.get("categories", [])
    if eligible_categories:
        if profile.get("category") is None:
            unknown.append("category")
        elif profile["category"] in eligible_categories:
            matches.append("category")
        else:
            unmet.append("category")

    domicile_required = criteria.get("maharashtra_domicile")
    if domicile_required is not None:
        if profile.get("maharashtra_domicile") is None:
            unknown.append("maharashtra_domicile")
        elif profile["maharashtra_domicile"] is domicile_required:
            matches.append("maharashtra_domicile")
        else:
            unmet.append("maharashtra_domicile")

    for field in ("minority", "divyang"):
        required = criteria.get(field)
        if required is not None:
            value = profile.get(field)
            if value is None:
                unknown.append(field)
            elif value is required:
                matches.append(field)
            else:
                unmet.append(field)

    income_max = criteria.get("income_max")
    if income_max is not None:
        bounds = income_bounds(profile.get("family_income_range"))
        if bounds is None:
            unknown.append("family_income_range")
        elif bounds[0] > income_max:
            unmet.append("family_income_range")
        elif bounds[1] is not None and bounds[1] <= income_max:
            matches.append("family_income_range")
        else:
            unknown.append("family_income_range")

    minimum_percentage = criteria.get("minimum_percentage")
    if minimum_percentage is not None:
        percentage = profile.get("previous_percentage")
        if percentage is None:
            unknown.append("previous_percentage")
        elif percentage >= minimum_percentage:
            matches.append("previous_percentage")
        else:
            unmet.append("previous_percentage")

    courses = [course.casefold() for course in criteria.get("courses", [])]
    if courses:
        course = profile.get("course")
        if not course:
            unknown.append("course")
        elif any(item in course.casefold() or course.casefold() in item for item in courses):
            matches.append("course")
        else:
            unmet.append("course")

    study_years = criteria.get("study_years", [])
    if study_years:
        year = profile.get("year_of_study")
        if year is None:
            unknown.append("year_of_study")
        elif year in study_years:
            matches.append("year_of_study")
        else:
            unmet.append("year_of_study")

    districts = [district.casefold() for district in criteria.get("districts", [])]
    if districts:
        district = profile.get("district")
        if not district:
            unknown.append("district")
        elif district.casefold() in districts:
            matches.append("district")
        else:
            unmet.append("district")

    level = scholarship.get("education_level")
    if level and profile.get("education_level"):
        if profile["education_level"] == level:
            matches.append("education_level")
        else:
            unmet.append("education_level")
    elif level:
        unknown.append("education_level")

    status = "not_eligible" if unmet else "needs_more_information" if unknown else "eligible"
    return {
        "status": status,
        "matched_criteria": matches,
        "unmet_criteria": unmet,
        "missing_information": unknown,
    }
