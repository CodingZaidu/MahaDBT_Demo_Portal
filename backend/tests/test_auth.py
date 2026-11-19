import unittest
import base64
import io
import json
from datetime import datetime, timedelta, timezone
import re
from unittest.mock import patch

from cryptography.fernet import Fernet
from PIL import Image
from werkzeug.security import generate_password_hash
from app import create_app
from app.services.auth import make_auth_token, password_matches
from app.services.profiles import assess_eligibility


class FakeCollection:
    def __init__(self):
        self.documents = []

    def create_index(self, *args, **kwargs):
        return None

    def _matches(self, document, query):
        for key, expected in query.items():
            if key == "$or":
                if not any(self._matches(document, clause) for clause in expected):
                    return False
                continue
            if key == "$and":
                if not all(self._matches(document, clause) for clause in expected):
                    return False
                continue
            actual = document.get(key)
            if "." in key:
                actual = document
                for part in key.split("."):
                    actual = actual.get(part) if isinstance(actual, dict) else None
            if isinstance(expected, dict):
                if "$exists" in expected and (actual is not None) != expected["$exists"]:
                    return False
                if actual is None and any(
                    operator in expected for operator in ("$gt", "$lt", "$lte", "$gte")
                ):
                    return False
                if "$gt" in expected and not actual > expected["$gt"]:
                    return False
                if "$lt" in expected and not actual < expected["$lt"]:
                    return False
                if "$lte" in expected and not actual <= expected["$lte"]:
                    return False
                if "$gte" in expected and not actual >= expected["$gte"]:
                    return False
                if "$in" in expected:
                    values = actual if isinstance(actual, list) else [actual]
                    if not any(value in expected["$in"] for value in values):
                        return False
                if "$regex" in expected:
                    values = actual if isinstance(actual, list) else [actual]
                    flags = re.IGNORECASE if expected.get("$options") == "i" else 0
                    if not any(
                        isinstance(value, str)
                        and re.search(expected["$regex"], value, flags=flags)
                        for value in values
                    ):
                        return False
            elif isinstance(actual, list):
                if expected not in actual:
                    return False
            elif actual != expected:
                return False
        return True

    def find_one(self, query):
        return next(
            (document.copy() for document in self.documents if self._matches(document, query)),
            None,
        )

    def insert_one(self, document):
        stored = document.copy()
        stored.setdefault("_id", len(self.documents) + 1)
        self.documents.append(stored)
        return stored["_id"]

    def find_one_and_update(
        self,
        query,
        update,
        upsert=False,
        return_document=None,
    ):
        document = next(
            (candidate for candidate in self.documents if self._matches(candidate, query)),
            None,
        )
        if document is None and upsert:
            document = {key: value for key, value in query.items() if not key.startswith("$")}
            document["_id"] = query.get("_id", len(self.documents) + 1)
            self.documents.append(document)
        if document is None:
            return None
        for key, value in update.get("$inc", {}).items():
            document[key] = document.get(key, 0) + value
        return document.copy()

    def delete_one(self, query):
        for index, document in enumerate(self.documents):
            if self._matches(document, query):
                del self.documents[index]
                return

    def count_documents(self, query):
        return sum(self._matches(document, query) for document in self.documents)

    def find(self, query):
        return FakeCursor(
            [document.copy() for document in self.documents if self._matches(document, query)]
        )

    def replace_one(self, query, replacement):
        for index, document in enumerate(self.documents):
            if self._matches(document, query):
                replacement = replacement.copy()
                replacement.setdefault("_id", document.get("_id"))
                self.documents[index] = replacement
                return

    def update_one(self, query, update):
        for document in self.documents:
            if self._matches(document, query):
                document.update(update.get("$set", {}))
                return type("UpdateResult", (), {"matched_count": 1})()
        return type("UpdateResult", (), {"matched_count": 0})()


class FakeCursor:
    def __init__(self, documents):
        self.documents = documents

    def sort(self, key, direction):
        self.documents.sort(
            key=lambda document: document.get(key) or "",
            reverse=direction < 0,
        )
        return self

    def skip(self, amount):
        self.documents = self.documents[amount:]
        return self

    def limit(self, amount):
        self.documents = self.documents[:amount]
        return self

    def __iter__(self):
        return iter(self.documents)


class FakeDatabase:
    def __init__(self):
        self.users = FakeCollection()
        self.colleges = FakeCollection()
        self.colleges.insert_one({
            "id": "college-test",
            "name": "Test College",
            "normalized_name": "test college",
            "code": "TEST-001",
            "verified": True,
            "verifier_user_id": "CV-TEST-001",
        })
        self.pending_users = FakeCollection()
        self.password_reset_requests = FakeCollection()
        self.counters = FakeCollection()
        self.scholarships = FakeCollection()
        self.applications = FakeCollection()
        self.application_documents = FakeCollection()
        self.support_tickets = FakeCollection()
        self.grievances = FakeCollection()
        self.feedback = FakeCollection()
        self.tutorials = FakeCollection()
        self.notifications = FakeCollection()
        self.surveys = FakeCollection()


class RegistrationApiTests(unittest.TestCase):
    def setUp(self):
        self.database = FakeDatabase()
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret-key",
                "AADHAAR_ENCRYPTION_KEY": Fernet.generate_key().decode("ascii"),
            }
        )
        self.client = self.app.test_client()
        self.database_patch = patch(
            "app.routes.auth.get_database",
            return_value=self.database,
        )
        self.database_patch.start()
        self.addCleanup(self.database_patch.stop)
        self.otp_email_patch = patch("app.routes.auth.send_otp_email")
        self.mock_send_otp_email = self.otp_email_patch.start()
        self.addCleanup(self.otp_email_patch.stop)

    def registration_payload(self):
        return {
            "full_name": "Asha Patil",
            "email": "asha@example.org",
            "mobile": "9876543210",
            "password": "correct-horse-27",
            "confirm_password": "correct-horse-27",
            "date_of_birth": "2004-04-12",
            "gender": "female",
            "consent": True,
        }

    def register(self, otp="123456"):
        with patch("app.routes.auth.generate_otp", return_value=otp):
            return self.client.post(
                "/api/auth/register",
                json=self.registration_payload(),
            )

    def test_registration_verification_login_and_protected_profile(self):
        response = self.register()
        self.assertEqual(response.status_code, 202)
        self.mock_send_otp_email.assert_called_once_with("asha@example.org", "123456")

        pending = self.database.pending_users.documents[0]
        self.assertNotEqual(pending["password_hash"], "correct-horse-27")
        self.assertTrue(password_matches(pending["password_hash"], "correct-horse-27"))
        self.assertNotIn("otp", pending)
        self.assertNotEqual(pending["otp_hash"], "123456")
        self.assertIn("consented_at", pending)
        self.assertEqual(
            (pending["expires_at"] - pending["created_at"]).total_seconds(),
            600,
        )

        with patch("app.routes.auth.send_registration_email") as send_confirmation:
            verified = self.client.post(
                "/api/auth/verify-email",
                json={"email": "asha@example.org", "otp": "123456"},
            )
        self.assertEqual(verified.status_code, 201)
        self.assertEqual(verified.json["user"]["user_id"], f"SS-{datetime.now().year}-000001")
        send_confirmation.assert_called_once_with(
            "asha@example.org",
            f"SS-{datetime.now().year}-000001",
        )
        self.assertEqual(self.database.pending_users.documents, [])

        login = self.client.post(
            "/api/auth/login",
            json={"email": "asha@example.org", "password": "correct-horse-27"},
        )
        self.assertEqual(login.status_code, 200)
        self.assertNotIn("password", login.json["user"])

        student_id_login = self.client.post(
            "/api/auth/login",
            json={
                "identifier": verified.json["user"]["user_id"].lower(),
                "password": "correct-horse-27",
            },
        )
        self.assertEqual(student_id_login.status_code, 200)
        self.assertEqual(
            student_id_login.json["user"]["user_id"],
            verified.json["user"]["user_id"],
        )

        profile = self.client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {login.json['access_token']}"},
        )
        self.assertEqual(profile.status_code, 200)
        self.assertEqual(profile.json["user"]["email"], "asha@example.org")
        self.assertEqual(profile.json["permissions"], {"admin": False, "finance": False})

    def test_password_reset_otp_changes_password_and_can_only_be_used_once(self):
        self.database.users.insert_one(
            {
                "user_id": "SS-2026-000009",
                "full_name": "Asha Patil",
                "email": "asha@example.org",
                "password_hash": generate_password_hash("old-password-123"),
                "role": "student",
            }
        )
        with patch("app.routes.auth.send_password_reset_otp_email") as send_reset_email:
            with patch("app.routes.auth.generate_otp", return_value="654321") as generate_otp:
                requested = self.client.post(
                    "/api/auth/forgot-password",
                    json={"email": "asha@example.org"},
                )
        self.assertEqual(requested.status_code, 202)
        generate_otp.assert_called_once_with()
        send_reset_email.assert_called_once_with("asha@example.org", "654321")
        reset_request = self.database.password_reset_requests.documents[0]
        self.assertNotEqual(reset_request["otp_hash"], "654321")

        changed = self.client.post(
            "/api/auth/reset-password",
            json={
                "email": "asha@example.org",
                "otp": "654321",
                "password": "new-password-456",
                "confirm_password": "new-password-456",
            },
        )
        self.assertEqual(changed.status_code, 200)
        account = self.database.users.find_one({"email": "asha@example.org"})
        self.assertTrue(password_matches(account["password_hash"], "new-password-456"))
        self.assertEqual(self.database.password_reset_requests.documents, [])

        reused_code = self.client.post(
            "/api/auth/reset-password",
            json={
                "email": "asha@example.org",
                "otp": "654321",
                "password": "another-password-789",
                "confirm_password": "another-password-789",
            },
        )
        self.assertEqual(reused_code.status_code, 404)

        old_password_login = self.client.post(
            "/api/auth/login",
            json={"identifier": "asha@example.org", "password": "old-password-123"},
        )
        new_password_login = self.client.post(
            "/api/auth/login",
            json={"identifier": "asha@example.org", "password": "new-password-456"},
        )
        self.assertEqual(old_password_login.status_code, 401)
        self.assertEqual(new_password_login.status_code, 200)

    def test_password_reset_does_not_disclose_unknown_email_and_limits_otp_attempts(self):
        unknown = self.client.post(
            "/api/auth/forgot-password",
            json={"email": "unknown@example.org"},
        )
        self.assertEqual(unknown.status_code, 202)
        self.assertEqual(
            unknown.json["message"],
            "If an account exists for this email, a password reset code has been sent.",
        )
        self.assertEqual(self.database.password_reset_requests.documents, [])

        self.database.users.insert_one(
            {
                "user_id": "SS-2026-000009",
                "full_name": "Asha Patil",
                "email": "asha@example.org",
                "password_hash": generate_password_hash("old-password-123"),
                "role": "student",
            }
        )
        with patch("app.routes.auth.send_password_reset_otp_email"):
            with patch("app.routes.auth.generate_otp", return_value="654321"):
                requested = self.client.post(
                    "/api/auth/forgot-password",
                    json={"email": "asha@example.org"},
                )
        self.assertEqual(requested.status_code, 202)

        for attempt in range(4):
            rejected = self.client.post(
                "/api/auth/reset-password",
                json={
                    "email": "asha@example.org",
                    "otp": "000000",
                    "password": "new-password-456",
                    "confirm_password": "new-password-456",
                },
            )
            self.assertEqual(rejected.status_code, 400, msg=f"attempt {attempt + 1}")
        locked = self.client.post(
            "/api/auth/reset-password",
            json={
                "email": "asha@example.org",
                "otp": "000000",
                "password": "new-password-456",
                "confirm_password": "new-password-456",
            },
        )
        self.assertEqual(locked.status_code, 429)
        self.assertEqual(self.database.password_reset_requests.documents, [])

    def test_optional_aadhaar_is_encrypted_and_never_returned(self):
        aadhaar = "000000000000"
        payload = self.registration_payload()
        payload["aadhaar"] = aadhaar
        payload["aadhaar_consent"] = True
        with patch("app.routes.auth.generate_otp", return_value="123456"):
            response = self.client.post("/api/auth/register", json=payload)

        self.assertEqual(response.status_code, 202)
        pending = self.database.pending_users.documents[0]
        self.assertNotIn("aadhaar", pending)
        self.assertNotEqual(pending["aadhaar_encrypted"], aadhaar)
        self.assertIn("aadhaar_consented_at", pending)
        cipher = Fernet(self.app.config["AADHAAR_ENCRYPTION_KEY"].encode("ascii"))
        self.assertEqual(
            cipher.decrypt(pending["aadhaar_encrypted"].encode("ascii")).decode("ascii"),
            aadhaar,
        )
        self.assertNotIn(aadhaar, response.get_data(as_text=True))

        with patch("app.routes.auth.send_registration_email"):
            verified = self.client.post(
                "/api/auth/verify-email",
                json={"email": "asha@example.org", "otp": "123456"},
            )
        self.assertEqual(verified.status_code, 201)
        self.assertNotIn("aadhaar", verified.json["user"])
        account = self.database.users.documents[0]
        self.assertNotIn("aadhaar", account)
        self.assertIn("aadhaar_consented_at", account)
        self.assertEqual(
            cipher.decrypt(account["aadhaar_encrypted"].encode("ascii")).decode("ascii"),
            aadhaar,
        )
        self.assertNotIn(aadhaar, verified.get_data(as_text=True))

    def test_aadhaar_requires_twelve_digits_and_encryption_key(self):
        invalid_payload = self.registration_payload()
        invalid_payload["aadhaar"] = "1234"
        invalid_payload["aadhaar_consent"] = True
        invalid = self.client.post("/api/auth/register", json=invalid_payload)
        self.assertEqual(invalid.status_code, 400)
        self.assertIn("exactly 12 digits", invalid.json["error"])

        no_consent_payload = self.registration_payload()
        no_consent_payload["aadhaar"] = "000000000000"
        no_consent = self.client.post("/api/auth/register", json=no_consent_payload)
        self.assertEqual(no_consent.status_code, 400)
        self.assertIn("consent is required", no_consent.json["error"])

        self.app.config["AADHAAR_ENCRYPTION_KEY"] = None
        payload = self.registration_payload()
        payload["aadhaar"] = "000000000000"
        payload["aadhaar_consent"] = True
        unavailable = self.client.post("/api/auth/register", json=payload)
        self.assertEqual(unavailable.status_code, 503)
        self.assertNotIn("000000000000", unavailable.get_data(as_text=True))

    def test_otp_expires_after_ten_minutes(self):
        response = self.register()
        self.assertEqual(response.status_code, 202)
        self.database.pending_users.documents[0]["expires_at"] = datetime(
            2000,
            1,
            1,
            tzinfo=timezone.utc,
        )

        verified = self.client.post(
            "/api/auth/verify-email",
            json={"email": "asha@example.org", "otp": "123456"},
        )
        self.assertEqual(verified.status_code, 410)
        self.assertEqual(self.database.pending_users.documents, [])

    def test_fifth_incorrect_otp_attempt_invalidates_registration(self):
        response = self.register()
        self.assertEqual(response.status_code, 202)

        for attempt in range(4):
            response = self.client.post(
                "/api/auth/verify-email",
                json={"email": "asha@example.org", "otp": "000000"},
            )
            self.assertEqual(response.status_code, 400, msg=f"attempt {attempt + 1}")
        response = self.client.post(
            "/api/auth/verify-email",
            json={"email": "asha@example.org", "otp": "000000"},
        )
        self.assertEqual(response.status_code, 429)
        self.assertEqual(self.database.pending_users.documents, [])

    def test_registration_rejects_unconfirmed_password_and_missing_consent(self):
        payload = self.registration_payload()
        payload["confirm_password"] = "different-password"
        response = self.client.post("/api/auth/register", json=payload)
        self.assertEqual(response.status_code, 400)

        payload = self.registration_payload()
        payload["consent"] = False
        response = self.client.post("/api/auth/register", json=payload)
        self.assertEqual(response.status_code, 400)

        payload = self.registration_payload()
        payload["full_name"] = "   "
        response = self.client.post("/api/auth/register", json=payload)
        self.assertEqual(response.status_code, 400)

    def test_email_delivery_failure_does_not_leave_pending_account(self):
        with patch(
            "app.routes.auth.send_otp_email",
            side_effect=RuntimeError("SMTP is not configured"),
        ):
            response = self.register()

        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.database.pending_users.documents, [])


class SmtpEmailTests(unittest.TestCase):
    def test_otp_and_registration_confirmation_are_sent_through_smtp(self):
        app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret-key",
                "SMTP_HOST": "smtp.example.org",
                "SMTP_PORT": 587,
                "SMTP_USERNAME": "support@example.org",
                "SMTP_PASSWORD": "test-app-password",
                "SMTP_FROM": "support@example.org",
                "SMTP_USE_TLS": True,
            }
        )
        with app.app_context(), patch("app.services.auth.smtplib.SMTP") as smtp_factory:
            smtp = smtp_factory.return_value.__enter__.return_value
            smtp.send_message.return_value = {}
            from app.services.auth import (
                send_otp_email,
                send_password_reset_otp_email,
                send_registration_email,
            )

            send_otp_email("student@example.org", "123456")
            otp_message = smtp.send_message.call_args.args[0]
            self.assertIn("123456", otp_message.get_content())
            self.assertNotIn("password", otp_message.get_content().lower())

            send_registration_email("student@example.org", "SS-2026-000123")
            confirmation = smtp.send_message.call_args.args[0]
            self.assertIn("SS-2026-000123", confirmation.get_content())
            self.assertIn("same password you created", confirmation.get_content())
            self.assertNotIn("test-app-password", confirmation.get_content())

            send_password_reset_otp_email("student@example.org", "654321")
            reset_message = smtp.send_message.call_args.args[0]
            self.assertIn("654321", reset_message.get_content())
            self.assertIn("expires in 10 minutes", reset_message.get_content())
            self.assertIn("ignore this email", reset_message.get_content())

            self.assertEqual(smtp_factory.call_args.args, ("smtp.example.org", 587))
            self.assertEqual(smtp.starttls.call_count, 3)
            self.assertEqual(smtp.login.call_count, 3)


class ScholarshipApiTests(unittest.TestCase):
    def setUp(self):
        self.database = FakeDatabase()
        self.database.users.insert_one(
            {"user_id": "SS-2026-000001", "email": "admin@example.org"}
        )
        self.database.users.insert_one(
            {"user_id": "SS-2026-000002", "email": "student@example.org"}
        )
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret-key",
                "ADMIN_EMAILS": ["admin@example.org"],
            }
        )
        self.client = self.app.test_client()
        self.database_patch = patch(
            "app.routes.auth.get_database",
            return_value=self.database,
        )
        self.database_patch.start()
        self.addCleanup(self.database_patch.stop)
        self.scholarship_database_patch = patch(
            "app.routes.scholarships.get_database",
            return_value=self.database,
        )
        self.scholarship_database_patch.start()
        self.addCleanup(self.scholarship_database_patch.stop)
        with self.app.app_context():
            self.admin_token = make_auth_token("SS-2026-000001")
            self.student_token = make_auth_token("SS-2026-000002")

    def authorization(self, token):
        return {"Authorization": f"Bearer {token}"}

    def payload(self, **overrides):
        payload = {
            "title": "Maharashtra Merit Scholarship",
            "description": "Support for eligible undergraduate students.",
            "provider": "State Scholarship Department",
            "education_level": "undergraduate",
            "categories": ["obc", "sc"],
            "eligibility_summary": "Maharashtra domicile and annual income below 800000.",
            "eligibility": {
                "categories": ["obc", "sc"],
                "maharashtra_domicile": True,
                "income_max": 800000,
                "minimum_percentage": 60,
                "courses": ["Engineering"],
            },
            "award_amount": "Up to INR 50,000",
            "deadline": "2026-12-31",
            "official_url": "https://example.org/scholarship",
            "application_url": "https://example.org/apply",
            "documents": ["Income certificate", "Marksheet"],
            "faqs": [
                {
                    "question": "Where do I apply?",
                    "answer": "Use the official application portal.",
                }
            ],
        }
        payload.update(overrides)
        return payload

    def create_scholarship(self, payload=None):
        return self.client.post(
            "/api/scholarships",
            json=payload if payload is not None else self.payload(),
            headers=self.authorization(self.admin_token),
        )

    def test_public_directory_filters_and_paginates_active_schemes(self):
        created = self.create_scholarship()
        self.assertEqual(created.status_code, 201)
        scholarship_id = created.json["scholarship"]["id"]

        second_payload = self.payload(
            title="Postgraduate Research Award",
            education_level="postgraduate",
            categories=["open"],
            deadline="2026-11-30",
        )
        self.assertEqual(self.create_scholarship(second_payload).status_code, 201)
        self.database.scholarships.insert_one(
            {**self.payload(title="Hidden scheme", status="inactive"), "id": "hidden"}
        )

        response = self.client.get(
            "/api/scholarships?level=undergraduate&category=obc"
            "&eligibility=domicile&deadline_before=2026-12-31&per_page=1"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["pagination"]["total"], 1)
        self.assertEqual(response.json["items"][0]["id"], scholarship_id)

        response = self.client.get("/api/scholarships?q=research")
        self.assertEqual(response.json["pagination"]["total"], 1)
        self.assertEqual(response.json["items"][0]["education_level"], "postgraduate")

    def test_deadline_filter_lists_schemes_open_through_selected_date(self):
        self.assertEqual(
            self.create_scholarship(self.payload(deadline="2025-12-31")).status_code,
            201,
        )
        self.assertEqual(
            self.create_scholarship(self.payload(title="Open scheme", deadline="2027-01-15")).status_code,
            201,
        )
        self.assertEqual(
            self.create_scholarship(self.payload(title="No deadline", deadline=None)).status_code,
            201,
        )

        response = self.client.get("/api/scholarships?deadline_after=2026-01-01")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["title"] for item in response.json["items"]], ["Open scheme"])

    def test_scholarship_can_be_created_without_hidden_url_fields(self):
        payload = self.payload()
        payload.pop("official_url")
        payload.pop("application_url")
        created = self.create_scholarship(payload)

        self.assertEqual(created.status_code, 201)
        self.assertIsNone(created.json["scholarship"]["official_url"])
        self.assertIsNone(created.json["scholarship"]["application_url"])
        self.assertNotIn("verified_at", created.json["scholarship"])

    def test_admin_only_crud_and_archive(self):
        no_token = self.client.post("/api/scholarships", json=self.payload())
        self.assertEqual(no_token.status_code, 401)
        student_response = self.client.post(
            "/api/scholarships",
            json=self.payload(),
            headers=self.authorization(self.student_token),
        )
        self.assertEqual(student_response.status_code, 403)

        created = self.create_scholarship()
        self.assertEqual(created.status_code, 201)
        scholarship_id = created.json["scholarship"]["id"]
        verified = self.client.post(
            f"/api/scholarships/{scholarship_id}/verification",
            json={"verified": True},
            headers=self.authorization(self.admin_token),
        )
        self.assertEqual(verified.status_code, 200)

        updated = self.client.patch(
            f"/api/scholarships/{scholarship_id}",
            json={"deadline": "2027-01-15"},
            headers=self.authorization(self.admin_token),
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json["scholarship"]["deadline"], "2027-01-15")
        stored = self.database.scholarships.find_one({"id": scholarship_id})
        self.assertNotIn("verified_at", stored)

        archived = self.client.delete(
            f"/api/scholarships/{scholarship_id}",
            headers=self.authorization(self.admin_token),
        )
        self.assertEqual(archived.status_code, 200)
        self.assertEqual(
            self.client.get(f"/api/scholarships/{scholarship_id}").status_code,
            404,
        )
        all_records = self.client.get(
            "/api/scholarships/admin",
            headers=self.authorization(self.admin_token),
        )
        self.assertEqual(all_records.json["items"][0]["status"], "inactive")

    def test_invalid_scheme_data_and_filters_return_clear_errors(self):
        invalid = self.create_scholarship(self.payload(official_url="javascript:alert(1)"))
        self.assertEqual(invalid.status_code, 400)
        self.assertIn("http or https", invalid.json["error"])

        response = self.client.get("/api/scholarships?level=unlisted")
        self.assertEqual(response.status_code, 400)
        response = self.client.get("/api/scholarships?sort=unsupported")
        self.assertEqual(response.status_code, 400)


class ProfileAndScholarshipIntelligenceTests(unittest.TestCase):
    def setUp(self):
        self.database = FakeDatabase()
        self.database.users.insert_one(
            {
                "user_id": "SS-2026-000003",
                "email": "student@example.org",
                "profile": {},
            }
        )
        self.scholarship = {
            "id": "scheme-1",
            "title": "Merit Support",
            "description": "Scholarship for eligible students.",
            "provider": "State",
            "education_level": "undergraduate",
            "categories": ["obc"],
            "eligibility_summary": "Domicile, income and marks criteria.",
            "eligibility": {
                "categories": ["obc"],
                "maharashtra_domicile": True,
                "income_max": 500000,
                "minimum_percentage": 60,
                "courses": ["Engineering"],
            },
            "award_amount": "INR 20,000",
            "deadline": "2026-12-30",
            "official_url": "https://example.org/official",
            "documents": ["Income certificate"],
            "faqs": [],
            "status": "active",
        }
        self.database.scholarships.insert_one(self.scholarship)
        self.database.scholarships.insert_one(
            {
                **self.scholarship,
                "id": "scheme-2",
                "title": "Open Research Award",
                "education_level": "postgraduate",
                "categories": ["open"],
                "status": "active",
            }
        )
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret-key",
            }
        )
        self.client = self.app.test_client()
        self.database_patches = [
            patch("app.routes.auth.get_database", return_value=self.database),
            patch("app.routes.scholarships.get_database", return_value=self.database),
            patch("app.routes.profiles.get_database", return_value=self.database),
        ]
        for database_patch in self.database_patches:
            database_patch.start()
            self.addCleanup(database_patch.stop)
        with self.app.app_context():
            self.token = make_auth_token("SS-2026-000003")
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def test_profile_saves_only_supported_non_sensitive_fields(self):
        response = self.client.patch(
            "/api/profile",
            json={
                "category": "OBC",
                "maharashtra_domicile": True,
                "family_income_range": "2_5_to_5_lakh",
                "education_level": "undergraduate",
                "course": "Engineering",
                "previous_percentage": 75,
                "preferred_language": "mr",
            },
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["profile"]["category"], "obc")
        self.assertNotIn("aadhaar", response.json["profile"])
        alerts = self.client.patch(
            "/api/profile",
            json={"alert_channels": ["email", "sms"]},
            headers=self.headers,
        )
        self.assertEqual(alerts.status_code, 400)

        response = self.client.patch(
            "/api/profile",
            json={"aadhaar": "123456789012"},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 400)

    def test_eligibility_checker_returns_match_missing_and_mismatch_reasons(self):
        profile = {
            "category": "obc",
            "maharashtra_domicile": True,
            "family_income_range": "2_5_to_5_lakh",
            "education_level": "undergraduate",
            "course": "Computer Engineering",
            "previous_percentage": 75,
        }
        response = self.client.post(
            "/api/profile/eligibility",
            json={"scholarship_id": "scheme-1", "profile": profile},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["result"]["status"], "eligible")

        missing_response = self.client.post(
            "/api/profile/eligibility",
            json={"scholarship_id": "scheme-1", "profile": {"category": "obc"}},
        )
        self.assertEqual(
            missing_response.json["result"]["status"],
            "needs_more_information",
        )
        self.assertIn("course", missing_response.json["result"]["missing_information"])

        profile["previous_percentage"] = 40
        mismatch = self.client.post(
            "/api/profile/eligibility",
            json={"scholarship_id": "scheme-1", "profile": profile},
        )
        self.assertEqual(mismatch.json["result"]["status"], "not_eligible")
        self.assertIn("previous_percentage", mismatch.json["result"]["unmet_criteria"])

    def test_recommendations_and_two_to_three_scheme_comparison(self):
        response = self.client.get("/api/profile/recommendations", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["recommendations"], [])
        self.assertEqual(
            response.json["missing_profile_fields"],
            ["category", "education_level", "maharashtra_domicile"],
        )

        self.client.patch(
            "/api/profile",
            json={
                "category": "obc",
                "maharashtra_domicile": True,
                "family_income_range": "2_5_to_5_lakh",
                "education_level": "undergraduate",
                "course": "Engineering",
                "previous_percentage": 75,
            },
            headers=self.headers,
        )
        response = self.client.get("/api/profile/recommendations", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["recommendations"][0]["scholarship"]["id"], "scheme-1")
        self.assertEqual(len(response.json["recommendations"]), 1)

        comparison = self.client.get(
            "/api/profile/compare?id=scheme-1&id=scheme-2"
        )
        self.assertEqual(comparison.status_code, 200)
        self.assertEqual(len(comparison.json["comparison"]), 2)
        invalid = self.client.get("/api/profile/compare?id=scheme-1")
        self.assertEqual(invalid.status_code, 400)

    def test_eligibility_assessment_marks_unknown_income_range(self):
        result = assess_eligibility(
            self.scholarship,
            {"category": "obc", "maharashtra_domicile": True},
        )
        self.assertEqual(result["status"], "needs_more_information")
        self.assertIn("family_income_range", result["missing_information"])
        partially_overlapping_range = assess_eligibility(
            self.scholarship,
            {
                "category": "obc",
                "maharashtra_domicile": True,
                "family_income_range": "2_5_to_5_lakh",
            },
        )
        self.assertEqual(
            partially_overlapping_range["status"],
            "needs_more_information",
        )


class ApplicationAndDocumentTests(unittest.TestCase):
    def setUp(self):
        self.database = FakeDatabase()
        self.database.users.insert_one(
            {
                "user_id": "SS-2026-000004",
                "full_name": "Test Student",
                "email": "student@example.org",
                "profile": {},
            }
        )
        self.database.users.insert_one(
            {
                "user_id": "SS-2026-000006",
                "full_name": "Finance Admin",
                "email": "finance@example.org",
                "profile": {},
            }
        )
        self.database.users.insert_one({
            "user_id": "CV-TEST-001",
            "full_name": "Test Verifier",
            "email": "verifier@testcollege.example",
            "mobile": "",
            "password_hash": generate_password_hash("test-verifier-password"),
            "role": "college_verifier",
            "college_id": "college-test",
            "college_name": "Test College",
        })
        self.database.scholarships.insert_one(
            {
                "id": "scheme-1",
                "title": "Merit Support",
                "description": "Scholarship for eligible students.",
                "provider": "State",
                "education_level": "undergraduate",
                "categories": ["obc"],
                "eligibility_summary": "Domicile, income and marks criteria.",
                "eligibility": {"categories": ["obc"]},
                "status": "active",
                "deadline": None,
                "payout_amount": "25000.00",
                "documents": ["Income certificate", "Previous marksheet"],
            }
        )
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret-key",
                "DOCUMENT_ENCRYPTION_KEY": Fernet.generate_key().decode("ascii"),
                "BANK_DETAILS_ENCRYPTION_KEY": Fernet.generate_key().decode("ascii"),
                "ADMIN_EMAILS": ["student@example.org"],
                "FINANCE_ADMIN_EMAILS": ["finance@example.org"],
            }
        )
        self.client = self.app.test_client()
        self.database_patches = [
            patch("app.routes.auth.get_database", return_value=self.database),
            patch("app.routes.scholarships.get_database", return_value=self.database),
            patch("app.routes.applications.get_database", return_value=self.database),
            patch("app.routes.colleges.get_database", return_value=self.database),
        ]
        for database_patch in self.database_patches:
            database_patch.start()
            self.addCleanup(database_patch.stop)
        with self.app.app_context():
            self.token = make_auth_token("SS-2026-000004")
            self.finance_token = make_auth_token("SS-2026-000006")
            self.verifier_token = make_auth_token("CV-TEST-001")
        self.headers = {"Authorization": f"Bearer {self.token}"}
        self.finance_headers = {"Authorization": f"Bearer {self.finance_token}"}
        self.verifier_headers = {"Authorization": f"Bearer {self.verifier_token}"}

    def test_current_account_reports_admin_permissions(self):
        response = self.client.get("/api/auth/me", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["permissions"], {"admin": True, "finance": False})

        finance = self.client.get("/api/auth/me", headers=self.finance_headers)
        self.assertEqual(finance.status_code, 200)
        self.assertEqual(finance.json["permissions"], {"admin": False, "finance": True})

    def test_application_creation_rejects_expired_deadlines(self):
        self.database.scholarships.documents[0]["deadline"] = (
            datetime.now(timezone.utc).date() - timedelta(days=1)
        ).isoformat()

        expired = self.client.post(
            "/api/applications",
            json={"scholarship_id": "scheme-1", "document_consent": True},
            headers=self.headers,
        )
        self.assertEqual(expired.status_code, 409)
        self.assertEqual(
            expired.json["error"],
            "The scholarship application deadline has passed",
        )
        self.assertEqual(self.database.applications.documents, [])

        self.database.scholarships.documents[0]["deadline"] = (
            datetime.now(timezone.utc).date().isoformat()
        )
        open_until_today = self.client.post(
            "/api/applications",
            json={"scholarship_id": "scheme-1", "document_consent": True},
            headers=self.headers,
        )
        self.assertEqual(open_until_today.status_code, 201)

    def test_application_dashboard_checklist_status_and_timeline(self):
        missing_consent = self.client.post(
            "/api/applications",
            json={"scholarship_id": "scheme-1"},
            headers=self.headers,
        )
        self.assertEqual(missing_consent.status_code, 400)
        created = self.client.post(
            "/api/applications",
            json={"scholarship_id": "scheme-1", "document_consent": True},
            headers=self.headers,
        )
        self.assertEqual(created.status_code, 201)
        application = created.json["application"]
        self.assertEqual(application["status"], "draft")
        self.assertEqual(len(application["checklist"]), 2)
        application_id = application["id"]
        application_form = {
            "full_name": "Test Student",
            "mobile": "9876543210",
            "district": "Pune",
            "category": "open",
            "family_income_range": "Below ₹2.5 lakh",
            "course": "Engineering",
            "year_of_study": 2,
            "college": "Test College",
            "previous_percentage": "82",
        }
        updated_form = self.client.patch(
            f"/api/applications/{application_id}",
            json={
                "application_form": application_form,
                "bank_details": {"account_number": "123456789012", "ifsc": "SBIN0001234"},
                "bank_details_consent": True,
            },
            headers=self.headers,
        )
        self.assertEqual(updated_form.status_code, 200)
        incomplete = self.client.patch(
            f"/api/applications/{application_id}",
            json={"status": "submitted"},
            headers=self.headers,
        )
        self.assertEqual(incomplete.status_code, 400)
        self.assertIn("Upload required documents", incomplete.json["error"])
        for document_name in ["Income certificate", "Previous marksheet"]:
            uploaded = self.client.post(
                f"/api/applications/{application_id}/documents",
                data={
                    "document_name": document_name,
                    "file": (io.BytesIO(b"%PDF-1.4\nsample document"), f"{document_name}.pdf"),
                },
                headers=self.headers,
                content_type="multipart/form-data",
            )
            self.assertEqual(uploaded.status_code, 201)
        duplicate = self.client.post(
            "/api/applications",
            json={"scholarship_id": "scheme-1", "document_consent": True},
            headers=self.headers,
        )
        self.assertEqual(duplicate.status_code, 200)
        self.assertTrue(duplicate.json["resumed"])
        self.assertEqual(duplicate.json["application"]["id"], application_id)

        updated = self.client.patch(
            f"/api/applications/{application_id}",
            json={
                "status": "submitted",
                "official_application_id": "MDBT-001",
                "reminder_date": "2026-11-01",
            },
            headers=self.headers,
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json["application"]["status"], "submitted")
        repeated_submission = self.client.post(
            "/api/applications",
            json={"scholarship_id": "scheme-1", "document_consent": True},
            headers=self.headers,
        )
        self.assertEqual(repeated_submission.status_code, 409)

        dashboard = self.client.get(
            "/api/applications/dashboard",
            headers=self.headers,
        )
        self.assertEqual(dashboard.json["totals"]["submitted"], 1)
        self.assertEqual(len(dashboard.json["due_reminders"]), 1)

        timeline = self.client.get(
            f"/api/applications/{application_id}/timeline",
            headers=self.headers,
        )
        self.assertEqual(
            [item["status"] for item in timeline.json["timeline"]],
            ["draft", "submitted"],
        )
        self.assertIn("fund distribution", timeline.json["payment_guidance"])

    def test_admin_can_review_application_and_view_encrypted_documents(self):
        self.database.scholarships.documents[0]["payout_amount"] = None
        created = self.client.post(
            "/api/applications",
            json={
                "scholarship_id": "scheme-1",
                "document_consent": True,
                "application_form": {
                    "full_name": "Test Student",
                    "mobile": "9876543210",
                    "district": "Pune",
                    "category": "open",
                    "family_income_range": "",
                    "course": "Engineering",
                    "year_of_study": "2",
                    "college": "Test College",
                    "previous_percentage": "82",
                },
                "bank_details": {"account_number": "123456789012", "ifsc": "SBIN0001234"},
                "bank_details_consent": True,
            },
            headers=self.headers,
        )
        application_id = created.json["application"]["id"]
        self.client.post(
            f"/api/applications/{application_id}/documents",
            data={
                "document_name": "Income certificate",
                "file": (io.BytesIO(b"%PDF-1.4\nprivate certificate"), "income.pdf"),
            },
            headers=self.headers,
            content_type="multipart/form-data",
        )
        self.client.post(
            f"/api/applications/{application_id}/documents",
            data={
                "document_name": "Previous marksheet",
                "file": (io.BytesIO(b"%PDF-1.4\nprivate marksheet"), "marksheet.pdf"),
            },
            headers=self.headers,
            content_type="multipart/form-data",
        )
        submitted = self.client.patch(
            f"/api/applications/{application_id}",
            json={"status": "submitted"},
            headers=self.headers,
        )
        self.assertEqual(submitted.status_code, 200)
        self.assertEqual(submitted.json["application"]["status"], "submitted")
        locked_edit = self.client.patch(
            f"/api/applications/{application_id}",
            json={"application_form": {"full_name": "Changed Student"}},
            headers=self.headers,
        )
        self.assertEqual(locked_edit.status_code, 409)
        pending_queue = self.client.get("/api/applications/admin", headers=self.headers)
        self.assertEqual(pending_queue.status_code, 200)
        self.assertEqual(
            next(item for item in pending_queue.json["applications"] if item["id"] == application_id)["status"],
            "submitted",
        )
        self.assertEqual(len(self.database.application_documents.documents), 2)
        stored_application = self.database.applications.find_one({"id": application_id})
        self.assertNotIn("123456789012", stored_application["bank_details_encrypted"])
        self.assertNotIn(
            b"private certificate",
            self.database.application_documents.documents[0]["encrypted_data"],
        )
        student_cannot_review = self.client.get(
            "/api/colleges/applications",
            headers=self.headers,
        )
        self.assertEqual(student_cannot_review.status_code, 403)
        other_college = self.client.post(
            "/api/colleges/admin",
            json={
                "name": "Other Test College",
                "code": "OTHER-001",
                "verifier_name": "Other Verifier",
                "verifier_email": "other-verifier@example.org",
                "verifier_password": "other-verifier-password",
            },
            headers=self.headers,
        )
        self.database.applications.insert_one({
            "id": "other-college-application",
            "college_id": other_college.json["college"]["id"],
            "user_id": "SS-2026-000004",
            "status": "submitted",
            "updated_at": datetime.now(timezone.utc),
            "documents": [],
        })

        with patch("app.routes.colleges.dispatch_notification") as send_college_email:
            correction = self.client.post(
                f"/api/colleges/applications/{application_id}/review",
                json={"status": "correction_required", "note": "Upload a clearer marksheet."},
                headers=self.verifier_headers,
            )
        self.assertEqual(correction.status_code, 200)
        self.assertEqual(correction.json["application"]["status"], "correction_required")
        self.assertEqual(correction.json["email_status"], "sent")
        self.assertIn("Upload a clearer marksheet.", send_college_email.call_args.args[0]["body"])
        resubmitted = self.client.patch(
            f"/api/applications/{application_id}",
            json={"status": "submitted"},
            headers=self.headers,
        )
        self.assertEqual(resubmitted.status_code, 200)
        self.assertEqual(resubmitted.json["application"]["status"], "submitted")

        bypass_department = self.client.patch(
            f"/api/applications/admin/{application_id}",
            json={"status": "approved"},
            headers=self.headers,
        )
        self.assertEqual(bypass_department.status_code, 409)

        college_queue = self.client.get(
            "/api/colleges/applications",
            headers=self.verifier_headers,
        )
        self.assertEqual(college_queue.status_code, 200)
        self.assertEqual(len(college_queue.json["applications"]), 1)
        foreign_review = self.client.post(
            "/api/colleges/applications/other-college-application/review",
            json={"status": "college_verified", "note": ""},
            headers=self.verifier_headers,
        )
        self.assertEqual(foreign_review.status_code, 404)
        document_id = college_queue.json["applications"][0]["documents"][0]["id"]
        college_document = self.client.get(
            f"/api/colleges/applications/{application_id}/documents/{document_id}",
            headers=self.verifier_headers,
        )
        self.assertEqual(college_document.status_code, 200)
        self.assertTrue(college_document.data.startswith(b"%PDF-1.4"))

        with patch("app.routes.colleges.dispatch_notification") as send_college_email:
            verified = self.client.post(
                f"/api/colleges/applications/{application_id}/review",
                json={"status": "college_verified", "note": ""},
                headers=self.verifier_headers,
            )
        self.assertEqual(verified.status_code, 200)
        self.assertEqual(verified.json["application"]["status"], "college_verified")
        self.assertEqual(verified.json["email_status"], "sent")
        self.assertIn("forwarded to the department", send_college_email.call_args.args[0]["body"])

        review_queue = self.client.get("/api/applications/admin", headers=self.headers)
        self.assertEqual(review_queue.status_code, 200)
        self.assertEqual(len(review_queue.json["applications"]), 2)
        student_application = next(
            item for item in review_queue.json["applications"] if item["id"] == application_id
        )
        self.assertEqual(student_application["student"]["email"], "student@example.org")
        allowed_admins = self.app.config["ADMIN_EMAILS"]
        self.app.config["ADMIN_EMAILS"] = []
        denied = self.client.get("/api/applications/admin", headers=self.headers)
        self.assertEqual(denied.status_code, 403)
        self.app.config["ADMIN_EMAILS"] = allowed_admins
        downloaded = self.client.get(
            f"/api/applications/admin/{application_id}/documents/{document_id}",
            headers=self.headers,
        )
        self.assertEqual(downloaded.status_code, 200)
        self.assertTrue(downloaded.headers["Cache-Control"].startswith("no-store"))
        self.assertTrue(downloaded.data.startswith(b"%PDF-1.4"))

        with patch("app.routes.applications.dispatch_notification") as send_email:
            correction_request = self.client.patch(
                f"/api/applications/admin/{application_id}",
                json={"status": "correction_required", "admin_note": "Correct the year of study."},
                headers=self.headers,
            )
        self.assertEqual(correction_request.status_code, 200)
        self.assertEqual(correction_request.json["application"]["status"], "correction_required")
        self.assertEqual(correction_request.json["email_status"], "sent")
        self.assertIn("Correct the year of study.", send_email.call_args.args[0]["body"])
        resubmitted_to_admin = self.client.patch(
            f"/api/applications/{application_id}",
            json={
                "application_form": {
                    **student_application["application_form"],
                    "year_of_study": "3",
                },
                "status": "submitted",
            },
            headers=self.headers,
        )
        self.assertEqual(resubmitted_to_admin.status_code, 200)
        self.assertEqual(resubmitted_to_admin.json["application"]["status"], "college_verified")
        locked_again = self.client.patch(
            f"/api/applications/{application_id}",
            json={"application_form": {"full_name": "Changed after resubmit"}},
            headers=self.headers,
        )
        self.assertEqual(locked_again.status_code, 409)

        approval_without_amount = self.client.patch(
            f"/api/applications/admin/{application_id}",
            json={"status": "approved", "admin_note": "Verified."},
            headers=self.headers,
        )
        self.assertEqual(approval_without_amount.status_code, 409)
        self.assertEqual(
            approval_without_amount.json["error"],
            "Set an exact fixed amount in Admin dashboard > Scholarships before approval",
        )
        self.assertEqual(approval_without_amount.json["code"], "missing_fixed_payout_amount")
        self.assertEqual(approval_without_amount.json["scholarship_id"], "scheme-1")
        scholarship_update = self.client.patch(
            "/api/scholarships/scheme-1",
            json={"payout_amount": "25000.00"},
            headers=self.headers,
        )
        self.assertEqual(scholarship_update.status_code, 200, scholarship_update.json)
        self.assertEqual(scholarship_update.json["scholarship"]["payout_amount"], "25000.00")

        with patch("app.routes.applications.dispatch_notification") as send_email:
            approved = self.client.patch(
                f"/api/applications/admin/{application_id}",
                json={"status": "approved", "admin_note": "Verified."},
                headers=self.headers,
            )
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(approved.json["application"]["status"], "approved")
        self.assertEqual(approved.json["application"]["admin_note"], "Verified.")
        self.assertEqual(approved.json["application"]["payout_amount"], "25000.00")
        self.assertNotIn("bank_details_encrypted", approved.json["application"])
        self.assertEqual(approved.json["email_status"], "sent")
        send_email.assert_called_once()
        approval_email = send_email.call_args.args[0]
        self.assertEqual(approval_email["recipient"], "student@example.org")
        self.assertIn("Fund distribution is pending", approval_email["body"])
        student_view = self.client.get(
            f"/api/applications/{application_id}",
            headers=self.headers,
        )
        self.assertEqual(student_view.json["application"]["status"], "approved")
        timeline = self.client.get(
            f"/api/applications/{application_id}/timeline",
            headers=self.headers,
        )
        self.assertIn("fund distribution", timeline.json["payment_guidance"])
        finance_queue = self.client.get(
            "/api/applications/finance",
            headers=self.finance_headers,
        )
        self.assertEqual(finance_queue.status_code, 200)
        self.assertEqual(finance_queue.json["simulation_only"], True)
        self.assertEqual(len(finance_queue.json["items"]), 1)
        finance_item = finance_queue.json["items"][0]
        self.assertEqual(finance_item["payout_amount"], "25000.00")
        self.assertEqual(finance_item["bank_account_number"], "123456789012")
        self.assertEqual(finance_item["ifsc"], "SBIN0001234")
        self.assertNotIn("student", finance_item)
        self.assertNotIn("full_name", finance_item)
        with patch("app.routes.applications.dispatch_notification") as send_email:
            paid = self.client.post(
                f"/api/applications/finance/{application_id}/simulate-disbursement",
                headers=self.finance_headers,
            )
        self.assertEqual(paid.status_code, 200)
        self.assertEqual(paid.json["status"], "paid")
        self.assertEqual(paid.json["distribution_mode"], "simulated")
        self.assertEqual(paid.json["distributed_amount"], "25000.00")
        self.assertEqual(paid.json["email_status"], "sent")
        distribution_email = send_email.call_args.args[0]
        self.assertIn("₹25000.00", distribution_email["body"])
        self.assertIn("No money was transferred", distribution_email["body"])
        self.assertEqual(distribution_email["recipient"], "student@example.org")
        notification_count = len(self.database.notifications.documents)
        duplicate = self.client.post(
            f"/api/applications/finance/{application_id}/simulate-disbursement",
            headers=self.finance_headers,
        )
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(len(self.database.notifications.documents), notification_count)
        paid_student_application = self.client.get(
            f"/api/applications/{application_id}",
            headers=self.headers,
        )
        self.assertEqual(
            [entry["status"] for entry in paid_student_application.json["application"]["status_history"]],
            [
                "draft",
                "submitted",
                "correction_required",
                "submitted",
                "college_verified",
                "correction_required",
                "college_verified",
                "approved",
                "paid",
            ],
        )

    def test_college_and_admin_rejections_email_the_student(self):
        now = datetime.now(timezone.utc)
        base_application = {
            "user_id": "SS-2026-000004",
            "scholarship_id": "scheme-1",
            "scholarship_title": "Merit Support",
            "college_id": "college-test",
            "college_name": "Test College",
            "application_form": {"full_name": "Test Student"},
            "documents": [],
            "updated_at": now,
            "status_history": [],
        }
        self.database.applications.insert_one({
            **base_application,
            "id": "college-rejection",
            "status": "submitted",
        })
        with patch("app.routes.colleges.dispatch_notification") as college_email:
            college_rejection = self.client.post(
                "/api/colleges/applications/college-rejection/review",
                json={"status": "rejected", "note": "The enrollment record does not match."},
                headers=self.verifier_headers,
            )
        self.assertEqual(college_rejection.status_code, 200)
        self.assertEqual(college_rejection.json["email_status"], "sent")
        self.assertIn("The enrollment record does not match.", college_email.call_args.args[0]["body"])

        self.database.applications.insert_one({
            **base_application,
            "id": "admin-rejection",
            "status": "college_verified",
        })
        with patch("app.routes.applications.dispatch_notification") as admin_email:
            admin_rejection = self.client.patch(
                "/api/applications/admin/admin-rejection",
                json={"status": "rejected", "rejection_reason": "The award criteria were not met."},
                headers=self.headers,
            )
        self.assertEqual(admin_rejection.status_code, 200)
        self.assertEqual(admin_rejection.json["email_status"], "sent")
        self.assertIn("The award criteria were not met.", admin_email.call_args.args[0]["body"])

    def test_admin_can_create_college_and_verifier_login(self):
        created = self.client.post(
            "/api/colleges/admin",
            json={
                "name": "New Demo Institute",
                "code": "DEMO-NEW-02",
                "verifier_name": "Verifier Person",
                "verifier_email": "new-verifier@example.org",
                "verifier_password": "safe-demo-password",
            },
            headers=self.headers,
        )
        self.assertEqual(created.status_code, 201)
        self.assertTrue(created.json["college"]["verified"])
        self.assertTrue(created.json["verifier"]["user_id"].startswith("CV-"))

        login = self.client.post(
            "/api/auth/login",
            json={"identifier": "new-verifier@example.org", "password": "safe-demo-password"},
        )
        self.assertEqual(login.status_code, 200)
        self.assertEqual(login.json["user"]["role"], "college_verifier")
        self.assertEqual(login.json["user"]["college_id"], created.json["college"]["id"])
        verifier_id_login = self.client.post(
            "/api/auth/login",
            json={"identifier": created.json["verifier"]["user_id"].lower(), "password": "safe-demo-password"},
        )
        self.assertEqual(verifier_id_login.status_code, 200)

        unused_college = self.client.post(
            "/api/colleges/admin",
            json={
                "name": "Unused Demo Institute",
                "code": "DEMO-UNUSED-03",
                "verifier_name": "Unused Verifier",
                "verifier_email": "unused-verifier@example.org",
                "verifier_password": "safe-demo-password",
            },
            headers=self.headers,
        )
        self.assertEqual(unused_college.status_code, 201)
        unused_college_id = unused_college.json["college"]["id"]
        permanent_delete = self.client.delete(
            f"/api/colleges/admin/{unused_college_id}",
            headers=self.headers,
        )
        self.assertEqual(permanent_delete.status_code, 200)
        self.assertTrue(permanent_delete.json["deleted"])
        self.assertIsNone(self.database.colleges.find_one({"id": unused_college_id}))
        self.assertIsNone(self.database.users.find_one({"user_id": unused_college.json["verifier"]["user_id"]}))

        student_colleges = self.client.get("/api/colleges/list", headers=self.headers)
        self.assertEqual(student_colleges.status_code, 200)
        self.assertIn("New Demo Institute", [item["name"] for item in student_colleges.json["colleges"]])

        self.database.applications.insert_one({
            "id": "application-for-removed-college",
            "user_id": "SS-2026-000004",
            "scholarship_id": "scheme-1",
            "scholarship_title": "Merit Support",
            "college_id": created.json["college"]["id"],
            "college_name": "New Demo Institute",
            "status": "submitted",
            "application_form": {"full_name": "Test Student"},
            "documents": [],
            "updated_at": datetime.now(timezone.utc),
        })
        removed = self.client.delete(
            f"/api/colleges/admin/{created.json['college']['id']}",
            headers=self.headers,
        )
        self.assertEqual(removed.status_code, 200)
        self.assertTrue(removed.json["verifier_access_removed"])
        self.assertIsNotNone(self.database.applications.find_one({"id": "application-for-removed-college"}))
        removed_colleges = self.client.get("/api/colleges/list", headers=self.headers)
        self.assertNotIn("New Demo Institute", [item["name"] for item in removed_colleges.json["colleges"]])
        removed_verifier_login = self.client.post(
            "/api/auth/login",
            json={"identifier": "new-verifier@example.org", "password": "safe-demo-password"},
        )
        self.assertEqual(removed_verifier_login.status_code, 401)
        admin_queue = self.client.get("/api/applications/admin", headers=self.headers)
        removed_application = next(
            item for item in admin_queue.json["applications"]
            if item["id"] == "application-for-removed-college"
        )
        self.assertFalse(removed_application["college_active"])
        admin_correction = self.client.patch(
            "/api/applications/admin/application-for-removed-college",
            json={"status": "correction_required", "admin_note": "Please update your enrollment details."},
            headers=self.headers,
        )
        self.assertEqual(admin_correction.status_code, 200)
        self.assertEqual(admin_correction.json["application"]["correction_requested_by"], "admin")
        repeated_delete = self.client.delete(
            f"/api/colleges/admin/{created.json['college']['id']}",
            headers=self.headers,
        )
        self.assertEqual(repeated_delete.status_code, 409)

    def test_application_bank_details_validation_and_finance_email_retry(self):
        self.database.scholarships.documents[0]["documents"] = []
        created = self.client.post(
            "/api/applications",
            json={
                "scholarship_id": "scheme-1",
                "document_consent": True,
                "application_form": {
                    "full_name": "Test Student",
                    "mobile": "9876543210",
                    "district": "Pune",
                    "category": "open",
                    "family_income_range": "",
                    "course": "Engineering",
                    "year_of_study": "2",
                    "college": "Test College",
                    "previous_percentage": "82",
                },
                "bank_details": {"account_number": "123456789012", "ifsc": "SBIN0001234"},
                "bank_details_consent": True,
            },
            headers=self.headers,
        )
        application_id = created.json["application"]["id"]
        submitted = self.client.patch(
            f"/api/applications/{application_id}",
            json={"status": "submitted"},
            headers=self.headers,
        )
        self.assertEqual(submitted.status_code, 200)
        college_verified = self.client.post(
            f"/api/colleges/applications/{application_id}/review",
            json={"status": "college_verified", "note": ""},
            headers=self.verifier_headers,
        )
        self.assertEqual(college_verified.status_code, 200)
        with patch(
            "app.routes.applications.dispatch_notification",
            side_effect=RuntimeError("SMTP temporarily unavailable"),
        ):
            approved = self.client.patch(
                f"/api/applications/admin/{application_id}",
                json={"status": "approved"},
                headers=self.headers,
            )
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(approved.json["email_status"], "failed")
        approval_notification = self.database.notifications.documents[-1]
        self.assertEqual(approval_notification["status"], "failed")
        self.assertEqual(approval_notification["attempts"], 1)

        with patch(
            "app.routes.applications.dispatch_notification",
            side_effect=RuntimeError("SMTP temporarily unavailable"),
        ):
            paid = self.client.post(
                f"/api/applications/finance/{application_id}/simulate-disbursement",
                headers=self.finance_headers,
            )
        self.assertEqual(paid.status_code, 200)
        self.assertEqual(paid.json["email_status"], "failed")
        notification = self.database.notifications.documents[-1]
        self.assertEqual(notification["status"], "failed")
        self.assertIn("SMTP temporarily unavailable", notification["last_error"])
        forbidden = self.client.get("/api/applications/finance", headers=self.headers)
        self.assertEqual(forbidden.status_code, 403)

    def test_application_rejects_invalid_status_checklist_and_cross_user_access(self):
        created = self.client.post(
            "/api/applications",
            json={"scholarship_id": "scheme-1", "document_consent": True},
            headers=self.headers,
        )
        application_id = created.json["application"]["id"]

        invalid_status = self.client.patch(
            f"/api/applications/{application_id}",
            json={"status": "paid"},
            headers=self.headers,
        )
        self.assertEqual(invalid_status.status_code, 403)

        invalid_checklist = self.client.patch(
            f"/api/applications/{application_id}",
            json={"checklist": [{"name": "Unknown item", "completed": True}]},
            headers=self.headers,
        )
        self.assertEqual(invalid_checklist.status_code, 400)

        other_user = self.client.get(
            "/api/applications/not-owned",
            headers=self.headers,
        )
        self.assertEqual(other_user.status_code, 404)

    def test_document_precheck_resizes_compresses_and_does_not_store(self):
        image_bytes = io.BytesIO()
        Image.new("RGB", (400, 300), "white").save(image_bytes, format="JPEG")
        response = self.client.post(
            "/api/applications/documents/check",
            data={"file": (io.BytesIO(image_bytes.getvalue()), "certificate.jpg")},
            headers=self.headers,
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json["stored"])
        self.assertTrue(response.json["blurry"])
        processed = base64.b64decode(response.json["processed_file_base64"])
        self.assertTrue(processed.startswith(b"\xff\xd8"))
        self.assertEqual(self.database.applications.documents, [])

        guide = self.client.get("/api/applications/documents/upload-guide")
        self.assertEqual(guide.status_code, 200)
        self.assertEqual(guide.json["maximum_size_bytes"], 8 * 1024 * 1024)

    def test_document_precheck_compresses_clear_image_and_rejects_unknown_type(self):
        image = Image.new("RGB", (180, 180), "white")
        for x in range(0, 180, 12):
            for y in range(180):
                image.putpixel((x, y), (0, 0, 0))
        image_bytes = io.BytesIO()
        image.save(image_bytes, format="PNG")
        response = self.client.post(
            "/api/applications/documents/check",
            data={"file": (io.BytesIO(image_bytes.getvalue()), "marksheet.png")},
            headers=self.headers,
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["file_type"], "image/png")
        self.assertFalse(response.json["blurry"])
        self.assertLess(
            response.json["processed_size_bytes"],
            response.json["original_size_bytes"],
        )
        large = Image.new("RGB", (2200, 2200), "white")
        large_bytes = io.BytesIO()
        large.save(large_bytes, format="PNG")
        resized = self.client.post(
            "/api/applications/documents/check",
            data={"file": (io.BytesIO(large_bytes.getvalue()), "large.png")},
            headers=self.headers,
            content_type="multipart/form-data",
        )
        self.assertEqual(resized.status_code, 200)
        self.assertLessEqual(max(resized.json["dimensions"].values()), 2000)

        unknown = self.client.post(
            "/api/applications/documents/check",
            data={"file": (io.BytesIO(b"not a supported file"), "file.txt")},
            headers=self.headers,
            content_type="multipart/form-data",
        )
        self.assertEqual(unknown.status_code, 400)


class SupportAndCommunityTests(unittest.TestCase):
    def setUp(self):
        self.database = FakeDatabase()
        self.database.users.insert_one(
            {"user_id": "SS-2026-000005", "email": "student@example.org"}
        )
        self.database.users.insert_one(
            {"user_id": "SS-2026-000006", "email": "admin@example.org"}
        )
        self.database.scholarships.insert_one(
            {
                "id": "scheme-1",
                "title": "Merit Support",
                "description": "Support for undergraduate education students.",
                "provider": "State Department",
                "education_level": "undergraduate",
                "categories": ["obc"],
                "eligibility_summary": "For eligible OBC students.",
                "eligibility": {"categories": ["obc"], "courses": ["Engineering"]},
                "payout_amount": "25000.00",
                "official_url": "https://example.org/merit",
                "status": "active",
                "translations": {
                    "hi": {
                        "title": "Merit Sahayata",
                        "description": "Snatak vidyarthiyon ke liye sahayata.",
                        "eligibility_summary": "Yogya OBC vidyarthiyon ke liye.",
                    }
                },
            }
        )
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret-key",
                "BANK_DETAILS_ENCRYPTION_KEY": Fernet.generate_key().decode("ascii"),
                "ADMIN_EMAILS": ["admin@example.org"],
            }
        )
        self.client = self.app.test_client()
        self.database_patches = [
            patch("app.routes.auth.get_database", return_value=self.database),
            patch("app.routes.scholarships.get_database", return_value=self.database),
            patch("app.routes.support.get_database", return_value=self.database),
            patch("app.routes.admin.get_database", return_value=self.database),
            patch("app.routes.applications.get_database", return_value=self.database),
        ]
        for database_patch in self.database_patches:
            database_patch.start()
            self.addCleanup(database_patch.stop)
        with self.app.app_context():
            self.student_token = make_auth_token("SS-2026-000005")
            self.admin_token = make_auth_token("SS-2026-000006")
            self.bank_details_encrypted = Fernet(
                self.app.config["BANK_DETAILS_ENCRYPTION_KEY"].encode("ascii")
            ).encrypt(
                json.dumps(
                    {"account_number": "123456789012", "ifsc": "SBIN0001234"}
                ).encode("utf-8")
            ).decode("ascii")
        self.student_headers = {"Authorization": f"Bearer {self.student_token}"}
        self.admin_headers = {"Authorization": f"Bearer {self.admin_token}"}

    def test_chatbot_answers_only_from_explicitly_verified_scheme_sources(self):
        response = self.client.get("/api/chat?q=merit%20support&lang=hi")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["sources"], [])

        verified = self.client.post(
            "/api/scholarships/scheme-1/verification",
            json={"verified": True},
            headers=self.admin_headers,
        )
        self.assertEqual(verified.status_code, 200)
        response = self.client.get("/api/chat?q=merit%20support&lang=hi")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["language"], "hi")
        self.assertEqual(response.json["answer"][0]["title"], "Merit Sahayata")
        self.assertEqual(response.json["sources"], ["https://example.org/merit"])

        no_match = self.client.get("/api/chat?q=unrelated%20topic&lang=mr")
        self.assertEqual(no_match.json["language"], "mr")
        self.assertIn("योजना", no_match.json["answer"])
        untranslated = self.client.get("/api/chat?q=merit%20support&lang=mr")
        self.assertIn("Marathi verified", untranslated.json["answer"])

    def test_admin_can_review_scheme_without_url_and_broad_chat_query_lists_it(self):
        scheme = self.database.scholarships.documents[0]
        scheme.pop("official_url")

        response = self.client.get("/api/chat?q=which%20scholarship%20schemes%20can%20apply%20me")
        self.assertIn("administrator-reviewed", response.json["answer"])
        self.assertEqual(response.json["review_pending_count"], 1)

        reviewed = self.client.post(
            "/api/scholarships/scheme-1/verification",
            json={"verified": True},
            headers=self.admin_headers,
        )
        self.assertEqual(reviewed.status_code, 200)

        response = self.client.get("/api/chat?q=which%20scholarship%20schemes%20can%20apply%20me")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["answer"][0]["title"], "Merit Support")
        self.assertEqual(response.json["sources"], [])

    def test_help_ticket_and_grievance_can_be_created_and_privately_tracked(self):
        ticket = self.client.post(
            "/api/tickets",
            json={"subject": "Status help", "message": "Please explain this status."},
            headers=self.student_headers,
        )
        self.assertEqual(ticket.status_code, 201)
        ticket_id = ticket.json["ticket"]["id"]
        self.assertTrue(ticket_id.startswith("HELP-"))
        self.assertEqual(
            self.client.get(
                f"/api/tickets/{ticket_id}",
                headers=self.student_headers,
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(
                f"/api/tickets/{ticket_id}",
                headers=self.admin_headers,
            ).status_code,
            404,
        )

        grievance = self.client.post(
            "/api/grievances",
            json={
                "subject": "Verification delay",
                "description": "College status has not changed.",
            },
            headers=self.student_headers,
        )
        self.assertEqual(grievance.status_code, 201)
        grievance_id = grievance.json["grievance"]["id"]
        self.assertTrue(grievance_id.startswith("GRV-"))
        self.assertEqual(
            self.client.get(
                f"/api/grievances/{grievance_id}",
                headers=self.student_headers,
            ).status_code,
            200,
        )

        admin_update = self.client.patch(
            f"/api/admin/grievances/{grievance_id}",
            json={"status": "under_review", "resolution_note": "Checking with the college."},
            headers=self.admin_headers,
        )
        self.assertEqual(admin_update.status_code, 200)
        self.assertEqual(admin_update.json["grievance"]["status"], "under_review")

    def test_feedback_rating_guides_and_admin_video_tutorials(self):
        feedback = self.client.post(
            "/api/feedback",
            json={"scholarship_id": "scheme-1", "rating": 5, "comment": "Helpful."},
            headers=self.student_headers,
        )
        self.assertEqual(feedback.status_code, 201)
        feedback_id = self.database.feedback.documents[0]["id"]
        self.assertEqual(
            self.client.get("/api/feedback/scheme-1").json["count"],
            0,
        )
        admin_feedback = self.client.get(
            "/api/admin/feedback",
            headers=self.admin_headers,
        )
        self.assertEqual(admin_feedback.status_code, 200)
        self.assertEqual(
            admin_feedback.json["feedback"][0]["moderation_status"],
            "pending",
        )
        self.assertEqual(
            self.client.patch(
                f"/api/admin/feedback/{feedback_id}",
                json={"moderation_status": "approved"},
                headers=self.student_headers,
            ).status_code,
            403,
        )
        moderation = self.client.patch(
            f"/api/admin/feedback/{feedback_id}",
            json={"moderation_status": "approved"},
            headers=self.admin_headers,
        )
        self.assertEqual(moderation.status_code, 200)
        rating = self.client.get("/api/feedback/scheme-1")
        self.assertEqual(rating.json["average_rating"], 5)
        analytics = self.client.get(
            "/api/admin/analytics",
            headers=self.admin_headers,
        )
        self.assertEqual(analytics.json["feedback"]["count"], 1)
        self.assertEqual(analytics.json["feedback"]["average_rating"], 5)
        self.assertEqual(
            self.client.patch(
                f"/api/admin/feedback/{feedback_id}",
                json={"moderation_status": "rejected"},
                headers=self.admin_headers,
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.get("/api/feedback/scheme-1").json["count"],
            0,
        )

        invalid_rating = self.client.post(
            "/api/feedback",
            json={"scholarship_id": "scheme-1", "rating": 6},
            headers=self.student_headers,
        )
        self.assertEqual(invalid_rating.status_code, 400)
        self.assertEqual(self.client.get("/api/guides/payment").status_code, 200)
        self.assertEqual(
            self.client.get("/api/guides/college-verification").status_code,
            200,
        )
        rejection = self.client.get("/api/guides/rejection?reason=income%20certificate")
        self.assertIn("certificate", rejection.json["guidance"][0]["fix"])

        tutorial = self.client.post(
            "/api/admin/tutorials",
            json={
                "title": "Application guide",
                "description": "How to review an application.",
                "language": "en",
                "video_url": "https://video.example.org/guide",
                "status": "published",
            },
            headers=self.admin_headers,
        )
        self.assertEqual(tutorial.status_code, 201)
        tutorials = self.client.get("/api/tutorials?lang=en")
        self.assertEqual(len(tutorials.json["tutorials"]), 1)
        tutorial_id = tutorial.json["tutorial"]["id"]
        updated_tutorial = self.client.patch(
            f"/api/admin/tutorials/{tutorial_id}",
            json={"status": "draft"},
            headers=self.admin_headers,
        )
        self.assertEqual(updated_tutorial.status_code, 200)
        self.assertEqual(
            len(self.client.get("/api/tutorials?lang=en").json["tutorials"]),
            0,
        )
        admin_tutorials = self.client.get(
            "/api/admin/tutorials",
            headers=self.admin_headers,
        )
        self.assertEqual(admin_tutorials.status_code, 200)
        self.assertEqual(len(admin_tutorials.json["tutorials"]), 1)
        self.assertEqual(admin_tutorials.json["tutorials"][0]["status"], "draft")
        self.assertEqual(
            self.client.get(
                "/api/admin/tutorials",
                headers=self.student_headers,
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.get("/api/admin/tutorials").status_code,
            401,
        )

    def test_feedback_moderation_rejects_invalid_status_and_missing_records(self):
        created = self.client.post(
            "/api/feedback",
            json={"scholarship_id": "scheme-1", "rating": 4},
            headers=self.student_headers,
        )
        feedback_id = self.database.feedback.documents[0]["id"]
        invalid = self.client.patch(
            f"/api/admin/feedback/{feedback_id}",
            json={"moderation_status": ["approved"]},
            headers=self.admin_headers,
        )
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(
            self.client.patch(
                "/api/admin/feedback/missing",
                json={"moderation_status": "approved"},
                headers=self.admin_headers,
            ).status_code,
            404,
        )
        self.assertEqual(created.status_code, 201)

    def test_admin_analytics_and_published_survey_results(self):
        self.database.users.documents[0]["email_verified"] = True
        self.database.scholarships.documents[0]["verified_at"] = datetime.now(timezone.utc)
        self.database.applications.insert_one(
            {
                "id": "application-1",
                "user_id": "SS-2026-000005",
                "scholarship_id": "scheme-1",
                "status": "submitted",
            }
        )
        analytics = self.client.get(
            "/api/admin/analytics",
            headers=self.admin_headers,
        )
        self.assertEqual(analytics.status_code, 200)
        self.assertEqual(analytics.json["students"], 1)
        self.assertEqual(analytics.json["applications"]["by_status"]["submitted"], 1)
        self.assertEqual(analytics.json["scholarships"]["verified"], 1)

        survey = self.client.post(
            "/api/admin/surveys",
            json={
                "title": "Student support survey",
                "question": "Which support channel is most useful?",
                "language": "en",
                "respondents": 20,
                "options": [
                    {"label": "Email", "count": 12},
                    {"label": "Helpline", "count": 8},
                ],
                "source_url": "https://example.org/research",
                "survey_date": "2026-10-01",
                "status": "published",
            },
            headers=self.admin_headers,
        )
        self.assertEqual(survey.status_code, 201)
        results = self.client.get("/api/surveys/results")
        self.assertEqual(len(results.json["results"]), 1)
        self.assertEqual(
            results.json["results"][0]["chart"],
            {"labels": ["Email", "Helpline"], "values": [12, 8]},
        )

    def test_application_status_queues_email_and_dispatch_retries_failures(self):
        self.database.applications.insert_one(
            {
                "id": "application-1",
                "user_id": "SS-2026-000005",
                "scholarship_id": "scheme-1",
                "scholarship_title": "Merit Support",
                "status": "draft",
                "official_application_id": None,
                "application_date": "2026-10-01",
                "reminder_date": None,
                "rejection_reason": None,
                "notes": "",
                "payout_amount": "25000.00",
                "bank_details_encrypted": self.bank_details_encrypted,
                "bank_details_consent_at": datetime.now(timezone.utc).isoformat(),
                "application_form": {
                    "full_name": "Test Student",
                    "mobile": "9876543210",
                    "district": "Pune",
                    "category": "open",
                    "family_income_range": "",
                    "course": "Engineering",
                    "year_of_study": "",
                    "college": "Test College",
                    "previous_percentage": "",
                },
                "documents": [],
                "checklist": [],
                "status_history": [{"status": "draft", "at": "2026-10-01T00:00:00+00:00"}],
            }
        )
        updated = self.client.patch(
            "/api/applications/application-1",
            json={"status": "submitted"},
            headers=self.student_headers,
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(len(self.database.notifications.documents), 1)
        self.assertEqual(self.database.notifications.documents[0]["status"], "pending")

        with patch(
            "app.routes.admin.dispatch_notification",
            side_effect=RuntimeError("SMTP temporarily unavailable"),
        ):
            response = self.client.post(
                "/api/admin/notifications/dispatch",
                headers=self.admin_headers,
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["failed"], 1)
        self.assertEqual(self.database.notifications.documents[0]["status"], "failed")
        with patch("app.routes.admin.dispatch_notification") as dispatch:
            response = self.client.post(
                "/api/admin/notifications/dispatch",
                headers=self.admin_headers,
            )
        self.assertEqual(response.json["sent"], 1)
        dispatch.assert_called_once()
        self.assertEqual(self.database.notifications.documents[0]["status"], "sent")
        listed = self.client.get(
            "/api/admin/notifications",
            headers=self.admin_headers,
        )
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(
            listed.json["notifications"][0]["subject"],
            self.database.notifications.documents[0]["subject"],
        )

    def test_sms_and_whatsapp_dispatch_are_not_supported(self):
        response = self.client.post(
            "/api/admin/notifications/dispatch?channel=sms",
            headers=self.admin_headers,
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("SMTP email", response.json["error"])
        whatsapp = self.client.post(
            "/api/admin/notifications/dispatch?channel=whatsapp",
            headers=self.admin_headers,
        )
        self.assertEqual(whatsapp.status_code, 400)

    def test_due_reminders_are_queued_and_delivered_by_smtp_email(self):
        self.database.applications.insert_one(
            {
                "id": "application-reminder",
                "user_id": "SS-2026-000005",
                "scholarship_id": "scheme-1",
                "scholarship_title": "Merit Support",
                "status": "submitted",
                "reminder_date": "2000-01-01",
                "reminder_queued_for": None,
            }
        )
        with patch(
            "app.routes.admin.dispatch_notification",
            side_effect=RuntimeError("SMTP is unavailable"),
        ):
            response = self.client.post(
                "/api/admin/notifications/dispatch",
                headers=self.admin_headers,
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["queued_reminders"], 1)
        self.assertEqual(response.json["failed"], 1)
        self.assertEqual(self.database.notifications.documents[0]["status"], "failed")
        self.assertEqual(self.database.notifications.documents[0]["channel"], "email")
        self.assertEqual(
            self.database.notifications.documents[0]["recipient"],
            "student@example.org",
        )
        with patch("app.routes.admin.dispatch_notification") as dispatch:
            response = self.client.post(
                "/api/admin/notifications/dispatch",
                headers=self.admin_headers,
            )
        self.assertEqual(response.json["sent"], 1)
        dispatch.assert_called_once()

    def test_approaching_scheme_deadline_queues_one_email_reminder(self):
        deadline = (datetime.now(timezone.utc).date() + timedelta(days=3)).isoformat()
        self.database.scholarships.documents[0]["deadline"] = deadline
        self.database.applications.insert_one(
            {
                "id": "application-deadline",
                "user_id": "SS-2026-000005",
                "scholarship_id": "scheme-1",
                "scholarship_title": "Merit Support",
                "status": "submitted",
                "reminder_date": None,
            }
        )
        with patch("app.routes.admin.dispatch_notification"):
            first = self.client.post(
                "/api/admin/notifications/dispatch",
                headers=self.admin_headers,
            )
            second = self.client.post(
                "/api/admin/notifications/dispatch",
                headers=self.admin_headers,
            )
        self.assertEqual(first.json["queued_reminders"], 1)
        self.assertEqual(second.json["queued_reminders"], 0)
        self.assertEqual(
            sum(
                item["idempotency_key"].startswith("deadline:")
                for item in self.database.notifications.documents
            ),
            1,
        )


if __name__ == "__main__":
    unittest.main()
