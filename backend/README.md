# Scholarship Support API

The Flask API provides student registration with email verification, login,
a protected current-account endpoint, and a searchable scholarship directory
with administrator-managed scholarship records. It also provides profiles and
eligibility matching, application tracking, in-memory document checking, help
and grievance tracking, ratings, verified-source chatbot answers, notifications,
admin analytics, and sourced survey result data. Student passwords and pending
email OTPs are stored as hashes. Verification codes expire after 10 minutes
and allow at most five attempts. The post-verification email contains the
unique student ID and never contains the student's password.

## Run locally

1. Create a MongoDB database and configure the environment variables shown in
   [`.env.example`](./.env.example). Copy it to `.env` and replace the example
   values; never commit `.env`.
2. To enable the optional Aadhaar signup field, generate a Fernet key with
   `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
   and set it as `AADHAAR_ENCRYPTION_KEY`. Keep it in a secrets manager, back it
   up securely, and keep it stable: losing or changing the key makes stored
   Aadhaar values unrecoverable. Do not commit the key. If the key is not set,
   users can register without Aadhaar, but providing Aadhaar is unavailable.
3. Generate a separate Fernet key for `DOCUMENT_ENCRYPTION_KEY` using the same
   command. This key is required to accept application documents; those files
   are encrypted before being stored in MongoDB. Back it up securely and keep
   it stable: losing it makes stored application documents unreadable. Never
   commit either encryption key.
4. Generate another separate Fernet key for `BANK_DETAILS_ENCRYPTION_KEY`.
   Student bank account and IFSC data are stored encrypted with this key.
   Keep it stable and backed up securely; losing it makes stored bank details
   unreadable. Never commit it.
5. Set `ADMIN_EMAILS` for application reviewers and `FINANCE_ADMIN_EMAILS`
   for the separate finance-only role. Use verified account email addresses.
   The finance role can access only approved application IDs, scholarship
   titles, the fixed amount, account number and IFSC; it cannot access student
   names, profile fields, or uploaded documents.
6. Configure an SMTP account. For Gmail, use an App Password rather than your
   regular account password.
7. Install dependencies with `pip install -r requirements.txt`.
8. Start MongoDB and run `python run.py`.
9. Run the backend tests with `python -m unittest discover -s tests -v`.

## Authentication endpoints

- `POST /api/auth/register` — requires `full_name`, `email`, `mobile`,
  `password`, `confirm_password`, `date_of_birth` (`YYYY-MM-DD`), `gender`
  (`female`, `male`, `other`, or `prefer_not_to_say`), and `consent: true`.
  The optional `aadhaar` field accepts exactly 12 digits and also requires
  `aadhaar_consent: true`. It is encrypted with Fernet before database storage
  and is never included in API responses or emails. The consent time is kept
  with the account. Returns `202` after sending the OTP.
- `POST /api/auth/verify-email` — requires `email` and the 6-digit `otp`.
  Returns the generated ID (`SS-YYYY-NNNNNN`) after activating the account.
- `POST /api/auth/forgot-password` — requires the account `email`. Sends a
  one-time password-reset code valid for 10 minutes. The response is the same
  whether or not an account exists for the email.
- `POST /api/auth/reset-password` — requires `email`, the 6-digit `otp`,
  `password`, and `confirm_password`. Allows at most five OTP attempts, updates
  only the password hash, and invalidates the reset code after use.
- `POST /api/auth/login` — requires an `identifier` (email address or student
  ID such as `SS-2026-000123` or verifier ID such as `CV-ABC123DEF456`) and
  `password`; the legacy `email` request field is also accepted and may contain
  either identifier. Returns a signed bearer token and the user's role.
- `GET /api/auth/me` — requires `Authorization: Bearer <token>` and returns
  server-authoritative admin/finance permission flags for navigation. Protected
  API routes still enforce access independently.

## Profiles and scholarship matching

Authenticated requests use `Authorization: Bearer <token>`.

- `GET /api/profile` and `PATCH /api/profile` — read/update the optional
  category, domicile, income range, course, year, college, marks, language,
  and alert channel profile. Aadhaar, PAN, and bank numbers are not accepted
  in profile data.
- `POST /api/profile/eligibility` — accepts `scholarship_id` and a profile
  object; returns eligible, not eligible, or missing-information criteria.
- `GET /api/profile/recommendations` — recommends schemes using the saved
  profile; `limit` ranges from 1 to 50. If category, education level, or
  Maharashtra domicile is missing, it returns an empty list and
  `missing_profile_fields` so the client can request profile completion.
- `GET /api/profile/compare?id=<id>&id=<id>` — compares two or three schemes.

## Scholarship directory and administration

- `GET /api/scholarships` — public, paginated directory. Supports `q`,
  `level`, `category`, `eligibility`, `deadline_before`, `deadline_after`,
  `sort=deadline|updated`, `page`, and `per_page` (1–100).
- `GET /api/scholarships/<id>` — public detail for an active scholarship.
- `GET /api/scholarships/admin` — administrator-only paginated list including
  inactive records.
- `POST /api/scholarships` — administrator-only create.
- `PATCH /api/scholarships/<id>` — administrator-only partial update.
- `DELETE /api/scholarships/<id>` — administrator-only archive; records are
  retained for existing trackers and audit history.
- `POST /api/scholarships/<id>/verification` — administrator records that the
  current scheme details have been checked against official guidelines. Any
  later scheme edit clears this review until it is checked again.

The admin form does not collect scheme source/application URLs. New records
therefore have no source URL. Admins must manually check scheme details against
official guidelines and mark records reviewed before they can appear in
chatbot answers. Existing URL values are retained when editing records;
official source URLs, when present, are included in chatbot responses.

Set `ADMIN_EMAILS` to a comma-separated allowlist of verified account email
addresses. The backend does not provide a self-service admin role. Scholarship
records include eligibility criteria, category, deadline, official and
application links, document checklist items, FAQs, and active/inactive status.
Verify scholarship criteria and deadlines against each scheme's official
guidelines before publishing them.

## College, application, and document workflows

- `POST /api/colleges/admin` — administrator-only creation of a verified
  college record and its first `college_verifier` account. Requires the
  college name/code, verifier name/email, and a password of at least 10
  characters. The password is stored as a hash; the admin shares the demo
  credentials with the verifier. Login accepts either the verifier email or
  generated `CV-...` account ID.
- `GET /api/colleges/admin` — administrator-only list of registered colleges
  and their verifier IDs/emails. Passwords are never returned.
- `DELETE /api/colleges/admin/<college_id>` — administrator-only deactivation.
  It removes the verifier account and prevents new applications while retaining
  the college record and historical applications. Pending applications for
  inactive colleges stay in the admin queue for follow-up review.
- `GET /api/colleges/list` — authenticated list of colleges registered for
  this prototype, used to assign an application to the correct verifier.
- College records created by the administrator are marked verified for this
  project prototype only. This does not confirm an institution with MahaDBT
  or a government authority.

- `POST /api/applications` — create a draft for an active `scholarship_id`,
  including the application form, bank account/IFSC, and explicit consent to
  encrypted document storage, bank-detail storage, and review/finance
  processing. A fixed demo payout amount is not required to submit; an
  administrator must configure one on the scholarship before approving an
  application for the finance simulation. If a draft already exists for the
  same student and scholarship, the API returns that draft so the student can
  continue instead of creating a duplicate tracker.
- On submission, the selected registered college is stored on the application.
  The flow is `submitted` → college verification → department/admin review.
  The college verifier can verify and forward (`college_verified`), request
  changes (`correction_required`), or reject with a note. Students may update
  and resubmit while corrections are requested. Only `college_verified`
  applications enter the department review queue for final approval/rejection.
  Department admins can also request corrections; those resubmissions return
  directly to the department queue without repeating college verification.
- `POST /api/colleges/admin` provisions verifier access; a verifier is linked
  to one college. `GET /api/colleges/applications` returns only that college's
  pending submissions. `POST /api/colleges/applications/<id>/review` records
  the verifier decision and audit details. The document endpoint
  `GET /api/colleges/applications/<id>/documents/<document_id>` only permits
  downloads for applications assigned to that verifier's college.
- Bank account and IFSC values are separately encrypted using
  `BANK_DETAILS_ENCRYPTION_KEY`. They are excluded from student, college, and
  department reviewer API responses. The finance-only allowlist receives only
  an application reference, scheme title, fixed amount, account number, and
  IFSC after department approval.
- `GET /api/applications`, `GET /api/applications/dashboard`, and
  `GET /api/applications/<id>` — read only the signed-in student's trackers.
- `POST /api/applications/<id>/documents` — multipart fields `document_name`
  and `file`; accepts PDF/JPG/PNG up to 8 MB, validates file contents, and
  encrypts files with `DOCUMENT_ENCRYPTION_KEY` before private MongoDB storage.
  Students can upload only documents named in the scheme checklist or the
  supported optional document list. Checklist documents must be uploaded
  before submission.
- `PATCH /api/applications/<id>` — students can submit a complete draft,
  resubmit a correction, and update tracker reminders/notes. Details are
  locked while the application is being reviewed.
- `GET /api/applications/admin` and `PATCH /api/applications/admin/<id>` —
  administrator-only review queue and final status update, including requests
  for student corrections. The queue includes applications waiting for college
  review and applications whose requested corrections are pending.
  Applications assigned to a college cannot be approved/rejected by department
  admins until the college marks them `college_verified`. Approval requires
  encrypted bank details and a configured fixed payout amount.
- `GET /api/applications/finance` and
  `POST /api/applications/finance/<id>/simulate-disbursement` — finance-only
  endpoints, restricted to `FINANCE_ADMIN_EMAILS`. The amount is fixed on the
  scheme record and copied to the application; finance staff cannot change it.
  The action is a **simulation only**: it records a demo status and sends a
  clearly labeled email, but does not connect to a bank or transfer money. If
  SMTP delivery fails, the email is retained in the retryable admin email
  queue.
- `GET /api/applications/admin/<id>/documents/<document_id>` — administrator
  only; decrypts an application file for download with `Cache-Control:
  no-store`.
- `GET /api/applications/<id>/timeline` — return status history and stage
  guidance. Application statuses are `draft`, `submitted`,
  `college_verified`, `correction_required`, `approved`, `rejected`, and
  `paid`.
- `POST /api/applications/documents/check` — multipart field `file`; accepts
  PDF/JPG/PNG up to 8 MB. Images are checked for blur and resized/compressed.
  This standalone precheck processes uploads in memory only. Documents
  submitted with an application are stored separately and encrypted for
  authorized college and department review. The admin-managed scheme checklist defines required documents;
  supported common documents can be uploaded optionally.
- `GET /api/applications/documents/upload-guide` — common upload errors and
  corrective steps.

The college and department workflow is an internal project prototype and
**payment simulation**, not a MahaDBT integration or payment service. Admin
registration verifies colleges only for this prototype; it is not official
institutional validation. “Approved” means the department administrator
approved the application's review in this website; the finance simulation is
not proof that money reached a bank account. Configure a retention/deletion
policy for uploaded supporting documents and bank details appropriate to your
deployment and jurisdiction.

## Student support and multilingual content

- `GET /api/chat?q=<question>&lang=en|hi|mr` — deterministic answers from
  active schemes explicitly source-verified by an admin. Unverified records
  are excluded; no generative answer is presented as scheme fact.
- `GET /api/guides/rejection?reason=<text>`, `/api/guides/payment`, and
  `/api/guides/college-verification` — general guidance; official portal
  notices remain authoritative.
- `POST /api/tickets`, `GET /api/tickets`, `GET /api/tickets/<id>` — create
  and track private help-centre tickets.
- `POST /api/grievances`, `GET /api/grievances`,
  `GET /api/grievances/<id>` — create and privately track grievances.
- `POST /api/feedback` and `GET /api/feedback/<scholarship_id>` — submit and
  read approved scheme ratings. New ratings remain pending until an
  administrator approves them.
- `GET /api/admin/feedback` and
  `PATCH /api/admin/feedback/<feedback_id>` — administrator feedback review
  and moderation (`moderation_status: approved|rejected`).
- `GET /api/tutorials?lang=en|hi|mr` — list published language-specific video
  tutorials. Administrators can list all published and draft tutorials with
  `GET /api/admin/tutorials` and create/update them with
  `POST`/`PATCH /api/admin/tutorials`.
- Admins manage support tickets and grievances with
  `/api/admin/tickets` and `/api/admin/grievances` endpoints.
- Scholarship translations for `en`, `hi`, and `mr` can be entered while
  creating/updating a scheme. The chatbot uses those translations when present.

## Notifications, analytics, and survey results

- College verification, correction requests, and rejections, plus admin
  approvals, correction requests, and rejections, send an email to the student
  immediately when SMTP is configured. Failed deliveries remain queued for
  retry. Other application status changes queue email alerts. Configure SMTP and run
  `POST /api/admin/notifications/dispatch` periodically (for example, from a
  protected scheduled job) to deliver queued messages and due reminders.
  Failed deliveries are retained with an error and can be retried by dispatch.
- All alerts, reminders, status updates, and verification codes use SMTP email.
  SMS/WhatsApp and paid Twilio integrations are intentionally not included.
- `GET /api/admin/analytics` — admin-only, chart-ready counts for students,
  schemes, application stages, and support workload.
- Admins publish sourced research survey data with `POST /api/admin/surveys`.
  `GET /api/surveys/results` returns published chart labels and counts; the
  API does not fabricate survey responses.

The registration form offers Aadhaar as an optional field. Supplying it
requires explicit consent and a configured encryption key; only ciphertext is
stored, and the application does not display, return, or email the number.
PAN and bank account details are not collected. The scholarship website is a
tracker and guidance service, not the official MahaDBT application portal.
Review applicable privacy and Aadhaar-handling requirements before production
deployment.
