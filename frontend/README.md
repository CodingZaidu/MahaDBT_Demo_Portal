# Scholarship Support frontend

Responsive React interface for the Scholarship Support Flask API.

## Run locally

1. Start the backend from `backend/` with `python run.py` (the default API
   address is `http://127.0.0.1:5000`).
2. From `frontend/`, install dependencies with `npm install`.
3. Start the Vite development server with `npm run dev`.
4. Open the local URL printed by Vite.

Vite proxies `/api` requests to the local Flask backend. To use a different
backend address, update `server.proxy` in `vite.config.js`.

Build the static frontend bundle with `npm run build`; the output is written
to `dist/`. Run the translation helper tests with `npm test`.

The interface includes student registration with email OTP verification,
login, scholarship search and comparison, application tracking, profile
management, the verified-scheme assistant, and support guides, tickets, and
grievances. It also includes document checks, eligibility estimates,
recommendations, application timelines, ratings, survey charts, and an
installable offline app shell. For the project prototype, an administrator can
register colleges and create verifier accounts; students submit applications
to the selected college, and verified applications move to department review.
College and department decisions can email students when SMTP is configured.
Applications are locked after submission until the college or administrator
requests corrections. The admin review screen separates pending, approved,
rejected, and correction-requested cases and opens full details on demand.
This internal workflow does not submit to or integrate with the official
MahaDBT portal. Backend-backed data and uploads require a network connection.

The interface supports English, Hindi, and Marathi, and remembers the selected
language in the browser. Assistant prompts, built-in guidance, and tutorial
lists follow the selected language. The dashboard lists active schemes whose
deadline is today or later; scholarships without a deadline are not presented
as currently open. Student and admin district selectors use the 36
alphabetically ordered Maharashtra districts. The administrator area provides
Chart.js analytics, scholarship and college/verifier management, application
department review, support and grievance status updates, feedback review,
survey/tutorial publishing, and queued email dispatch. College verifier
accounts can access only their assigned college's application queue and
documents.
The scholarship form omits official-source and application URL fields; new
schemes must be manually reviewed against their official guidelines in the
admin directory before chatbot answers can use them. Administrator
access depends on the signed-in email being listed in the backend
`ADMIN_EMAILS` configuration. Feedback can be approved or rejected; new ratings
remain out of public aggregates until approved. Admins can also edit, publish,
and unpublish tutorials, including drafts.

In the scholarship editor, directory categories, eligibility categories, and
eligible courses are selected from multi-select lists rather than typed as
comma-separated values. Eligibility summary is the short, student-facing
overview shown on scholarship cards and in assistant responses.
