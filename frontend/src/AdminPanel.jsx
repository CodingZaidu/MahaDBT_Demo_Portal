import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Bar,
  Doughnut,
} from "react-chartjs-2";
import {
  ArcElement,
  BarElement,
  CategoryScale,
  Chart as ChartJS,
  Filler,
  Legend,
  LinearScale,
  PointElement,
  Tooltip,
} from "chart.js";
import {
  Archive,
  ArrowDownUp,
  ArrowRight,
  Check,
  CheckCircle2,
  CircleHelp,
  FileText,
  LoaderCircle,
  Megaphone,
  MessageCircle,
  Pencil,
  Plus,
  RefreshCw,
  Save,
  Send,
  ShieldCheck,
  Star,
  Trash2,
  Users,
  X,
} from "lucide-react";
import { getLocale, t } from "./i18n.js";
import { districtLabel, MAHARASHTRA_DISTRICTS, normalizeDistrictNames } from "./districts.js";

ChartJS.register(ArcElement, BarElement, CategoryScale, Filler, Legend, LinearScale, PointElement, Tooltip);

const STATUSES = ["draft", "submitted", "college_verified", "correction_required", "approved", "rejected", "paid"];
const STATUS_LABELS = {
  draft: "Draft",
  submitted: "Submitted",
  college_verified: "College verified",
  correction_required: "Correction required",
  approved: "Approved",
  rejected: "Rejected",
  paid: "Paid",
};
const LANGUAGES = ["en", "hi", "mr"];
const SCHOLARSHIP_CATEGORIES = ["open", "obc", "sc", "st", "vjnt", "sbc", "ews", "minority"];
const COURSE_OPTIONS = [
  "Agriculture",
  "B.A. (Bachelor of Arts)",
  "B.Arch. (Bachelor of Architecture)",
  "B.B.A. (Bachelor of Business Administration)",
  "B.C.A. (Bachelor of Computer Applications)",
  "B.Com. (Bachelor of Commerce)",
  "B.D.S. (Bachelor of Dental Surgery)",
  "B.Des. (Bachelor of Design)",
  "B.Ed. (Bachelor of Education)",
  "B.E. (Bachelor of Engineering)",
  "B.F.A. (Bachelor of Fine Arts)",
  "B.H.M.S. (Bachelor of Homeopathic Medicine)",
  "B.Pharma. (Bachelor of Pharmacy)",
  "B.P.T. (Bachelor of Physiotherapy)",
  "B.Sc. (Bachelor of Science)",
  "B.Tech. (Bachelor of Technology)",
  "B.Voc. (Bachelor of Vocation)",
  "Commerce",
  "Computer Applications",
  "D.El.Ed. (Diploma in Elementary Education)",
  "Design",
  "Diploma",
  "Education",
  "Engineering",
  "Fine Arts",
  "Hotel Management",
  "ITI",
  "Law",
  "Management",
  "M.A. (Master of Arts)",
  "M.Arch. (Master of Architecture)",
  "M.B.A. (Master of Business Administration)",
  "M.C.A. (Master of Computer Applications)",
  "M.Com. (Master of Commerce)",
  "M.D. (Doctor of Medicine)",
  "M.Ed. (Master of Education)",
  "M.E. (Master of Engineering)",
  "M.F.A. (Master of Fine Arts)",
  "M.Pharma. (Master of Pharmacy)",
  "M.Phil. (Master of Philosophy)",
  "M.Sc. (Master of Science)",
  "M.Tech. (Master of Technology)",
  "LL.B. (Bachelor of Laws)",
  "LL.M. (Master of Laws)",
  "Medicine",
  "Nursing",
  "Ph.D. (Doctor of Philosophy)",
  "Other undergraduate course",
  "Other postgraduate course",
  "Other school course",
  "Pharmacy",
  "Physiotherapy",
  "Science",
  "Social Work",
  "Veterinary Science",
];
const SORTED_COURSE_OPTIONS = [...COURSE_OPTIONS].sort((first, second) => first.localeCompare(second));
const DEFAULT_SCHOLARSHIP = {
  title: "",
  provider: "",
  description: "",
  education_level: "undergraduate",
  categories: ["open"],
  eligibility_summary: "",
  eligibility_categories: [],
  income_max: "",
  minimum_percentage: "",
  courses: [],
  study_years: "",
  districts: [],
  maharashtra_domicile: "",
  minority: "",
  divyang: "",
  award_amount: "",
  payout_amount: "",
  deadline: "",
  official_url: "",
  application_url: "",
  documents: "",
  faqs: "",
  translations: "{}",
};

async function adminApi(path, token, options = {}) {
  const headers = new Headers(options.headers || {});
  if (options.body && !(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
  headers.set("Authorization", `Bearer ${token}`);
  let response;
  try {
    response = await fetch(path, { ...options, headers });
  } catch (error) {
    throw new Error(`Could not reach ${path}. Confirm the backend is running and try again.`, { cause: error });
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(`${path} returned ${response.status}: ${data.error || response.statusText || "The admin request failed."}`);
    error.status = response.status;
    error.code = data.code;
    throw error;
  }
  return data;
}

async function updateTutorialStatus(tutorial) {
  const status = tutorial.status === "published" ? "draft" : "published";
  try {
    await adminApi(`/api/admin/tutorials/${tutorial.id}`, token, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    });
    notify(status === "published" ? "Video tutorial published." : "Video tutorial moved to drafts.");
    refresh();
  } catch (requestError) {
    notify(requestError.message);
  }
}

function blankAnalytics() {
  return {
    students: 0,
    scholarships: { total: 0, active: 0, verified: 0 },
    applications: { total: 0, by_status: {} },
    most_tracked_scholarships: [],
    support: { open_tickets: 0, open_grievances: 0 },
    feedback: { count: 0, average_rating: null, rating_distribution: {} },
  };
}

function dateLabel(value) {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : new Intl.DateTimeFormat(`${getLocale()}-IN`, { dateStyle: "medium" }).format(parsed);
}

function toList(value) {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

function parseJsonObject(value, label) {
  try {
    const parsed = JSON.parse(value || "{}");
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error();
    return parsed;
  } catch {
    throw new Error(`${label} must be a valid JSON object.`);
  }
}

function scholarshipToForm(scheme) {
  const eligibility = scheme.eligibility || {};
  return {
    title: scheme.title || "",
    provider: scheme.provider || "",
    description: scheme.description || "",
    education_level: scheme.education_level || "undergraduate",
    categories: scheme.categories || [],
    eligibility_summary: scheme.eligibility_summary || "",
    eligibility_categories: eligibility.categories || [],
    income_max: eligibility.income_max ?? "",
    minimum_percentage: eligibility.minimum_percentage ?? "",
    courses: eligibility.courses || [],
    study_years: (eligibility.study_years || []).join(", "),
    districts: normalizeDistrictNames(eligibility.districts || []),
    maharashtra_domicile: eligibility.maharashtra_domicile == null ? "" : String(eligibility.maharashtra_domicile),
    minority: eligibility.minority == null ? "" : String(eligibility.minority),
    divyang: eligibility.divyang == null ? "" : String(eligibility.divyang),
    award_amount: scheme.award_amount || "",
    payout_amount: scheme.payout_amount || "",
    deadline: scheme.deadline || "",
    official_url: scheme.official_url || "",
    application_url: scheme.application_url || "",
    documents: (scheme.documents || []).join(", "),
    faqs: (scheme.faqs || []).map((item) => `${item.question} | ${item.answer}`).join("\n"),
    translations: JSON.stringify(scheme.translations || {}, null, 2),
  };
}

function scholarshipPayload(form) {
  const faqs = form.faqs.split("\n").map((line) => line.trim()).filter(Boolean).map((line) => {
    const [question, ...answer] = line.split("|");
    if (!question?.trim() || !answer.join("|").trim()) throw new Error("Write each FAQ as: question | answer.");
    return { question: question.trim(), answer: answer.join("|").trim() };
  });
  return {
    title: form.title,
    provider: form.provider,
    description: form.description,
    education_level: form.education_level,
    categories: form.categories,
    eligibility_summary: form.eligibility_summary,
    eligibility: {
      categories: form.eligibility_categories,
      ...(form.income_max !== "" ? { income_max: Number(form.income_max) } : {}),
      ...(form.minimum_percentage !== "" ? { minimum_percentage: Number(form.minimum_percentage) } : {}),
      courses: form.courses,
      study_years: toList(form.study_years).map(Number),
      districts: form.districts,
      ...(form.maharashtra_domicile !== "" ? { maharashtra_domicile: form.maharashtra_domicile === "true" } : {}),
      ...(form.minority !== "" ? { minority: form.minority === "true" } : {}),
      ...(form.divyang !== "" ? { divyang: form.divyang === "true" } : {}),
    },
    award_amount: form.award_amount || null,
    payout_amount: form.payout_amount || null,
    deadline: form.deadline || null,
    official_url: form.official_url || null,
    application_url: form.application_url || null,
    documents: toList(form.documents),
    faqs,
    translations: parseJsonObject(form.translations, "Translations"),
  };
}

function ChartOptions(horizontal = false) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    indexAxis: horizontal ? "y" : "x",
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: "#202a46",
        padding: 10,
        titleFont: { family: "DM Sans", size: 11 },
        bodyFont: { family: "DM Sans", size: 10 },
      },
    },
    scales: horizontal
      ? {
          x: { beginAtZero: true, border: { display: false }, grid: { color: "#eff1f6" }, ticks: { precision: 0, color: "#8d95a6", font: { family: "DM Sans", size: 9 } } },
          y: { border: { display: false }, grid: { display: false }, ticks: { color: "#707b90", font: { family: "DM Sans", size: 9 } } },
        }
      : {
          x: { border: { display: false }, grid: { display: false }, ticks: { color: "#8d95a6", font: { family: "DM Sans", size: 9 } } },
          y: { beginAtZero: true, border: { display: false }, grid: { color: "#eff1f6" }, ticks: { precision: 0, color: "#8d95a6", font: { family: "DM Sans", size: 9 } } },
        },
  };
}

const COLORS = ["#6b5bd4", "#45a787", "#f0ac61", "#7190df", "#e37d72", "#a58bce"];

function AdminPanel({ token, notify }) {
  const locale = getLocale();
  const [tab, setTab] = useState("overview");
  const [analytics, setAnalytics] = useState(blankAnalytics());
  const [scholarships, setScholarships] = useState([]);
  const [pendingApproval, setPendingApproval] = useState(null);
  const [tickets, setTickets] = useState([]);
  const [grievances, setGrievances] = useState([]);
  const [feedback, setFeedback] = useState([]);
  const [tutorials, setTutorials] = useState([]);
  const [notifications, setNotifications] = useState([]);
  const [applications, setApplications] = useState([]);
  const [colleges, setColleges] = useState([]);
  const [collegeForm, setCollegeForm] = useState({ name: "", code: "", verifier_name: "", verifier_email: "", verifier_password: "" });
  const [documentPreview, setDocumentPreview] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [modal, setModal] = useState("");
  const [editing, setEditing] = useState(null);
  const [saving, setSaving] = useState(false);
  const [scholarshipForm, setScholarshipForm] = useState(DEFAULT_SCHOLARSHIP);
  const [editingTutorial, setEditingTutorial] = useState(null);
  const [tutorialForm, setTutorialForm] = useState({ title: "", description: "", language: "en", video_url: "", status: "published", order: "100" });
  const [surveyForm, setSurveyForm] = useState({ title: "", question: "", language: "en", respondents: "", survey_date: "", source_url: "", status: "published", options: "Option one | 0\nOption two | 0" });
  const [dispatching, setDispatching] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    const requests = [
      ["/api/admin/analytics", (result) => setAnalytics(result)],
      ["/api/scholarships/admin?per_page=100", (result) => setScholarships(result.items || [])],
      ["/api/admin/tickets", (result) => setTickets(result.tickets || [])],
      ["/api/admin/grievances", (result) => setGrievances(result.grievances || [])],
      ["/api/admin/feedback", (result) => setFeedback(result.feedback || [])],
      ["/api/admin/tutorials", (result) => setTutorials(result.tutorials || [])],
      ["/api/admin/notifications", (result) => setNotifications(result.notifications || [])],
      ["/api/applications/admin", (result) => setApplications(result.applications || [])],
      ["/api/colleges/admin", (result) => setColleges(result.colleges || [])],
    ];
    const results = await Promise.allSettled(
      requests.map(([path]) => adminApi(path, token)),
    );
    const failures = [];
    results.forEach((result, index) => {
      if (result.status === "fulfilled") requests[index][1](result.value);
      else failures.push(result.reason.message);
    });
    setError(failures.join(" "));
    setLoading(false);
  }, [token]);
  useEffect(() => { refresh(); }, [refresh]);
  useEffect(() => () => {
    if (documentPreview?.url) URL.revokeObjectURL(documentPreview.url);
  }, [documentPreview]);

  const statusChart = useMemo(() => ({
    labels: STATUSES.map((status) => t(STATUS_LABELS[status])),
    datasets: [{
      label: "Applications",
      data: STATUSES.map((status) => analytics.applications.by_status?.[status] || 0),
      backgroundColor: COLORS,
      borderRadius: 5,
      maxBarThickness: 36,
    }],
  }), [analytics, locale]);

  const supportChart = useMemo(() => ({
    labels: [t("Help tickets"), t("Grievances")],
    datasets: [{
      data: [analytics.support.open_tickets || 0, analytics.support.open_grievances || 0],
      backgroundColor: ["#6b5bd4", "#f0ac61"],
      borderColor: "#fff",
      borderWidth: 4,
      hoverOffset: 5,
    }],
  }), [analytics, locale]);

  async function saveScholarship(event) {
    event.preventDefault();
    setSaving(true);
    try {
      const payload = scholarshipPayload(scholarshipForm);
      await adminApi(editing ? `/api/scholarships/${editing.id}` : "/api/scholarships", token, {
        method: editing ? "PATCH" : "POST",
        body: JSON.stringify(payload),
      });
      const approvalToRetry = pendingApproval && editing?.id === pendingApproval.application.scholarship_id
        ? pendingApproval
        : null;
      if (approvalToRetry) setPendingApproval(null);
      else notify(editing ? "Scholarship updated. Source verification needs to be repeated." : "Scholarship created.");
      setModal("");
      setEditing(null);
      setScholarshipForm(DEFAULT_SCHOLARSHIP);
      refresh();
      if (approvalToRetry) {
        await submitApplicationReview(
          approvalToRetry.application,
          "approved",
          approvalToRetry.admin_note,
        );
      }
    } catch (requestError) {
      notify(requestError.message);
    } finally {
      setSaving(false);
    }
  }

  async function verifyScheme(scheme) {
    if (!window.confirm(`${t("Have you checked")} "${scheme.title}" ${t("against its official scheme guidelines? Only mark it reviewed after confirming the eligibility and deadline.")}`)) return;
    try {
      await adminApi(`/api/scholarships/${scheme.id}/verification`, token, {
        method: "POST",
        body: JSON.stringify({ verified: true }),
      });
      notify("Scholarship marked as administrator-reviewed.");
      refresh();
    } catch (requestError) {
      notify(requestError.message);
    }
  }

  async function archiveScheme(scheme) {
    if (!window.confirm(`Archive "${scheme.title}"? Existing application trackers will be retained.`)) return;
    try {
      await adminApi(`/api/scholarships/${scheme.id}`, token, { method: "DELETE" });
      notify("Scholarship archived.");
      refresh();
    } catch (requestError) {
      notify(requestError.message);
    }
  }

  async function updateSupportRecord(kind, record, status) {
    const path = kind === "ticket" ? `/api/admin/tickets/${record.id}` : `/api/admin/grievances/${record.id}`;
    const payload = kind === "ticket"
      ? { status, admin_note: record.admin_note || "" }
      : { status, resolution_note: record.resolution_note || "" };
    try {
      await adminApi(path, token, { method: "PATCH", body: JSON.stringify(payload) });
      notify(`${kind === "ticket" ? "Ticket" : "Grievance"} status updated.`);
      refresh();
    } catch (requestError) {
      notify(requestError.message);
    }
  }

  function editScholarshipForApproval(application, admin_note) {
    const scholarship = scholarships.find((item) => item.id === application.scholarship_id);
    if (!scholarship) return false;
    setPendingApproval({ application, admin_note });
    setEditing(scholarship);
    setScholarshipForm(scholarshipToForm(scholarship));
    setModal("scholarship");
    notify(t("Set the fixed demo amount; approval will continue after you save."));
    return true;
  }

  async function submitApplicationReview(application, status, admin_note, rejection_reason) {
    try {
      const result = await adminApi(`/api/applications/admin/${application.id}`, token, {
        method: "PATCH",
        body: JSON.stringify({
          status,
          ...(rejection_reason ? { rejection_reason } : {}),
          admin_note,
        }),
      });
      const statusMessage = t(status === "approved"
        ? "Application approved. Fund distribution is still pending."
        : status === "rejected"
          ? "Application rejected with a reason."
          : status === "correction_required"
            ? "Correction request sent to the student."
            : "Application status updated.");
      const emailMessage = result.email_status === "sent"
        ? t("Email sent to student.")
        : result.email_status === "failed"
          ? t("Email could not be sent; it is queued for retry.")
          : "";
      notify([statusMessage, emailMessage].filter(Boolean).join(" "));
      refresh();
    } catch (requestError) {
      if (status === "approved" && requestError.status === 409
        && requestError.code === "missing_fixed_payout_amount") {
        if (editScholarshipForApproval(application, admin_note)) return;
      }
      notify(requestError.message);
    }
  }

  async function reviewApplication(application, status) {
    const rejection_reason = status === "rejected"
      ? window.prompt(t("Enter the reason that should be shown to the student:"))?.trim()
      : undefined;
    if (status === "rejected" && !rejection_reason) return;
    const admin_note = status === "correction_required"
      ? window.prompt(t("Describe the changes the student must make:"))?.trim()
      : window.prompt(t("Optional note for the student:"), application.admin_note || "");
    if (admin_note === null || (status === "correction_required" && !admin_note)) return;
    if (status === "approved") {
      const scholarship = scholarships.find((item) => item.id === application.scholarship_id);
      if (scholarship && !scholarship.payout_amount) {
        editScholarshipForApproval(application, admin_note);
        return;
      }
    }
    await submitApplicationReview(application, status, admin_note, rejection_reason);
  }

  async function createCollege(event) {
    event.preventDefault();
    setSaving(true);
    try {
      const result = await adminApi("/api/colleges/admin", token, {
        method: "POST",
        body: JSON.stringify(collegeForm),
      });
      notify(`${t("College verifier account created.")} ${t("Login ID:")} ${result.verifier.user_id}`);
      setCollegeForm({ name: "", code: "", verifier_name: "", verifier_email: "", verifier_password: "" });
      await refresh();
    } catch (requestError) {
      notify(requestError.message);
    } finally {
      setSaving(false);
    }
  }

  async function deleteCollege(college) {
    if (!window.confirm(t("Delete this college and its verifier account? Colleges with existing applications will be deactivated instead so their application history is preserved."))) return;
    try {
      const result = await adminApi(`/api/colleges/admin/${college.id}`, token, { method: "DELETE" });
      notify(t(result.deleted ? "College and verifier account deleted." : "College had applications; verifier access removed and history retained."));
      await refresh();
    } catch (requestError) {
      notify(requestError.message);
    }
  }

  async function previewApplicationDocument(application, document) {
      try {
        const response = await fetch(`/api/applications/admin/${application.id}/documents/${document.id}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!response.ok) {
          const data = await response.json().catch(() => ({}));
          throw new Error(data.error || "Could not load this document.");
        }
        const blob = await response.blob();
        setDocumentPreview({
          url: URL.createObjectURL(blob),
          mime_type: document.mime_type,
          filename: document.filename,
        });
      } catch (requestError) {
        notify(requestError.message);
      }
  }

  async function saveTutorial(event) {
    event.preventDefault();
    setSaving(true);
    try {
      await adminApi(editingTutorial ? `/api/admin/tutorials/${editingTutorial.id}` : "/api/admin/tutorials", token, {
        method: editingTutorial ? "PATCH" : "POST",
        body: JSON.stringify({ ...tutorialForm, order: Number(tutorialForm.order) }),
      });
      notify(editingTutorial ? "Video tutorial updated." : "Video tutorial published.");
      setEditingTutorial(null);
      setTutorialForm({ title: "", description: "", language: "en", video_url: "", status: "published", order: "100" });
      refresh();
    } catch (requestError) {
      notify(requestError.message);
    } finally {
      setSaving(false);
    }
  }

  async function saveSurvey(event) {
    event.preventDefault();
    setSaving(true);
    try {
      const options = surveyForm.options.split("\n").map((line) => line.trim()).filter(Boolean).map((line) => {
        const [label, count] = line.split("|");
        if (!label?.trim() || count === undefined || !Number.isInteger(Number(count)) || Number(count) < 0) {
          throw new Error("Write survey options as: label | response count.");
        }
        return { label: label.trim(), count: Number(count) };
      });
      await adminApi("/api/admin/surveys", token, {
        method: "POST",
        body: JSON.stringify({
          title: surveyForm.title,
          question: surveyForm.question,
          language: surveyForm.language,
          respondents: Number(surveyForm.respondents),
          options,
          source_url: surveyForm.source_url,
          survey_date: surveyForm.survey_date,
          status: surveyForm.status,
        }),
      });
      notify("Survey result saved.");
      setSurveyForm({ title: "", question: "", language: "en", respondents: "", survey_date: "", source_url: "", status: "published", options: "Option one | 0\nOption two | 0" });
      refresh();
    } catch (requestError) {
      notify(requestError.message);
    } finally {
      setSaving(false);
    }
  }

  async function dispatchEmails() {
    if (!window.confirm("Send queued notifications and due reminders by email now?")) return;
    setDispatching(true);
    try {
      const result = await adminApi("/api/admin/notifications/dispatch?channel=email", token, { method: "POST" });
      notify(`Email dispatch complete: ${result.sent} sent, ${result.failed} failed.`);
      refresh();
    } catch (requestError) {
      notify(requestError.message);
    } finally {
      setDispatching(false);
    }
  }

  const tabs = [
    ["overview", t("Overview"), ShieldCheck],
    ["applications", t("Applications to review"), FileText],
    ["colleges", t("Colleges & verifiers"), Users],
    ["scholarships", t("Scholarships"), FileText],
    ["support", t("Support requests"), MessageCircle],
    ["feedback", t("Feedback"), Star],
    ["content", t("Content & surveys"), Megaphone],
    ["notifications", t("Email queue"), Send],
  ];

  return (
    <>
      <div className="admin-heading">
        <div><div className="eyebrow">ADMINISTRATION</div><h1>Control centre</h1><p>Manage verified scheme information and student support workflows.</p></div>
        <button className="button button-outline" onClick={refresh} disabled={loading}><RefreshCw size={15} className={loading ? "spin" : ""} /> Refresh data</button>
      </div>
      <div className="admin-tabs" role="tablist">{tabs.map(([value, label, Icon]) => <button key={value} className={tab === value ? "admin-tab-active" : ""} onClick={() => setTab(value)}><Icon size={15} />{label}</button>)}</div>
      {error && <div className="admin-error"><CircleHelp size={17} /><span>{error}</span>{error.includes("Administrator access") && <span>Sign in with a verified address listed in the backend ADMIN_EMAILS configuration.</span>}<button onClick={refresh}>Retry</button></div>}
      {loading && !error ? <div className="admin-loading"><LoaderCircle size={20} className="spin" /> Loading admin data…</div> : null}
      {!loading && <>
        {tab === "overview" && <AdminOverview analytics={analytics} statusChart={statusChart} supportChart={supportChart} />}
        {tab === "applications" && <ApplicationReviewManagement applications={applications} onReview={reviewApplication} onViewDocument={previewApplicationDocument} />}
        {tab === "colleges" && <CollegeManagement colleges={colleges} form={collegeForm} setForm={setCollegeForm} onSubmit={createCollege} onDelete={deleteCollege} saving={saving} />}
        {tab === "scholarships" && <ScholarshipManagement scholarships={scholarships} onCreate={() => { setEditing(null); setScholarshipForm(DEFAULT_SCHOLARSHIP); setModal("scholarship"); }} onEdit={(scheme) => { setEditing(scheme); setScholarshipForm(scholarshipToForm(scheme)); setModal("scholarship"); }} onVerify={verifyScheme} onArchive={archiveScheme} />}
        {tab === "support" && <SupportManagement tickets={tickets} grievances={grievances} onUpdate={updateSupportRecord} />}
        {tab === "feedback" && <FeedbackManagement feedback={feedback} scholarships={scholarships} onModerate={async (item, moderation_status) => {
          try {
            await adminApi(`/api/admin/feedback/${item.id}`, token, { method: "PATCH", body: JSON.stringify({ moderation_status }) });
            notify(moderation_status === "approved" ? "Feedback approved." : "Feedback rejected.");
            refresh();
          } catch (requestError) {
            notify(requestError.message);
          }
        }} />}
        {tab === "content" && <ContentManagement tutorials={tutorials} tutorialForm={tutorialForm} setTutorialForm={setTutorialForm} editingTutorial={editingTutorial} onEditTutorial={(tutorial) => { setEditingTutorial(tutorial); setTutorialForm({ title: tutorial.title, description: tutorial.description, language: tutorial.language, video_url: tutorial.video_url, status: tutorial.status, order: String(tutorial.order ?? 100) }); }} onCancelTutorialEdit={() => { setEditingTutorial(null); setTutorialForm({ title: "", description: "", language: "en", video_url: "", status: "published", order: "100" }); }} onToggleTutorial={updateTutorialStatus} onSaveTutorial={saveTutorial} surveyForm={surveyForm} setSurveyForm={setSurveyForm} onSaveSurvey={saveSurvey} saving={saving} />}
        {tab === "notifications" && <NotificationManagement notifications={notifications} dispatching={dispatching} onDispatch={dispatchEmails} />}
      </>}
      {modal === "scholarship" && <ScholarshipEditor form={scholarshipForm} setForm={setScholarshipForm} editing={editing} saving={saving} onClose={() => { setPendingApproval(null); setModal(""); }} onSubmit={saveScholarship} />}
      {documentPreview && <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && setDocumentPreview(null)}><section className="document-preview-modal" role="dialog" aria-modal="true" aria-label={documentPreview.filename}><div className="modal-heading"><div><div className="eyebrow">{t("PRIVATE APPLICATION DOCUMENT")}</div><h2>{documentPreview.filename}</h2></div><button className="icon-button" onClick={() => setDocumentPreview(null)} aria-label={t("Close document preview")}><X size={20} /></button></div>{documentPreview.mime_type.startsWith("image/") ? <img src={documentPreview.url} alt={documentPreview.filename} /> : <iframe src={documentPreview.url} title={documentPreview.filename} />}</section></div>}
    </>
  );
}

function AdminOverview({ analytics, statusChart, supportChart }) {
  const cards = [
    { icon: Users, label: t("Verified students"), value: analytics.students, tone: "blue" },
    { icon: FileText, label: t("Active scholarships"), value: analytics.scholarships.active, tone: "purple" },
    { icon: CheckCircle2, label: t("Admin reviewed"), value: analytics.scholarships.verified, tone: "green" },
    { icon: Star, label: t("Average rating"), value: analytics.feedback.average_rating ?? "—", detail: `${analytics.feedback.count} ${t("ratings")}`, tone: "orange" },
  ];
  const tracked = analytics.most_tracked_scholarships || [];
  const topChart = {
    labels: tracked.map((item) => item.title.length > 28 ? `${item.title.slice(0, 27)}…` : item.title),
    datasets: [{
      data: tracked.map((item) => item.applications),
      backgroundColor: "#7669dc",
      borderRadius: 5,
      maxBarThickness: 25,
    }],
  };
  return <>
    <div className="admin-stat-grid">{cards.map(({ icon: Icon, label, value, detail, tone }) => <div className="admin-stat-card" key={label}><div className={`admin-stat-icon admin-tone-${tone}`}><Icon size={17} /></div><span>{label}</span><strong>{value}</strong><small>{detail || `${analytics.scholarships.total} ${t("total schemes")}`}</small></div>)}</div>
    <div className="admin-chart-grid"><section className="panel admin-chart-card"><div className="section-heading"><div><div className="eyebrow">APPLICATION PIPELINE</div><h2>Application status</h2></div></div><div className="admin-chart"><Bar data={statusChart} options={ChartOptions()} /></div></section><section className="panel admin-chart-card admin-support-chart"><div className="section-heading"><div><div className="eyebrow">STUDENT SUPPORT</div><h2>Open requests</h2></div></div><div className="admin-doughnut"><Doughnut data={supportChart} options={{ responsive: true, maintainAspectRatio: false, cutout: "72%", plugins: { legend: { display: false }, tooltip: ChartOptions().plugins.tooltip } }} /><div className="doughnut-center"><strong>{(analytics.support.open_tickets || 0) + (analytics.support.open_grievances || 0)}</strong><span>{t("open")}</span></div></div><div className="chart-legend"><span><i className="legend-purple" /> {t("Help tickets")} <strong>{analytics.support.open_tickets || 0}</strong></span><span><i className="legend-orange" /> {t("Grievances")} <strong>{analytics.support.open_grievances || 0}</strong></span></div></section></div>
    <section className="panel admin-chart-card admin-top-schemes"><div className="section-heading"><div><div className="eyebrow">STUDENT INTEREST</div><h2>Most tracked scholarships</h2></div></div>{tracked.length ? <div className="admin-top-chart"><Bar data={topChart} options={ChartOptions(true)} /></div> : <div className="admin-no-data">Application tracking data will appear here once students add schemes.</div>}</section>
  </>;
}

function ScholarshipManagement({ scholarships, onCreate, onEdit, onVerify, onArchive }) {
  return (
    <section className="panel admin-table-panel">
      <div className="section-heading">
        <div><div className="eyebrow">DIRECTORY MANAGEMENT</div><h2>Scholarship schemes</h2></div>
        <button className="button button-primary button-small" onClick={onCreate}><Plus size={15} /> Add scholarship</button>
      </div>
      {scholarships.length ? (
        <div className="admin-table-scroll">
          <table className="admin-table">
            <thead><tr><th>Scheme</th><th>Level</th><th>Deadline</th><th>Publication</th><th>Source</th><th>Actions</th></tr></thead>
            <tbody>{scholarships.map((scheme) => (
              <tr key={scheme.id}>
                <td><strong>{scheme.title}</strong><span>{scheme.provider}</span></td>
                <td>{scheme.education_level}</td>
                <td>{dateLabel(scheme.deadline)}</td>
                <td><span className={`admin-chip ${scheme.status === "active" ? "chip-active" : "chip-inactive"}`}>{scheme.status}</span></td>
                <td>{scheme.verified_at
                  ? <span className="admin-verified"><ShieldCheck size={14} /> Verified</span>
                  : <span className="admin-unverified">{t("Needs review")}</span>}
                </td>
                <td><div className="admin-row-actions">
                  <button className="icon-button" title="Edit scholarship" aria-label="Edit scholarship" onClick={() => onEdit(scheme)}><Pencil size={15} /></button>
                  {!scheme.verified_at && scheme.status === "active" && <button className="icon-button verify-action" title="Mark reviewed after checking official guidelines" aria-label="Mark reviewed after checking official guidelines" onClick={() => onVerify(scheme)}><CheckCircle2 size={15} /></button>}
                  {scheme.status === "active" && <button className="icon-button archive-action" title="Archive scholarship" aria-label="Archive scholarship" onClick={() => onArchive(scheme)}><Archive size={15} /></button>}
                </div></td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      ) : <div className="admin-no-data">{t("No scholarships yet. Add scheme details to build the directory.")}</div>}
    </section>
  );
}

function ApplicationReviewManagement({ applications, onReview, onViewDocument }) {
  const [filter, setFilter] = useState("pending");
  const [openApplicationId, setOpenApplicationId] = useState("");
  const pending = applications.filter((application) =>
    application.status === "college_verified"
    || (application.status === "submitted" && (!application.college_id || application.college_active === false)),
  );
  const awaitingCollege = applications.filter((application) =>
    application.status === "submitted" && application.college_id && application.college_active !== false,
  );
  const approved = applications.filter((application) => application.status === "approved");
  const rejected = applications.filter((application) => application.status === "rejected");
  const correctionRequested = applications.filter((application) => application.status === "correction_required");
  const filterApplications = {
    pending,
    college: awaitingCollege,
    approved,
    rejected,
    changes: correctionRequested,
    all: applications,
  };
  const filteredApplications = filterApplications[filter] || applications;
  const filters = [
    ["pending", "Pending", pending.length],
    ["college", "Waiting for college", awaitingCollege.length],
    ["approved", "Approved", approved.length],
    ["rejected", "Rejected", rejected.length],
    ["changes", "Changes requested", correctionRequested.length],
    ["all", "All applications", applications.length],
  ];
  return <section className="application-review-list">
    <div className="admin-application-status-summary">
      <span>{t("Pending")} <strong>{pending.length}</strong></span>
      <span>{t("Approved")} <strong>{approved.length}</strong></span>
      <span>{t("Rejected")} <strong>{rejected.length}</strong></span>
    </div>
    <div className="application-review-filters" role="tablist" aria-label={t("Filter applications")}>
      {filters.map(([value, label, count]) => <button key={value} type="button" className={filter === value ? "application-review-filter-active" : ""} aria-pressed={filter === value} onClick={() => setFilter(value)}>{t(label)} <strong>{count}</strong></button>)}
    </div>
    {filteredApplications.length ? filteredApplications.map((application) => {
      const isOpen = openApplicationId === application.id;
      const studentName = application.student?.full_name || application.application_form?.full_name || t("Student");
      const canReview = application.status === "college_verified" || (application.status === "submitted" && (!application.college_id || application.college_active === false));
      return <article className="panel application-review-card" key={application.id}>
        <header><div><div className="eyebrow">{application.id.slice(0, 8)} · {dateLabel(application.application_date)}</div><h2>{application.scholarship_title}</h2><p>{studentName} · {application.student?.email || ""}</p></div><span className={`admin-chip ${application.status === "approved" || application.status === "paid" ? "chip-active" : "chip-inactive"}`}>{t(STATUS_LABELS[application.status] || application.status)}</span></header>
        <div className="application-card-summary"><span>{t("Student ID")} <strong>{application.student?.user_id || application.user_id}</strong></span><span>{t("College")} <strong>{application.college_name || application.application_form?.college || "—"}</strong></span></div>
        <button className="button button-outline button-small application-open-button" type="button" aria-expanded={isOpen} onClick={() => setOpenApplicationId(isOpen ? "" : application.id)}>{isOpen ? t("Close details") : t("Open details")} <ArrowRight size={14} /></button>
        {isOpen && <>
          <div className="application-review-details">{Object.entries(application.application_form || {}).filter(([, value]) => value).map(([field, value]) => <div key={field}><span>{t(field.replaceAll("_", " "))}</span><strong>{value}</strong></div>)}</div>
          <div className="application-review-documents"><strong>{t("Submitted documents")}</strong>{application.documents?.length ? application.documents.map((document) => <div key={document.id}><span><FileText size={15} />{t(document.name)}{document.required && <em>{t("Required")}</em>}</span><button className="button button-outline button-small" onClick={() => onViewDocument(application, document)}>{t("View document")}</button></div>) : <p>{t("No documents were attached.")}</p>}</div>
          {application.college_note && <div className="application-admin-note"><strong>{t("College verifier note")}</strong><p>{application.college_note}</p></div>}
          {application.rejection_reason && <div className="application-admin-note"><strong>{t("Rejection reason")}</strong><p>{application.rejection_reason}</p></div>}
          {application.admin_note && <div className="application-admin-note"><strong>{t("Administrator note")}</strong><p>{application.admin_note}</p></div>}
          <footer>
            {canReview && <><button className="button button-primary button-small" onClick={() => onReview(application, "approved")}><CheckCircle2 size={15} />{t("Approve application")}</button><button className="button button-outline button-small" onClick={() => onReview(application, "correction_required")}>{t("Request changes")}</button><button className="button button-outline button-small review-reject" onClick={() => onReview(application, "rejected")}>{t("Reject application")}</button></>}
            {application.status === "submitted" && application.college_id && application.college_active !== false && <span>{t("Waiting for college verification.")}</span>}
            {application.status === "submitted" && application.college_id && application.college_active === false && <span>{t("College is inactive. Admin review is available.")}</span>}
            {application.status === "correction_required" && <span>{t("Waiting for student corrections.")}</span>}
            {application.status === "approved" && <span>{t("Approval recorded. Awaiting separate finance simulation.")}</span>}
          </footer>
        </>}
      </article>;
    }) : <div className="admin-no-data">{t("No applications in this section.")}</div>}
  </section>;
}

function CollegeManagement({ colleges, form, setForm, onSubmit, onDelete, saving }) {
  const update = (event) => setForm((current) => ({ ...current, [event.target.name]: event.target.value }));
  const activeColleges = colleges.filter((college) => college.active);
  const inactiveColleges = colleges.length - activeColleges.length;
  return <div className="college-management">
    <section className="panel college-create-panel">
      <div className="section-heading"><div><div className="eyebrow">{t("COLLEGE ACCESS")}</div><h2>{t("Register a verified college")}</h2></div><ShieldCheck size={19} className="heading-icon" /></div>
      <p className="college-admin-intro">{t("Only an administrator can register a college and issue its verifier login. The verifier can access applications assigned to this college only.")}</p>
      <form className="college-create-form" onSubmit={onSubmit}>
        <label>{t("College name")}<input name="name" value={form.name} onChange={update} maxLength="160" required /></label>
        <label>{t("College code")}<input name="code" value={form.code} onChange={update} maxLength="24" pattern="[A-Za-z0-9][A-Za-z0-9-]{2,23}" placeholder={t("e.g. PUNE-COL-01")} required /></label>
        <label>{t("Verifier full name")}<input name="verifier_name" value={form.verifier_name} onChange={update} maxLength="120" required /></label>
        <label>{t("Verifier email")}<input type="email" name="verifier_email" value={form.verifier_email} onChange={update} required /></label>
        <label>{t("Temporary login password")}<input type="password" name="verifier_password" value={form.verifier_password} onChange={update} minLength="10" maxLength="128" autoComplete="new-password" required /><small>{t("Use a unique password and share it with the demo verifier securely.")}</small></label>
        <button className="button button-primary" type="submit" disabled={saving}>{saving ? <LoaderCircle size={16} className="spin" /> : <Plus size={16} />}{t("Create college and verifier account")}</button>
      </form>
      <div className="college-demo-notice"><CircleHelp size={17} /><span>{t("This registers a college for the project prototype; it does not verify the institution with MahaDBT or a government authority.")}</span></div>
    </section>
    <section className="panel admin-table-panel">
      <div className="section-heading"><div><div className="eyebrow">{t("REGISTERED INSTITUTIONS")}</div><h2>{t("Colleges and verifier accounts")}</h2></div><span className="admin-count">{activeColleges.length} {t("active")}</span></div>
      {activeColleges.length ? <div className="admin-table-scroll"><table className="admin-table"><thead><tr><th>{t("College")}</th><th>{t("College ID")}</th><th>{t("Verifier account")}</th><th>{t("Status")}</th><th>{t("Actions")}</th></tr></thead><tbody>{activeColleges.map((college) => <tr key={college.id}><td><strong>{college.name}</strong></td><td>{college.code}</td><td>{college.verifier ? <><strong>{college.verifier.full_name}</strong><span>{college.verifier.email}</span><span>{t("Login ID:")} {college.verifier.user_id}</span></> : t("No verifier account")}</td><td><span className="admin-chip chip-active">{t("Verified for this prototype")}</span></td><td><button className="button button-outline button-small review-reject" type="button" onClick={() => onDelete(college)}><Trash2 size={14} />{t("Delete")}</button></td></tr>)}</tbody></table></div> : <div className="admin-no-data">{t("No colleges registered yet.")}</div>}
      {inactiveColleges > 0 && <p className="college-admin-intro">{t("Inactive colleges are hidden from this list. Their application history is retained for admin review.")} ({inactiveColleges})</p>}
    </section>
  </div>;
}

function SupportManagement({ tickets, grievances, onUpdate }) {
  return <div className="admin-support-tables"><SupportTable title="Help tickets" records={tickets} kind="ticket" onUpdate={onUpdate} options={["open", "in_progress", "resolved", "closed"]} /><SupportTable title="Grievances" records={grievances} kind="grievance" onUpdate={onUpdate} options={["received", "under_review", "resolved", "closed"]} /></div>;
}

function SupportTable({ title, records, kind, options, onUpdate }) {
  return <section className="panel admin-table-panel"><div className="section-heading"><div><div className="eyebrow">STUDENT SUPPORT</div><h2>{t(title)}</h2></div><span className="admin-count">{records.length} {t("total")}</span></div>{records.length ? <div className="admin-table-scroll"><table className="admin-table"><thead><tr><th>Request</th><th>Student ID</th><th>Submitted</th><th>Status</th></tr></thead><tbody>{records.map((record) => <tr key={record.id}><td><strong>{record.subject}</strong><span>{kind === "ticket" ? record.message : record.description}</span></td><td>{record.user_id}</td><td>{dateLabel(record.created_at)}</td><td><select className="admin-status-select" value={record.status} onChange={(event) => onUpdate(kind, record, event.target.value)}>{options.map((status) => <option value={status} key={status}>{t(status.replaceAll("_", " "))}</option>)}</select></td></tr>)}</tbody></table></div> : <div className="admin-no-data">{t("No")} {t(title.toLowerCase())} {t("to review right now.")}</div>}</section>;
}

function FeedbackManagement({ feedback, scholarships, onModerate }) {
  const titles = useMemo(() => Object.fromEntries(scholarships.map((scheme) => [scheme.id, scheme.title])), [scholarships]);
  return <section className="panel admin-table-panel"><div className="section-heading"><div><div className="eyebrow">STUDENT VOICE</div><h2>Scholarship feedback</h2></div><span className="admin-count">{feedback.length} {t("ratings")}</span></div>{feedback.length ? <div className="feedback-list">{feedback.map((item) => <article className="feedback-row" key={item.id}><div className="feedback-rating"><Star size={15} fill="currentColor" /> {item.rating}/5</div><div className="feedback-copy"><strong>{titles[item.scholarship_id] || t("Archived scholarship")}</strong><p>{item.comment || t("No written comment.")}</p><span>{t("Student")} {item.user_id} · {dateLabel(item.created_at)}</span></div><div className="admin-row-actions"><span className={`admin-chip ${item.moderation_status === "approved" ? "chip-active" : "chip-inactive"}`}>{t(item.moderation_status || "approved")}</span>{item.moderation_status !== "approved" && <button className="button button-outline button-small" onClick={() => onModerate(item, "approved")}>{t("Approve")}</button>}{item.moderation_status !== "rejected" && <button className="button button-outline button-small" onClick={() => onModerate(item, "rejected")}>{t("Reject")}</button>}</div></article>)}</div> : <div className="admin-no-data">No feedback has been submitted yet.</div>}</section>;
}

function ContentManagement({ tutorials, tutorialForm, setTutorialForm, editingTutorial, onEditTutorial, onCancelTutorialEdit, onToggleTutorial, onSaveTutorial, surveyForm, setSurveyForm, onSaveSurvey, saving }) {
  const [mode, setMode] = useState("tutorial");
  return <div className="admin-content-grid"><section className="panel admin-form-panel"><div className="section-heading"><div><div className="eyebrow">PUBLISH CONTENT</div><h2>{mode === "tutorial" ? editingTutorial ? "Edit video tutorial" : "Video tutorials" : "Survey results"}</h2></div><div className="admin-segment"><button className={mode === "tutorial" ? "segment-active" : ""} onClick={() => setMode("tutorial")}>Tutorial</button><button className={mode === "survey" ? "segment-active" : ""} onClick={() => setMode("survey")}>Survey</button></div></div>{mode === "tutorial" ? <form className="admin-form-grid" onSubmit={onSaveTutorial}><label>Title<input required maxLength="160" value={tutorialForm.title} onChange={(event) => setTutorialForm({ ...tutorialForm, title: event.target.value })} /></label><label>Language<select value={tutorialForm.language} onChange={(event) => setTutorialForm({ ...tutorialForm, language: event.target.value })}>{LANGUAGES.map((language) => <option key={language} value={language}>{language.toUpperCase()}</option>)}</select></label><label className="admin-form-span">Description<input required value={tutorialForm.description} onChange={(event) => setTutorialForm({ ...tutorialForm, description: event.target.value })} /></label><label className="admin-form-span">Video URL<input type="url" required placeholder="https://…" value={tutorialForm.video_url} onChange={(event) => setTutorialForm({ ...tutorialForm, video_url: event.target.value })} /></label><label>Sort order<input type="number" min="0" max="10000" value={tutorialForm.order} onChange={(event) => setTutorialForm({ ...tutorialForm, order: event.target.value })} /></label><label>Status<select value={tutorialForm.status} onChange={(event) => setTutorialForm({ ...tutorialForm, status: event.target.value })}><option value="published">Published</option><option value="draft">Draft</option></select></label><div className="admin-form-span"><button className="button button-primary button-small" disabled={saving}>{saving ? <LoaderCircle size={15} className="spin" /> : editingTutorial ? <Save size={15} /> : <Plus size={15} />}{editingTutorial ? "Save tutorial" : "Publish tutorial"}</button>{editingTutorial && <button type="button" className="button button-outline button-small" onClick={onCancelTutorialEdit}>Cancel edit</button>}</div></form> : <form className="admin-form-grid" onSubmit={onSaveSurvey}><label>Survey title<input required maxLength="160" value={surveyForm.title} onChange={(event) => setSurveyForm({ ...surveyForm, title: event.target.value })} /></label><label>Language<select value={surveyForm.language} onChange={(event) => setSurveyForm({ ...surveyForm, language: event.target.value })}>{LANGUAGES.map((language) => <option key={language} value={language}>{language.toUpperCase()}</option>)}</select></label><label className="admin-form-span">Research question<input required maxLength="500" value={surveyForm.question} onChange={(event) => setSurveyForm({ ...surveyForm, question: event.target.value })} /></label><label>Respondents<input type="number" min="1" required value={surveyForm.respondents} onChange={(event) => setSurveyForm({ ...surveyForm, respondents: event.target.value })} /></label><label>Survey date<input type="date" required value={surveyForm.survey_date} onChange={(event) => setSurveyForm({ ...surveyForm, survey_date: event.target.value })} /></label><label className="admin-form-span">Source URL<input type="url" required placeholder="https://research-source…" value={surveyForm.source_url} onChange={(event) => setSurveyForm({ ...surveyForm, source_url: event.target.value })} /></label><label className="admin-form-span">Results (one per line: label | count)<textarea rows="4" required value={surveyForm.options} onChange={(event) => setSurveyForm({ ...surveyForm, options: event.target.value })} /></label><label>Status<select value={surveyForm.status} onChange={(event) => setSurveyForm({ ...surveyForm, status: event.target.value })}><option value="published">Published</option><option value="draft">Draft</option></select></label><div className="admin-form-span"><button className="button button-primary button-small" disabled={saving}>{saving ? <LoaderCircle size={15} className="spin" /> : <Save size={15} />} Save survey</button></div></form>}</section><aside className="panel admin-content-list"><div className="section-heading"><div><div className="eyebrow">CURRENTLY PUBLISHED</div><h2>{tutorials.length} tutorials</h2></div></div>{tutorials.length ? tutorials.slice(0, 8).map((tutorial) => <div className="published-item" key={tutorial.id}><div><strong>{tutorial.title}</strong><span>{tutorial.language.toUpperCase()} · {tutorial.status}</span></div><div className="admin-row-actions"><a href={tutorial.video_url} target="_blank" rel="noreferrer" aria-label={`Open ${tutorial.title}`}><ArrowRight size={15} /></a><button type="button" className="icon-button" aria-label={`Edit ${tutorial.title}`} onClick={() => { onEditTutorial(tutorial); setMode("tutorial"); }}><Pencil size={15} /></button><button type="button" className="button button-outline button-small" onClick={() => onToggleTutorial(tutorial)}>{t(tutorial.status === "published" ? "Unpublish" : "Publish")}</button></div></div>) : <div className="admin-no-data">No tutorials published.</div>}<div className="admin-hint"><ShieldCheck size={15} /> Survey results require a public source URL and real response counts.</div></aside></div>;
}

function NotificationManagement({ notifications, dispatching, onDispatch }) {
  const sent = notifications.filter((item) => item.status === "sent").length;
  const failed = notifications.filter((item) => item.status === "failed").length;
  const pending = notifications.filter((item) => item.status === "pending").length;
  return <><div className="notification-summary"><div><span>Pending</span><strong>{pending}</strong></div><div><span>Sent</span><strong>{sent}</strong></div><div><span>Failed / retryable</span><strong>{failed}</strong></div><button className="button button-primary" onClick={onDispatch} disabled={dispatching}>{dispatching ? <LoaderCircle size={16} className="spin" /> : <Send size={16} />}{dispatching ? "Sending email…" : "Dispatch email queue"}</button></div><div className="admin-email-note"><ShieldCheck size={17} /> Dispatch sends queued email notifications and due reminders through configured SMTP. It does not use SMS or WhatsApp.</div><section className="panel admin-table-panel"><div className="section-heading"><div><div className="eyebrow">SMTP DELIVERY</div><h2>Recent notification queue</h2></div><span className="admin-count">{notifications.length} records</span></div>{notifications.length ? <div className="admin-table-scroll"><table className="admin-table"><thead><tr><th>Notification</th><th>Channel</th><th>Status</th><th>Attempts</th><th>Last error</th></tr></thead><tbody>{notifications.map((item) => <tr key={item.id}><td><strong>{item.subject || item.id}</strong></td><td>{item.channel}</td><td><span className={`admin-chip ${item.status === "sent" ? "chip-active" : item.status === "failed" ? "chip-inactive" : ""}`}>{item.status}</span></td><td>{item.attempts || 0}</td><td>{item.last_error || "—"}</td></tr>)}</tbody></table></div> : <div className="admin-no-data">The notification queue is empty.</div>}</section></>;
}

function ScholarshipEditor({ form, setForm, editing, saving, onClose, onSubmit }) {
  const field = (name, value) => setForm((current) => ({ ...current, [name]: value }));
  const legacyDistricts = form.districts.filter(
    (name) => !MAHARASHTRA_DISTRICTS.some((district) => district.name.toLowerCase() === name.toLowerCase()),
  );
  return (
    <div className="admin-modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section className="admin-editor-modal" role="dialog" aria-modal="true" aria-labelledby="scheme-editor-title">
        <div className="admin-editor-header">
          <div><div className="eyebrow">DIRECTORY CONTENT</div><h2 id="scheme-editor-title">{editing ? "Edit scholarship" : "Add scholarship"}</h2><p>Enter details from the official scheme guidelines. Save changes to the admin-managed directory.</p></div>
          <button className="icon-button" onClick={onClose} aria-label="Close scholarship form"><X size={20} /></button>
        </div>
        <form className="admin-editor-form" onSubmit={onSubmit}>
          <div className="admin-form-grid">
            <label>Scholarship title<input required maxLength="160" value={form.title} onChange={(event) => field("title", event.target.value)} /></label>
            <label>Provider<input required maxLength="160" value={form.provider} onChange={(event) => field("provider", event.target.value)} /></label>
            <label>Education level<select value={form.education_level} onChange={(event) => field("education_level", event.target.value)}><option value="school">School</option><option value="undergraduate">Undergraduate</option><option value="postgraduate">Postgraduate</option><option value="doctoral">Doctoral</option><option value="other">Other</option></select></label>
            <label>{t("Categories (directory tags)")}
              <select className="district-multi-select" multiple size="5" required value={form.categories} onChange={(event) => field("categories", Array.from(event.target.selectedOptions, (option) => option.value))}>
                {SCHOLARSHIP_CATEGORIES.map((category) => <option value={category} key={category}>{category.toUpperCase()}</option>)}
              </select>
              <span className="admin-field-hint">{t("Select one or more tags for finding this scheme in the directory. Use Ctrl (Windows/Linux) or Command (Mac) for multiple choices.")}</span>
            </label>
            <label className="admin-form-span">{t("Eligibility summary")}
              <textarea required rows="2" maxLength="2000" value={form.eligibility_summary} onChange={(event) => field("eligibility_summary", event.target.value)} placeholder={t("e.g. Maharashtra students enrolled in an undergraduate course with family income below ₹2.5 lakh.")} />
              <span className="admin-field-hint">{t("A short, student-friendly summary of the main eligibility rules. It appears on scholarship cards and in assistant answers; keep it accurate to the official scheme criteria.")}</span>
            </label>
            <label className="admin-form-span">Description<textarea required rows="4" maxLength="10000" value={form.description} onChange={(event) => field("description", event.target.value)} /></label>
            <label>Eligible categories
              <select className="district-multi-select" multiple size="5" value={form.eligibility_categories} onChange={(event) => field("eligibility_categories", Array.from(event.target.selectedOptions, (option) => option.value))}>
                {SCHOLARSHIP_CATEGORIES.map((category) => <option value={category} key={category}>{category.toUpperCase()}</option>)}
              </select>
              <span className="admin-field-hint">{t("Leave all unselected if there is no category restriction.")}</span>
            </label>
            <label>Maximum family income (₹)<input type="number" min="0" value={form.income_max} onChange={(event) => field("income_max", event.target.value)} /></label>
            <label>Minimum percentage<input type="number" min="0" max="100" step="0.01" value={form.minimum_percentage} onChange={(event) => field("minimum_percentage", event.target.value)} /></label>
            <label>Study years<input placeholder="1, 2, 3" value={form.study_years} onChange={(event) => field("study_years", event.target.value)} /></label>
            <label className="admin-form-span">Eligible courses
              <select className="district-multi-select" multiple size="7" value={form.courses} onChange={(event) => field("courses", Array.from(event.target.selectedOptions, (option) => option.value))}>
                {form.courses.filter((course) => !COURSE_OPTIONS.includes(course)).map((course) => <option value={course} key={course}>{course}</option>)}
                {SORTED_COURSE_OPTIONS.map((course) => <option value={course} key={course}>{course}</option>)}
              </select>
              <span className="admin-field-hint">{t("Select every course allowed by the scheme. Leave unselected if all courses are eligible. Use Ctrl (Windows/Linux) or Command (Mac) to select multiple options.")}</span>
            </label>
            <label className="admin-form-span">{t("Eligible districts (optional; select all that apply)")}
              <select className="district-multi-select" multiple value={form.districts} onChange={(event) => field("districts", Array.from(event.target.selectedOptions, (option) => option.value))}>
                {legacyDistricts.map((name) => <option value={name} key={name}>{name}</option>)}
                {MAHARASHTRA_DISTRICTS.map((district) => <option value={district.name} key={district.name}>{districtLabel(district.name, getLocale())}</option>)}
              </select>
            </label>
            <label>Award amount<input maxLength="120" placeholder="e.g. Up to ₹25,000" value={form.award_amount} onChange={(event) => field("award_amount", event.target.value)} /></label>
            <label>{t("Fixed demo payout amount (₹)")}<input type="number" min="0.01" max="999999999999.99" step="0.01" placeholder="e.g. 25000.00" value={form.payout_amount} onChange={(event) => field("payout_amount", event.target.value)} /><span className="admin-field-hint">{t("Exact amount loaded in the simulated finance flow. Not a real transfer.")}</span></label>
            <label>Deadline<input type="date" value={form.deadline || ""} onChange={(event) => field("deadline", event.target.value)} /></label>
            <label>Maharashtra domicile<select value={form.maharashtra_domicile} onChange={(event) => field("maharashtra_domicile", event.target.value)}><option value="">Not specified</option><option value="true">Required</option><option value="false">Not required</option></select></label>
            <label>Minority criterion<select value={form.minority} onChange={(event) => field("minority", event.target.value)}><option value="">Not specified</option><option value="true">Required</option><option value="false">Not required</option></select></label>
            <label>Divyang criterion<select value={form.divyang} onChange={(event) => field("divyang", event.target.value)}><option value="">Not specified</option><option value="true">Required</option><option value="false">Not required</option></select></label>
            <label className="admin-form-span">Required documents from official guidelines (comma-separated)<input placeholder="Only required items, e.g. income certificate" value={form.documents} onChange={(event) => field("documents", event.target.value)} /></label>
            <label className="admin-form-span">FAQs (one per line: question | answer)<textarea rows="3" placeholder={"Who can apply? | Students who meet the listed criteria."} value={form.faqs} onChange={(event) => field("faqs", event.target.value)} /></label>
            <label className="admin-form-span">Translations JSON (en / hi / mr)<textarea rows="5" spellCheck="false" value={form.translations} onChange={(event) => field("translations", event.target.value)} /><span className="admin-field-hint">Example: {"{\"hi\":{\"title\":\"...\",\"description\":\"...\",\"eligibility_summary\":\"...\"}}"}</span></label>
          </div>
          <div className="admin-field-hint source-free-note">{t("Official source and application links are not collected here. New schemes remain unreviewed and are excluded from assistant answers. Review scheme facts against official guidelines in the directory after saving.")}</div>
          <div className="admin-editor-footer">
            <span><ShieldCheck size={15} /> {t(editing?.verified_at ? "Saving edits clears administrator review." : "New schemes must be checked against official guidelines after saving.")}</span>
            <div><button type="button" className="button button-outline" onClick={onClose}>Cancel</button><button className="button button-primary" disabled={saving}>{saving ? <LoaderCircle size={16} className="spin" /> : editing ? <Save size={16} /> : <Plus size={16} />}{editing ? "Save changes" : "Create scholarship"}</button></div>
          </div>
        </form>
      </section>
    </div>
  );
}

export default AdminPanel;
