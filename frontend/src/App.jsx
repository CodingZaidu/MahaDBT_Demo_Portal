import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from "react";
import {
  Accessibility,
  ArrowDownToLine,
  ArrowDownUp,
  ArrowRight,
  ArrowUpRight,
  Bell,
  Banknote,
  BookOpen,
  CalendarDays,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleHelp,
  Clock3,
  FileCheck2,
  FileText,
  Filter,
  GraduationCap,
  HeartHandshake,
  History,
  LayoutDashboard,
  ListChecks,
  LoaderCircle,
  LogOut,
  Menu,
  MessageCircle,
  Moon,
  Plus,
  Search,
  Send,
  ShieldCheck,
  Sparkles,
  Star,
  Sun,
  TrendingUp,
  Upload,
  UserRound,
  X,
  Eye,
  EyeOff,
} from "lucide-react";
import { getLocale, setLocale, t } from "./i18n.js";
import { districtLabel, MAHARASHTRA_DISTRICTS } from "./districts.js";

const AdminPanel = lazy(() => import("./AdminPanel.jsx"));
const FinancePanel = lazy(() => import("./FinancePanel.jsx"));
const CollegeVerifierPanel = lazy(() => import("./CollegeVerifierPanel.jsx"));
const AuthScene = lazy(() => import("./AuthScene.jsx"));
const DashboardScene = lazy(() => import("./AuthScene.jsx").then((module) => ({ default: module.DashboardScene })));
const INITIAL_LOCALE = (() => {
  const savedLocale = typeof window === "undefined"
    ? "en"
    : window.localStorage.getItem("scholarship-support-language") || "en";
  return ["en", "hi", "mr"].includes(savedLocale) ? savedLocale : "en";
})();
setLocale(INITIAL_LOCALE);
const TOKEN_KEY = "scholarship-support-token";
const USER_KEY = "scholarship-support-user";
const STATUSES = ["draft", "submitted", "college_verified", "correction_required", "approved", "rejected", "paid"];
const PROFILE_FIELDS = [
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
];
const EMPTY_PROFILE = {
  category: "",
  minority: "",
  divyang: "",
  maharashtra_domicile: "",
  family_income_range: "",
  district: "",
  preferred_language: "en",
  course: "",
  education_level: "",
  year_of_study: "",
  college: "",
  university: "",
  previous_percentage: "",
};
const STATUS_LABELS = {
  draft: "Draft",
  submitted: "Submitted",
  college_verified: "College verified",
  correction_required: "Correction required",
  approved: "Approved",
  rejected: "Rejected",
  paid: "Paid",
};
const LANGUAGES = [
  { value: "en", label: "English" },
  { value: "hi", label: "हिन्दी" },
  { value: "mr", label: "मराठी" },
];

async function api(path, options = {}, token = "") {
  const headers = new Headers(options.headers || {});
  if (options.body && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(path, { ...options, headers });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.error || "Something went wrong. Please try again.");
    error.status = response.status;
    throw error;
  }
  return data;
}

function localDateISO() {
  const date = new Date();
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function initials(name = "") {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0].toUpperCase())
    .join("") || "SS";
}

function formatDate(value) {
  if (!value) return "Not set";
  const date = new Date(`${value}T00:00:00`);
  return Number.isNaN(date.getTime())
    ? value
    : new Intl.DateTimeFormat(`${getLocale()}-IN`, { day: "numeric", month: "short", year: "numeric" }).format(date);
}

function App() {
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY) || "");
  const [user, setUser] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem(USER_KEY) || "null");
    } catch {
      return null;
    }
  });
  const [view, setView] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem(USER_KEY) || "null")?.role === "college_verifier"
        ? "college"
        : "dashboard";
    } catch {
      return "dashboard";
    }
  });
  const [applicationToEdit, setApplicationToEdit] = useState("");
  const [language, setLanguage] = useState(INITIAL_LOCALE);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [toast, setToast] = useState("");
  const [adminAccess, setAdminAccess] = useState(false);
  const [financeAccess, setFinanceAccess] = useState(false);
  const [largeText, setLargeText] = useState(() => localStorage.getItem("scholarship-support-large-text") === "true");
  const [theme, setTheme] = useState(() => localStorage.getItem("scholarship-support-theme") === "dark" ? "dark" : "light");

  const notify = useCallback((message) => {
    setToast(t(message));
    window.clearTimeout(notify.timeout);
    notify.timeout = window.setTimeout(() => setToast(""), 3800);
  }, []);

  const onAuthenticated = useCallback((newToken, newUser) => {
    localStorage.setItem(TOKEN_KEY, newToken);
    localStorage.setItem(USER_KEY, JSON.stringify(newUser));
    setToken(newToken);
    setUser(newUser);
    setView(newUser.role === "college_verifier" ? "college" : "dashboard");
  }, []);

  const signOut = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    setToken("");
    setUser(null);
    setAdminAccess(false);
    setFinanceAccess(false);
    setView("dashboard");
  }, []);

  useEffect(() => {
    setAdminAccess(false);
    setFinanceAccess(false);
    if (!token) return;
    api("/api/auth/me", {}, token)
      .then(({ user: currentUser, permissions = {} }) => {
        setUser(currentUser);
        localStorage.setItem(USER_KEY, JSON.stringify(currentUser));
        setAdminAccess(Boolean(permissions.admin));
        setFinanceAccess(Boolean(permissions.finance));
      })
      .catch((error) => {
        if (error.status === 401) signOut();
        else notify(error.message);
      });
  }, [token, signOut, notify]);

  useEffect(() => {
    setLocale(language);
    localStorage.setItem("scholarship-support-language", language);
  }, [language]);

  useEffect(() => {
    document.documentElement.style.zoom = largeText ? "1.1" : "1";
    localStorage.setItem("scholarship-support-large-text", String(largeText));
  }, [largeText]);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("scholarship-support-theme", theme);
  }, [theme]);

  if (!token || !user) {
    return <AuthScreen onAuthenticated={onAuthenticated} notify={notify} toast={toast} theme={theme} onToggleTheme={() => setTheme((current) => current === "dark" ? "light" : "dark")} />;
  }

  const navigate = (nextView, applicationId = "") => {
    setView(nextView);
    if (nextView === "applications") setApplicationToEdit(applicationId);
    setMobileNavOpen(false);
  };

  return (
    <div className="app-shell">
      <aside className={`sidebar ${mobileNavOpen ? "sidebar-open" : ""}`}>
        <div className="brand">
          <div className="brand-mark"><GraduationCap size={22} strokeWidth={2.2} /></div>
          <div className="brand-copy"><strong>Scholarship</strong><span>SUPPORT</span></div>
          <button className="icon-button mobile-close" onClick={() => setMobileNavOpen(false)} aria-label="Close menu"><X size={20} /></button>
        </div>
        <div className="sidebar-label">Workspace</div>
        {user.role === "college_verifier" ? <nav className="nav-list" aria-label="College navigation">
          <NavItem icon={GraduationCap} label="College verification" active={view === "college"} onClick={() => navigate("college")} />
        </nav> : <nav className="nav-list" aria-label="Main navigation">
          <NavItem icon={LayoutDashboard} label="Overview" active={view === "dashboard"} onClick={() => navigate("dashboard")} />
          <NavItem icon={Search} label="Find scholarships" active={view === "scholarships"} onClick={() => navigate("scholarships")} />
          <NavItem icon={ListChecks} label="My applications" active={view === "applications"} onClick={() => navigate("applications")} />
          <NavItem icon={UserRound} label="My profile" active={view === "profile"} onClick={() => navigate("profile")} />
        </nav>}
        {user.role !== "college_verifier" && <><div className="sidebar-label sidebar-label-spaced">Explore</div>
        <nav className="nav-list" aria-label="Support navigation">
          <NavItem icon={MessageCircle} label="Scholarship assistant" active={view === "assistant"} onClick={() => navigate("assistant")} badge="AI" />
          <NavItem icon={HeartHandshake} label="Help & support" active={view === "help"} onClick={() => navigate("help")} />
          <NavItem icon={TrendingUp} label="Survey insights" active={view === "insights"} onClick={() => navigate("insights")} />
          {adminAccess && <NavItem icon={ShieldCheck} label="Admin dashboard" active={view === "admin"} onClick={() => navigate("admin")} />}
          {financeAccess && <NavItem icon={Banknote} label="Finance simulation" active={view === "finance"} onClick={() => navigate("finance")} />}
        </nav></>}
        <div className="sidebar-bottom">
          <div className="sidebar-help">
            <div className="sidebar-help-icon"><ShieldCheck size={18} /></div>
            <strong>Your data, protected</strong>
            <p>{t("Bank details are requested only for a scholarship application, with consent and encryption; never share them in support requests.")}</p>
            <button onClick={() => navigate("help")}>Privacy & safety <ArrowRight size={14} /></button>
          </div>
          <div className="profile-mini">
            <div className="avatar">{initials(user.full_name)}</div>
            <div className="profile-mini-copy"><strong>{user.full_name}</strong><span>{user.user_id}</span></div>
            <button className="icon-button logout-button" onClick={signOut} aria-label="Sign out" title="Sign out"><LogOut size={17} /></button>
          </div>
        </div>
      </aside>
      {mobileNavOpen && <button className="nav-scrim" onClick={() => setMobileNavOpen(false)} aria-label="Close navigation" />}

      <a className="skip-link" href="#main-content">Skip to main content</a>
      <main className="main-area" id="main-content">
        <header className="topbar">
          <button className="icon-button mobile-menu" onClick={() => setMobileNavOpen(true)} aria-label="Open menu"><Menu size={21} /></button>
          <div className="breadcrumb"><span>Workspace</span><ChevronRight size={14} /><strong>{t(pageTitle(view))}</strong></div>
          <div className="topbar-actions">
            <label className="language-select" aria-label="Assistant language">
              <span className="language-dot" />
              <select value={language} onChange={(event) => { setLocale(event.target.value); setLanguage(event.target.value); }}>
                {LANGUAGES.map((item) => <option value={item.value} key={item.value}>{item.label}</option>)}
              </select>
              <ChevronDown size={14} />
            </label>
            <button className="icon-button theme-toggle" onClick={() => setTheme((current) => current === "dark" ? "light" : "dark")} aria-label={t(theme === "dark" ? "Switch to light mode" : "Switch to dark mode")} title={t(theme === "dark" ? "Switch to light mode" : "Switch to dark mode")}>{theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}</button>
            <button className={`icon-button accessibility-button ${largeText ? "accessibility-active" : ""}`} onClick={() => setLargeText((value) => !value)} aria-label={largeText ? "Return to normal text size" : "Increase text size"} title={largeText ? "Return to normal text size" : "Increase text size"}><Accessibility size={19} /></button>
            <button className="icon-button notification-button" aria-label="Notifications" onClick={() => notify("Email reminders will appear here when available.")}><Bell size={19} /><i /></button>
            <button className="top-avatar" onClick={() => navigate("profile")} aria-label="Open your profile">{initials(user.full_name)}</button>
          </div>
        </header>
        <div className="content-area">
          {view === "college" && user.role === "college_verifier" && <Suspense fallback={<Loading label="Loading college verification queue…" />}><CollegeVerifierPanel token={token} user={user} notify={notify} /></Suspense>}
          {view === "dashboard" && user.role !== "college_verifier" && <Dashboard user={user} token={token} navigate={navigate} notify={notify} />}
          {view === "scholarships" && <Scholarships token={token} user={user} notify={notify} navigate={navigate} />}
          {view === "applications" && <Applications token={token} notify={notify} initialEditId={applicationToEdit} onInitialEditHandled={() => setApplicationToEdit("")} />}
          {view === "profile" && <Profile token={token} user={user} onUserChange={setUser} notify={notify} language={language} />}
          {view === "assistant" && <Assistant language={language} />}
          {view === "help" && <HelpCenter token={token} notify={notify} language={language} />}
          {view === "insights" && <SurveyInsights />}
          {view === "admin" && adminAccess && <Suspense fallback={<Loading label="Loading admin dashboard…" />}><AdminPanel token={token} notify={notify} /></Suspense>}
          {view === "finance" && financeAccess && <Suspense fallback={<Loading label="Loading finance simulation…" />}><FinancePanel token={token} notify={notify} /></Suspense>}
        </div>
      </main>
      {toast && <div className="toast" role="status"><CheckCircle2 size={18} />{toast}</div>}
    </div>
  );
}

function pageTitle(view) {
  return {
    dashboard: "Overview",
    scholarships: "Find scholarships",
    applications: "My applications",
    profile: "My profile",
    assistant: "Scholarship assistant",
    help: "Help & support",
    insights: "Survey insights",
    admin: "Admin dashboard",
    finance: "Finance simulation",
    college: "College verification",
  }[view] || "Overview";
}

function NavItem({ icon: Icon, label, active, onClick, badge }) {
  return (
    <button className={`nav-item ${active ? "nav-item-active" : ""}`} onClick={onClick}>
      <Icon size={19} strokeWidth={active ? 2.25 : 1.8} /><span>{t(label)}</span>
      {badge && <small>{badge}</small>}
    </button>
  );
}

function PageHeading({ eyebrow, title, description, action }) {
  return (
    <div className="page-heading">
      <div><div className="eyebrow">{t(eyebrow)}</div><h1>{t(title)}</h1>{description && <p>{t(description)}</p>}</div>
      {action && <div className="heading-action">{action}</div>}
    </div>
  );
}

function Loading({ label = "Loading your information…" }) {
  return <div className="loading-state"><LoaderCircle className="spin" size={22} />{t(label)}</div>;
}

function ErrorMessage({ children, onRetry }) {
  return <div className="error-box"><CircleHelp size={18} /><span>{t(children)}</span>{onRetry && <button onClick={onRetry}>Try again</button>}</div>;
}

function EmptyState({ icon: Icon = FileText, title, children, action }) {
  return <div className="empty-state"><div className="empty-icon"><Icon size={24} /></div><h3>{t(title)}</h3><p>{t(children)}</p>{action}</div>;
}

function Dashboard({ user, token, navigate, notify }) {
  const [dashboard, setDashboard] = useState(null);
  const [scholarships, setScholarships] = useState([]);
  const [profile, setProfile] = useState({});
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [applicationsData, scholarshipData, profileData] = await Promise.all([
        api("/api/applications/dashboard", {}, token),
        loadOpenScholarships(),
        api("/api/profile", {}, token),
      ]);
      setDashboard(applicationsData);
      setScholarships(scholarshipData);
      setProfile(profileData.profile || {});
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => { load(); }, [load]);
  const apps = dashboard?.applications || [];
  const counts = dashboard?.totals || {};
  const profileProgress = useMemo(() => {
    const fields = ["category", "maharashtra_domicile", "family_income_range", "education_level", "course", "year_of_study", "district", "preferred_language"];
    return Math.round((fields.filter((field) => profile[field] !== undefined && profile[field] !== "").length / fields.length) * 100);
  }, [profile]);
  const nextDeadline = scholarships.find((item) => item.deadline && item.deadline >= localDateISO());

  return (
    <>
      <div className="welcome-strip">
        <div><div className="eyebrow">YOUR SCHOLARSHIP JOURNEY</div><h1>Good to see you, {user.full_name.split(" ")[0]} <span className="wave">✦</span></h1><p>Small steps today can open big doors tomorrow.</p></div>
        <div className="welcome-art" aria-hidden="true">
          <div className="art-sun" />
          <div className="art-book"><BookOpen size={42} /></div>
          <div className="art-star star-one">✦</div>
          <div className="art-star star-two">✧</div>
          <Suspense fallback={null}><DashboardScene /></Suspense>
          <div className="welcome-orbit-label"><Sparkles size={13} /> Future in motion</div>
        </div>
      </div>
      {error && <ErrorMessage onRetry={load}>{error}</ErrorMessage>}
      {loading ? <Loading /> : (
        <>
          <div className="stats-grid">
            <StatCard icon={FileCheck2} label="Active applications" value={apps.length} sub={`${counts.submitted || 0} ${t("submitted")}`} tone="blue" />
            <StatCard icon={Clock3} label="In progress" value={(counts.draft || 0) + (counts.submitted || 0) + (counts.college_verified || 0)} sub="Keep your tracker updated" tone="orange" />
            <StatCard icon={CheckCircle2} label="Scholarships paid" value={counts.paid || 0} sub="You made it happen" tone="green" />
            <button className="stat-card profile-stat" onClick={() => navigate("profile")}><div className="stat-top"><div className="stat-icon tone-purple"><UserRound size={18} /></div><span className="stat-trend">{t("Profile")}</span></div><div className="profile-progress-row"><strong>{profileProgress}%</strong><span>{t("profile complete")}</span></div><div className="progress-track"><span style={{ width: `${profileProgress}%` }} /></div><span className="stat-foot">{t("Improve your matches")} <ArrowRight size={14} /></span></button>
          </div>

          <div className="dashboard-grid">
            <section className="panel applications-panel">
              <div className="section-heading"><div><div className="eyebrow">STAY ON TRACK</div><h2>Recent applications</h2></div><button className="text-link" onClick={() => navigate("applications")}>View all <ArrowRight size={15} /></button></div>
              {apps.length ? <div className="application-list">{apps.slice(0, 4).map((application) => <ApplicationRow key={application.id} application={application} />)}</div> : <EmptyState icon={ListChecks} title="Your tracker is ready">Add a scholarship application to see every update in one place.<button className="button button-primary button-small" onClick={() => navigate("scholarships")}>Explore scholarships <ArrowRight size={15} /></button></EmptyState>}
            </section>
            <section className="panel deadline-panel">
              <div className="section-heading"><div><div className="eyebrow">DON'T MISS OUT</div><h2>Coming up</h2></div><CalendarDays size={18} className="heading-icon" /></div>
              {nextDeadline ? <div className="deadline-feature"><div className="deadline-date"><CalendarDays size={19} /><span>{formatDate(nextDeadline.deadline)}</span></div><h3>{nextDeadline.title}</h3><p>{nextDeadline.provider}</p><button className="button button-dark button-full" onClick={() => navigate("scholarships")}>View scholarship <ArrowRight size={16} /></button></div> : <div className="deadline-empty"><div className="deadline-calendar"><CalendarDays size={26} /></div><strong>No upcoming deadlines</strong><span>We'll surface new opportunities here.</span><button className="text-link" onClick={() => navigate("scholarships")}>Browse directory <ArrowRight size={14} /></button></div>}
              <div className="deadline-note"><ShieldCheck size={15} /> Always verify deadlines on the official scheme site.</div>
            </section>
          </div>

          <section className="panel recommended-panel">
            <div className="section-heading"><div><div className="eyebrow">{t("OPEN FOR APPLICATIONS")}</div><h2>{t("Scholarships you can apply for now")}</h2></div><button className="text-link" onClick={() => navigate("scholarships")}>{t("Browse directory")} <ArrowRight size={15} /></button></div>
            {scholarships.length ? <div className="scholarship-grid">{scholarships.map((scholarship, index) => <ScholarshipCard key={scholarship.id} scholarship={scholarship} index={index} token={token} notify={notify} onOpen={() => navigate("scholarships")} />)}</div> : <div className="small-empty">{t("No active scholarships with a deadline today or later are open right now.")}</div>}
          </section>
          <Recommendations token={token} profile={profile} navigate={navigate} />
        </>
      )}
    </>
  );
}

async function loadOpenScholarships() {
  const params = new URLSearchParams({
    per_page: "100",
    sort: "deadline",
    deadline_after: localDateISO(),
  });
  const firstPage = await api(`/api/scholarships?${params}`);
  const remainingPages = await Promise.all(
    Array.from({ length: Math.max(0, firstPage.pagination.pages - 1) }, (_, index) =>
      api(`/api/scholarships?${new URLSearchParams({ ...Object.fromEntries(params), page: String(index + 2) })}`),
    ),
  );
  return [...(firstPage.items || []), ...remainingPages.flatMap((page) => page.items || [])];
}

function StatCard({ icon: Icon, label, value, sub, tone }) {
  return <div className="stat-card"><div className="stat-top"><div className={`stat-icon tone-${tone}`}><Icon size={18} /></div><span className="stat-trend"><ArrowUpRight size={14} /></span></div><strong className="stat-value">{value}</strong><span className="stat-label">{t(label)}</span><span className="stat-foot">{t(sub)}</span></div>;
}

function ApplicationRow({ application, compact = false }) {
  const pending = application.status === "submitted" || application.status === "college_verified";
  return <div className={`application-row ${compact ? "application-row-compact" : ""}`}><div className="app-logo">{initials(application.scholarship_title)}</div><div className="application-row-main"><strong>{application.scholarship_title}</strong><span>{application.official_application_id || "Application ID not added"}{application.scheme_deadline ? ` · Deadline ${formatDate(application.scheme_deadline)}` : ""}</span>{pending && <span>{t(application.status === "submitted" ? "Pending college review" : "Pending administrator review")}</span>}</div><StatusBadge status={application.status} label={pending ? t("Pending") : undefined} /></div>;
}

function StatusBadge({ status, label }) {
  return <span className={`status-badge status-${status}`}>{label || t(STATUS_LABELS[status] || status)}</span>;
}

function Scholarships({ token, user, notify, navigate }) {
  const [items, setItems] = useState([]);
  const [query, setQuery] = useState("");
  const [level, setLevel] = useState("");
  const [category, setCategory] = useState("");
  const [sort, setSort] = useState("deadline");
  const [selected, setSelected] = useState([]);
  const [comparison, setComparison] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [creating, setCreating] = useState("");
  const [eligibility, setEligibility] = useState(null);
  const [ratingScholarship, setRatingScholarship] = useState(null);
  const [applyingScholarship, setApplyingScholarship] = useState(null);
  const [applyingApplication, setApplyingApplication] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    const params = new URLSearchParams({ per_page: "50", sort });
    if (query.trim()) params.set("q", query.trim());
    if (level) params.set("level", level);
    if (category) params.set("category", category);
    try {
      const data = await api(`/api/scholarships?${params}`);
      setItems(data.items || []);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }, [query, level, category, sort]);

  useEffect(() => {
    const timeout = window.setTimeout(load, 260);
    return () => window.clearTimeout(timeout);
  }, [load]);

  async function addTracker(id) {
    const scholarship = items.find((item) => item.id === id);
    if (!scholarship) return;
    setCreating(id);
    try {
      const { applications } = await api("/api/applications/dashboard", {}, token);
      const existing = (applications || []).find((application) => application.scholarship_id === id);
      if (existing && existing.status !== "draft" && existing.status !== "correction_required") {
        notify(t("You already have an application tracker for this scholarship. Open My applications to view it."));
        navigate("applications");
        return;
      }
      setApplyingApplication(existing || null);
      setApplyingScholarship(scholarship);
    } catch (requestError) {
      notify(requestError.message);
      setApplyingApplication(null);
      setApplyingScholarship(scholarship);
    } finally {
      setCreating("");
    }
  }

  async function compareSelected() {
    if (selected.length < 2) return;
    try {
      const params = new URLSearchParams();
      selected.forEach((id) => params.append("id", id));
      const data = await api(`/api/profile/compare?${params}`);
      setComparison(data.comparison || []);
    } catch (requestError) {
      notify(requestError.message);
    }
  }

  async function checkEligibility(scholarship) {
    try {
      const { profile } = await api("/api/profile", {}, token);
      const eligibilityProfile = Object.fromEntries(
        PROFILE_FIELDS.filter((field) => field in profile).map((field) => [field, profile[field]]),
      );
      const result = await api("/api/profile/eligibility", {
        method: "POST",
        body: JSON.stringify({ scholarship_id: scholarship.id, profile: eligibilityProfile }),
      });
      setEligibility({ scholarship, ...result });
    } catch (requestError) {
      notify(requestError.message);
    }
  }

  async function submitRating(rating, comment) {
    if (!ratingScholarship) return;
    try {
      await api("/api/feedback", {
        method: "POST",
        body: JSON.stringify({ scholarship_id: ratingScholarship.id, rating, comment }),
      }, token);
      notify("Feedback submitted for administrator review.");
      setRatingScholarship(null);
    } catch (requestError) {
      notify(requestError.message);
    }
  }

  function toggleCompare(id) {
    setSelected((current) => current.includes(id)
      ? current.filter((value) => value !== id)
      : current.length < 3 ? [...current, id] : current);
    if (!selected.includes(id) && selected.length >= 3) notify("Compare up to 3 scholarships at a time.");
  }

  return (
    <>
      <PageHeading eyebrow="DISCOVER YOUR OPTIONS" title="Find your scholarship" description="Explore opportunities and find the support that fits your next step." action={<div className="verified-note"><ShieldCheck size={17} /> Scheme details verified by admins</div>} />
      <div className="search-banner"><div className="search-banner-copy"><Sparkles size={18} /><span>Start with a course, category or scholarship name</span></div><div className="scholarship-search"><Search size={19} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Try “engineering” or “postgraduate”" aria-label="Search scholarships" />{query && <button className="icon-button" onClick={() => setQuery("")} aria-label="Clear search"><X size={17} /></button>}</div></div>
      <div className="filter-toolbar">
        <div className="filter-label"><Filter size={16} /> Filters</div>
        <select value={level} onChange={(event) => setLevel(event.target.value)} aria-label="Filter by education level"><option value="">All education levels</option><option value="school">School</option><option value="undergraduate">Undergraduate</option><option value="postgraduate">Postgraduate</option><option value="doctoral">Doctoral</option><option value="other">Other</option></select>
        <select value={category} onChange={(event) => setCategory(event.target.value)} aria-label="Filter by category"><option value="">All categories</option>{["open", "obc", "sc", "st", "vjnt", "sbc", "ews", "minority"].map((item) => <option value={item} key={item}>{item.toUpperCase()}</option>)}</select>
        <select value={sort} onChange={(event) => setSort(event.target.value)} aria-label="Sort scholarships"><option value="deadline">Closing soon</option><option value="updated">Recently updated</option></select>
        {(level || category || query) && <button className="clear-filters" onClick={() => { setLevel(""); setCategory(""); setQuery(""); }}>Clear all</button>}
        <span className="results-count">{items.length} {items.length === 1 ? "opportunity" : "opportunities"}</span>
      </div>
      {selected.length >= 2 && <div className="compare-bar"><span><ArrowDownUp size={17} /> {selected.length} scholarships selected to compare</span><button className="button button-dark button-small" onClick={compareSelected}>Compare side by side <ArrowRight size={15} /></button><button className="icon-button" onClick={() => setSelected([])} aria-label="Clear selection"><X size={17} /></button></div>}
      {error && <ErrorMessage onRetry={load}>{error}</ErrorMessage>}
      {loading ? <Loading label="Finding scholarships…" /> : items.length ? <div className="scholarship-grid">{items.map((scholarship, index) => <ScholarshipCard key={scholarship.id} scholarship={scholarship} index={index} token={token} notify={notify} onAdd={() => addTracker(scholarship.id)} onEligibility={() => checkEligibility(scholarship)} onRate={() => setRatingScholarship(scholarship)} creating={creating === scholarship.id} selected={selected.includes(scholarship.id)} onToggleCompare={() => toggleCompare(scholarship.id)} />)}</div> : <EmptyState icon={Search} title="No scholarships found">Try a different search or remove one of your filters.</EmptyState>}
      {comparison && <ComparisonModal comparison={comparison} onClose={() => setComparison(null)} />}
      {eligibility && <EligibilityModal result={eligibility} onClose={() => setEligibility(null)} />}
      {ratingScholarship && <RatingModal scholarship={ratingScholarship} onClose={() => setRatingScholarship(null)} onSubmit={submitRating} />}
      {applyingScholarship && <ApplicationFormModal scholarship={applyingScholarship} existingApplication={applyingApplication} token={token} user={user} onClose={() => { setApplyingScholarship(null); setApplyingApplication(null); }} onSubmitted={(application) => {
        setApplyingScholarship(null);
        setApplyingApplication(null);
        setSelected((current) => current.filter((value) => value !== application.scholarship_id));
        notify(t("Application submitted to the administrator for review."));
        navigate("applications");
      }} />}
    </>
  );
}

function ScholarshipCard({ scholarship, index = 0, onAdd, creating, selected, onToggleCompare, onOpen, onEligibility, onRate }) {
  const colors = ["scheme-blue", "scheme-violet", "scheme-orange", "scheme-teal"];
  const isExpired = scholarship.deadline && scholarship.deadline < new Date().toISOString().slice(0, 10);
  return (
    <article className="scholarship-card">
      <div className={`scheme-art ${colors[index % colors.length]}`}><span className="scheme-emblem"><GraduationCap size={22} /></span><span className="scheme-art-label">{scholarship.education_level || "Scholarship"}</span><div className="scheme-decoration deco-a" /><div className="scheme-decoration deco-b" /></div>
      <div className="scholarship-card-body">
        <div className="scheme-provider">{scholarship.provider || "Scholarship program"}{scholarship.verified_at && <span title="Admin verified"><ShieldCheck size={14} /></span>}</div>
        <h3>{scholarship.title}</h3>
        <p className="scheme-summary">{scholarship.eligibility_summary}</p>
        <div className="scheme-meta">
          <div><span className="meta-label">Award</span><strong>{scholarship.award_amount || "As per scheme"}</strong></div>
          <div><span className="meta-label">Deadline</span><strong>{formatDate(scholarship.deadline)}</strong></div>
        </div>
        <div className="scheme-tags">{(scholarship.categories || []).slice(0, 3).map((item) => <span key={item}>{item.toUpperCase()}</span>)}</div>
        <div className="scheme-actions">{onAdd ? (isExpired ? <span className="deadline-passed-label">{t("Deadline passed")}</span> : <button className="button button-primary button-small" disabled={creating} onClick={onAdd}>{creating ? <LoaderCircle size={15} className="spin" /> : <Plus size={15} />}{t("Apply for this scholarship")}</button>) : <button className="button button-primary button-small" onClick={onOpen}>{t("View opportunities")} <ArrowRight size={15} /></button>}<div className="scheme-secondary-actions">{onEligibility && <button className="mini-action" onClick={onEligibility}>{t("Eligibility")}</button>}{onRate && <button className="mini-action" onClick={onRate}><Star size={12} /> {t("Rate")}</button>}</div><label className={`compare-checkbox ${selected ? "compare-checked" : ""}`}><input type="checkbox" checked={Boolean(selected)} onChange={onToggleCompare} aria-label={`${t("Compare")} ${scholarship.title}`} /><span>{selected ? <Check size={13} /> : null}</span>{t("Compare")}</label></div>
      </div>
    </article>
  );
}

function ApplicationFormModal({ scholarship, token, user, existingApplication = null, onClose, onSubmitted }) {
  const [form, setForm] = useState({
    full_name: existingApplication?.application_form?.full_name || user.full_name || "",
    mobile: existingApplication?.application_form?.mobile || user.mobile || "",
    district: existingApplication?.application_form?.district || "",
    category: existingApplication?.application_form?.category || "",
    family_income_range: existingApplication?.application_form?.family_income_range || "",
    course: existingApplication?.application_form?.course || "",
    year_of_study: existingApplication?.application_form?.year_of_study == null
      ? ""
      : String(existingApplication.application_form.year_of_study),
    college: existingApplication?.application_form?.college || "",
    previous_percentage: existingApplication?.application_form?.previous_percentage || "",
  });
  const [files, setFiles] = useState({});
  const [bankDetails, setBankDetails] = useState({ account_number: "", ifsc: "" });
  const [bankDetailsConsent, setBankDetailsConsent] = useState(Boolean(existingApplication?.bank_details_consent_at));
  const [bankDetailsSaved, setBankDetailsSaved] = useState(Boolean(existingApplication?.bank_details_consent_at));
  const [applicationId, setApplicationId] = useState(existingApplication?.id || "");
  const [uploadedNames, setUploadedNames] = useState((existingApplication?.documents || []).map((document) => document.name));
  const [documentConsent, setDocumentConsent] = useState(Boolean(existingApplication?.document_consent_at));
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [uploadingDocument, setUploadingDocument] = useState("");
  const [uploadProgress, setUploadProgress] = useState(0);
  const [colleges, setColleges] = useState([]);
  const isCorrection = existingApplication?.status === "correction_required";
  const requiredDocuments = scholarship.documents || [];

  useEffect(() => {
    api("/api/colleges/list", {}, token)
      .then(({ colleges: registeredColleges }) => setColleges(registeredColleges || []))
      .catch((requestError) => setError(requestError.message));
  }, [token]);

  useEffect(() => {
    if (existingApplication) return;
    api("/api/profile", {}, token)
      .then(({ profile }) => setForm((current) => ({
        ...current,
        district: profile.district || "",
        category: profile.category || "",
        family_income_range: profile.family_income_range || "",
        course: profile.course || "",
        year_of_study: profile.year_of_study == null ? "" : String(profile.year_of_study),
        college: colleges.some((college) => college.name === profile.college) ? profile.college : "",
        previous_percentage: profile.previous_percentage == null ? "" : String(profile.previous_percentage),
      })))
      .catch(() => setError(t("Saved profile details could not be loaded. Please enter the information manually.")));
  }, [token, colleges]);

  function updateField(event) {
    setForm((current) => ({ ...current, [event.target.name]: event.target.value }));
  }

  function updateBankField(event) {
    setBankDetails((current) => ({ ...current, [event.target.name]: event.target.value }));
  }

  async function submitApplication(event) {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      let id = applicationId;
      if (!id) {
        const { application, resumed } = await api("/api/applications", {
          method: "POST",
          body: JSON.stringify({
            scholarship_id: scholarship.id,
            application_form: form,
            document_consent: documentConsent,
            bank_details: bankDetails,
            bank_details_consent: bankDetailsConsent,
          }),
        }, token);
        id = application.id;
        setApplicationId(id);
        setUploadedNames((current) => [...new Set([
          ...current,
          ...(application.documents || []).map((document) => document.name),
        ])]);
        const savedBankDetails = Boolean(application.bank_details_consent_at);
        setBankDetailsSaved(savedBankDetails);
        if (savedBankDetails) setBankDetailsConsent(true);
        if (resumed) await saveDraftDetails(id, savedBankDetails);
      } else {
        await saveDraftDetails(id, bankDetailsSaved);
      }

      const selectedDocuments = [
        ...requiredDocuments.map((name) => ({ name, required: true })),
        ...OPTIONAL_DOCUMENTS.filter((name) => files[name]).map((name) => ({ name, required: false })),
      ];
      for (const document of selectedDocuments) {
        if (!files[document.name] || (uploadedNames.includes(document.name) && !isCorrection)) continue;
        setUploadingDocument(document.name);
        setUploadProgress(0);
        const result = await uploadApplicationDocument(id, document.name, files[document.name]);
        setUploadedNames((current) => [...new Set([...current, document.name])]);
        if (!result.document) throw new Error("Document upload response was incomplete.");
      }
      setUploadingDocument("");
      const { application } = await api(`/api/applications/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ status: "submitted" }),
      }, token);
      onSubmitted(application);
    } catch (requestError) {
      setUploadingDocument("");
      setError(requestError.message);
    } finally {
      setSubmitting(false);
    }
  }

  async function saveDraftDetails(id, bankDetailsAreSaved) {
    const update = { application_form: form };
    const hasEnteredBankDetails = bankDetails.account_number || bankDetails.ifsc;
    if (!isCorrection && (!bankDetailsAreSaved || hasEnteredBankDetails)) {
      update.bank_details = bankDetails;
      update.bank_details_consent = bankDetailsConsent;
    }
    await api(`/api/applications/${id}`, {
      method: "PATCH",
      body: JSON.stringify(update),
    }, token);
  }

  function uploadApplicationDocument(id, documentName, file) {
    return new Promise((resolve, reject) => {
      const request = new XMLHttpRequest();
      request.open("POST", `/api/applications/${id}/documents`);
      request.setRequestHeader("Authorization", `Bearer ${token}`);
      request.upload.onprogress = (event) => {
        if (event.lengthComputable) setUploadProgress(Math.round((event.loaded / event.total) * 100));
      };
      request.onload = () => {
        let data = {};
        try {
          data = JSON.parse(request.responseText);
        } catch {
          reject(new Error(t("The document upload returned an unreadable response. Retry the upload.")));
          return;
        }
        if (request.status < 200 || request.status >= 300) {
          reject(new Error(data.error || t("The document could not be uploaded. Retry the upload.")));
          return;
        }
        setUploadProgress(100);
        resolve(data);
      };
      request.onerror = () => reject(new Error(t("Document upload failed. Check your internet connection and retry.")));
      request.onabort = () => reject(new Error(t("Document upload was cancelled. You can try again.")));
      const body = new FormData();
      body.append("document_name", documentName);
      body.append("file", file);
      request.send(body);
    });
  }

  const requiredUploadMissing = requiredDocuments.some((name) => !files[name] && !uploadedNames.includes(name));
  return <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && !submitting && onClose()}>
    <section className="application-modal" role="dialog" aria-modal="true" aria-labelledby="application-form-title">
      <div className="modal-heading"><div><div className="eyebrow">{t("STUDENT APPLICATION")}</div><h2 id="application-form-title">{scholarship.title}</h2><p>{t(isCorrection ? (existingApplication?.correction_requested_by === "admin" ? "Update the requested details and resubmit to the administrator for review." : "Update the requested details and resubmit to your college for verification.") : "Your application will be reviewed by your college verifier, then by the department admin.")}</p></div><button className="icon-button" onClick={onClose} disabled={submitting} aria-label={t("Close application form")}><X size={20} /></button></div>
      <form className="application-modal-form" onSubmit={submitApplication}>
        <div className="application-form-grid">
          <label>{t("Full name")}<input name="full_name" value={form.full_name} onChange={updateField} maxLength="120" required /></label>
          <label>{t("Mobile number")}<input name="mobile" value={form.mobile} onChange={updateField} maxLength="20" required /></label>
          <label>{t("District")}<select name="district" value={form.district} onChange={updateField} required><option value="">{t("Choose district")}</option>{MAHARASHTRA_DISTRICTS.map((district) => <option value={district.name} key={district.name}>{districtLabel(district.name, getLocale())}</option>)}</select></label>
          <label>{t("Category")}<select name="category" value={form.category} onChange={updateField} required><option value="">{t("Choose category")}</option>{["open", "obc", "sc", "st", "vjnt", "sbc", "ews", "minority"].map((item) => <option value={item} key={item}>{item.toUpperCase()}</option>)}</select></label>
          <label>{t("Course")}<input name="course" value={form.course} onChange={updateField} maxLength="120" required /></label>
          <label>{t("Year of study")}<input name="year_of_study" value={form.year_of_study} onChange={updateField} maxLength="40" /></label>
          <label>{t("Registered college")}<select name="college" value={form.college} onChange={updateField} required><option value="">{t("Choose your registered college")}</option>{isCorrection && existingApplication?.college_name && !colleges.some((college) => college.name === existingApplication.college_name) && <option value={existingApplication.college_name}>{existingApplication.college_name} · {t("Inactive; administrator review")}</option>}{colleges.map((college) => <option value={college.name} key={college.id}>{college.name} · {college.code}</option>)}</select></label>
          <label>{t("Family annual income")}<select name="family_income_range" value={form.family_income_range} onChange={updateField}><option value="">{t("Select income range")}</option><option value="below_1_lakh">{t("Below ₹1 lakh")}</option><option value="1_to_2_5_lakh">{t("₹1–2.5 lakh")}</option><option value="2_5_to_5_lakh">{t("₹2.5–5 lakh")}</option><option value="5_to_8_lakh">{t("₹5–8 lakh")}</option><option value="above_8_lakh">{t("Above ₹8 lakh")}</option></select></label>
          <label>{t("Previous exam percentage")}<input name="previous_percentage" value={form.previous_percentage} onChange={updateField} maxLength="20" /></label>
        </div>
        {!isCorrection && <section className="application-bank-details">
          <div><h3>{t("Bank details for demo scholarship payment")}</h3><p>{t("Enter the account that would receive the scholarship. These details are encrypted and visible only to the separate finance role after approval.")}</p></div>
          <div className="application-form-grid">
            <label>{t("Bank account number")}<input name="account_number" inputMode="numeric" autoComplete="off" pattern="[0-9 ]{9,21}" maxLength="21" value={bankDetails.account_number} onChange={(event) => setBankDetails((current) => ({ ...current, account_number: event.target.value.replace(/[^0-9 ]/g, "") }))} required={!bankDetailsSaved} /></label>
            <label>{t("IFSC code")}<input name="ifsc" autoComplete="off" pattern="[A-Za-z]{4}0[A-Za-z0-9]{6}" maxLength="11" value={bankDetails.ifsc} onChange={(event) => setBankDetails((current) => ({ ...current, ifsc: event.target.value.toUpperCase() }))} required={!bankDetailsSaved} /></label>
          </div>
          {bankDetailsSaved && <p className="saved-bank-details-note">{t("Bank details are already saved securely. Leave the fields blank to keep them unchanged.")}</p>}
          <label className="application-document-consent"><input type="checkbox" checked={bankDetailsConsent} onChange={(event) => setBankDetailsConsent(event.target.checked)} required={!bankDetailsSaved} /><span>{t("I consent to encrypting my bank account and IFSC for this application. The separate finance role can access only these payout details and the fixed scheme amount. This demo does not transfer money.")}</span></label>
        </section>}
        <section className="application-modal-documents">
          <div><h3>{t("Upload required documents")}</h3><p>{t("Your documents are encrypted and visible only to authorized college and department reviewers.")}</p><p>{t("PDF, JPG or PNG · Maximum 8 MB. Photos are checked for clarity.")}</p></div>
          {requiredDocuments.length ? requiredDocuments.map((name) => <label className="application-file-field" key={name}>{t(name)} <span>{t("Required")}</span><input type="file" accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png" required={!uploadedNames.includes(name)} onChange={(event) => setFiles((current) => ({ ...current, [name]: event.target.files?.[0] || null }))} />{uploadedNames.includes(name) && <em>{t("Uploaded securely")}</em>}</label>) : <p>{t("No required files are listed for this scheme.")}</p>}
          <div className="optional-document-list"><strong>{t("Optional documents")}</strong><p>{t("Upload only if it applies to your application; confirm the official scheme rules.")}</p>{OPTIONAL_DOCUMENTS.filter((name) => !requiredDocuments.some((item) => item.toLowerCase() === name.toLowerCase())).map((name) => <label className="application-file-field" key={name}>{t(name)}<input type="file" accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png" onChange={(event) => setFiles((current) => ({ ...current, [name]: event.target.files?.[0] || null }))} />{uploadedNames.includes(name) && <em>{t("Uploaded securely")}</em>}</label>)}</div>
        </section>
        <label className="application-document-consent"><input type="checkbox" checked={documentConsent} onChange={(event) => setDocumentConsent(event.target.checked)} required disabled={Boolean(existingApplication?.document_consent_at)} /><span>{t("I consent to encrypting these documents and allowing authorized college and department reviewers to review them for this application.")}</span></label>
        <div className="application-privacy-note"><ShieldCheck size={16} /><span>{t("Documents and bank details are encrypted at rest. The reviewer cannot see bank details. Finance is simulation-only; no payment is sent and no funds are transferred.")}</span></div>
        {!isCorrection && !scholarship.payout_amount && <div className="application-payout-note"><CircleHelp size={16} /><span>{t("The fixed demo amount is not set yet. You can still submit your application; an administrator must configure the amount before approval.")}</span></div>}
        {uploadingDocument && <div className="upload-progress"><div><span>{t("Uploading document")} · {t(uploadingDocument)}</span><strong>{uploadProgress}%</strong></div><div className="progress-track"><span style={{ width: `${uploadProgress}%` }} /></div></div>}
        {error && <ErrorMessage>{error}</ErrorMessage>}
        <div className="modal-footer"><span>{t("You can retry uploads if a network error occurs.")}</span><button className="button button-primary" disabled={submitting || requiredUploadMissing || !documentConsent || (!isCorrection && !bankDetailsConsent)}><Send size={15} />{submitting ? t("Submitting…") : isCorrection ? t("Resubmit for verification") : t("Submit application")}</button></div>
      </form>
    </section>
  </div>;
}

function EligibilityModal({ result, onClose }) {
  const { scholarship, result: eligibility } = result;
  const labels = {
    eligible: ["Looks like a match", "You meet the currently listed criteria."],
    not_eligible: ["Some criteria don't match", "Review the unmet items and verify the full scheme rules."],
    needs_more_information: ["A few details are missing", "Complete your profile to get a more useful estimate."],
  };
  const [title, description] = labels[eligibility.status] || labels.needs_more_information;
  const fields = [...(eligibility.missing_information || []), ...(eligibility.unmet_criteria || [])];
  return <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}><section className="simple-modal" role="dialog" aria-modal="true" aria-labelledby="eligibility-title"><div className="modal-heading"><div><div className="eyebrow">PERSONALIZED ESTIMATE</div><h2 id="eligibility-title">Eligibility check</h2></div><button className="icon-button" onClick={onClose} aria-label="Close eligibility result"><X size={20} /></button></div><div className="eligibility-result"><div className={`eligibility-symbol eligibility-${eligibility.status}`}><ShieldCheck size={24} /></div><h3>{t(title)}</h3><p>{t(description)}</p><strong className="eligibility-scheme">{scholarship.title}</strong>{fields.length > 0 && <div className="eligibility-fields"><span>{t(eligibility.missing_information?.length ? "Information to complete" : "Criteria to review")}</span><div>{fields.map((field) => <span key={field}>{t(field.replaceAll("_", " "))}</span>)}</div></div>}{eligibility.matched_criteria?.length > 0 && <div className="eligibility-matched"><CheckCircle2 size={15} /> {eligibility.matched_criteria.length} {t("criteria matched")}</div>}<div className="privacy-callout"><CircleHelp size={17} /><span>{t(result.disclaimer)}</span></div></div><div className="modal-footer"><span>{t("Guidance only — official scheme rules take precedence.")}</span><button className="button button-dark" onClick={onClose}>{t("Got it")}</button></div></section></div>;
}

function RatingModal({ scholarship, onClose, onSubmit }) {
  const [rating, setRating] = useState(0);
  const [comment, setComment] = useState("");
  return <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}><section className="simple-modal" role="dialog" aria-modal="true" aria-labelledby="rating-title"><div className="modal-heading"><div><div className="eyebrow">STUDENT FEEDBACK</div><h2 id="rating-title">Rate this scholarship</h2></div><button className="icon-button" onClick={onClose} aria-label="Close rating"><X size={20} /></button></div><form className="rating-form" onSubmit={(event) => { event.preventDefault(); if (rating) onSubmit(rating, comment); }}><p>{scholarship.title}</p><div className="rating-stars" role="group" aria-label="Rating from 1 to 5">{[1, 2, 3, 4, 5].map((value) => <button key={value} type="button" className={value <= rating ? "star-selected" : ""} onClick={() => setRating(value)} aria-label={`${value} star${value === 1 ? "" : "s"}`}><Star size={27} fill={value <= rating ? "currentColor" : "none"} /></button>)}</div><label>Optional comment<textarea rows="3" maxLength="1000" value={comment} onChange={(event) => setComment(event.target.value)} placeholder="Share a helpful note about this scheme" /></label><div className="modal-footer"><span>Your feedback helps other students.</span><button className="button button-primary" disabled={!rating}><Send size={15} /> Submit rating</button></div></form></section></div>;
}

function ComparisonModal({ comparison, onClose }) {
  const rows = [
    ["Provider", (item) => item.provider],
    ["Study level", (item) => item.education_level],
    ["Categories", (item) => item.categories?.join(", ")],
    ["Award", (item) => item.award_amount || "As per scheme"],
    ["Deadline", (item) => formatDate(item.deadline)],
    ["Eligibility", (item) => item.eligibility_summary],
    ["Documents", (item) => item.documents?.join(", ") || "Check official guidelines"],
  ];
  return <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}><section className="comparison-modal" role="dialog" aria-modal="true" aria-labelledby="compare-title"><div className="modal-heading"><div><div className="eyebrow">MAKE AN INFORMED CHOICE</div><h2 id="compare-title">Compare scholarships</h2></div><button className="icon-button" onClick={onClose} aria-label="Close comparison"><X size={20} /></button></div><div className="comparison-scroll"><table className="comparison-table"><thead><tr><th>Details</th>{comparison.map((item) => <th key={item.id}>{item.title}</th>)}</tr></thead><tbody>{rows.map(([label, getValue]) => <tr key={label}><th>{label}</th>{comparison.map((item) => <td key={item.id}>{getValue(item) || "—"}</td>)}</tr>)}</tbody></table></div><div className="modal-footer"><span>Confirm current details on each official scheme website.</span><button className="button button-dark" onClick={onClose}>Done</button></div></section></div>;
}

function Recommendations({ token, profile, navigate }) {
  const [items, setItems] = useState([]);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    api("/api/profile/recommendations?limit=3", {}, token)
      .then((data) => {
        setItems(data.recommendations || []);
        setMessage(data.missing_profile_fields?.length
          ? "Add your category, education level and domicile to unlock personalized matches."
          : "");
      })
      .catch((requestError) => setMessage(requestError.message))
      .finally(() => setLoading(false));
  }, [token, profile]);
  return <section className="panel recommendations-panel"><div className="section-heading"><div><div className="eyebrow">BASED ON YOUR PROFILE</div><h2>Picked for your journey</h2></div><button className="text-link" onClick={() => navigate("profile")}>Edit profile <ArrowRight size={14} /></button></div>{loading ? <Loading label="Finding your matches…" /> : items.length ? <div className="recommendation-list">{items.map((item) =>   <div className="recommendation-row" key={item.scholarship.id}><div className="recommendation-icon"><Sparkles size={16} /></div><div className="recommendation-copy"><strong>{item.scholarship.title}</strong><span>{item.scholarship.provider} · {t(item.eligibility.status.replaceAll("_", " "))}</span></div><div className="match-score"><strong>{item.match_score}%</strong><span>{t("match")}</span></div><button className="icon-button" onClick={() => navigate("scholarships")} aria-label={`${t("Explore")} ${item.scholarship.title}`}><ArrowRight size={17} /></button></div>)}</div> : <div className="recommendation-empty"><UserRound size={19} /><span>{message.includes("Complete more") ? "Add your category, education level and domicile to unlock personalized matches." : message || "No matches are available just yet."}</span><button className="text-link" onClick={() => navigate("profile")}>Complete profile <ArrowRight size={14} /></button></div>}</section>;
}

function Applications({ token, notify, initialEditId = "", onInitialEditHandled }) {
  const [applications, setApplications] = useState([]);
  const [totals, setTotals] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState("");
  const [continuingApplication, setContinuingApplication] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await api("/api/applications/dashboard", {}, token);
      setApplications(data.applications || []);
      setTotals(data.totals || {});
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }, [token]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (!initialEditId || !applications.some((application) => application.id === initialEditId)) return;
    setEditing(initialEditId);
    onInitialEditHandled();
  }, [applications, initialEditId, onInitialEditHandled]);

  async function updateApplication(application, changes) {
    try {
      await api(`/api/applications/${application.id}`, { method: "PATCH", body: JSON.stringify(changes) }, token);
      notify("Application tracker updated.");
      setEditing("");
      load();
    } catch (requestError) {
      notify(requestError.message);
    }
  }

  return (
    <>
      <PageHeading eyebrow="ONE PLACE, EVERY UPDATE" title="My applications" description={t("Track your application through college verification and department review. After approval, fund distribution remains pending until the administrator records it.")} action={<button className="button button-primary" onClick={load}><ArrowDownUp size={16} /> Refresh tracker</button>} />
      <div className="application-summary-grid">{STATUSES.map((status) => <div key={status} className="summary-tile"><span>{t(status === "submitted" ? "Pending college review" : status === "college_verified" ? "Pending administrator review" : STATUS_LABELS[status])}</span><strong>{totals[status] || 0}</strong></div>)}</div>
      {error && <ErrorMessage onRetry={load}>{error}</ErrorMessage>}
      {loading ? <Loading label="Loading your applications…" /> : applications.length ? <div className="tracker-list">{applications.map((application) => <ApplicationTrackerCard key={application.id} application={application} token={token} editing={editing === application.id} onEdit={() => application.status === "draft" || application.status === "correction_required" ? setContinuingApplication(application) : setEditing(editing === application.id ? "" : application.id)} onSave={(changes) => updateApplication(application, changes)} />)}</div> : <EmptyState icon={ListChecks} title="No applications yet">Find a scheme that fits, then add it to your tracker to get started.</EmptyState>}
      {continuingApplication && <ApplicationFormModal scholarship={{ id: continuingApplication.scholarship_id, title: continuingApplication.scholarship_title, documents: continuingApplication.checklist.map((item) => item.name) }} existingApplication={continuingApplication} token={token} user={{}} onClose={() => setContinuingApplication(null)} onSubmitted={() => { setContinuingApplication(null); load(); }} />}
    </>
  );
}

function ApplicationTrackerCard({ application, token, editing, onEdit, onSave }) {
  const [reminder, setReminder] = useState(application.reminder_date || "");
  const [notes, setNotes] = useState(application.notes || "");
  const checklist = application.checklist || [];
  const [timelineOpen, setTimelineOpen] = useState(false);
  const completed = checklist.filter((item) => item.completed).length;
  const pendingStatus = application.status === "submitted" || application.status === "college_verified";
  return <article className="tracker-card"><div className="tracker-card-head"><div className="app-logo app-logo-large">{initials(application.scholarship_title)}</div><div className="tracker-title"><div className="eyebrow">{t("APPLICATION")} · {application.id.slice(0, 8)}</div><h3>{application.scholarship_title}</h3><span>{t("Submitted")} {formatDate(application.application_date)}</span></div>{pendingStatus ? <StatusBadge status={application.status} label={t("Pending")} /> : <StatusBadge status={application.status} />}{application.status === "draft" ? <button className="button button-primary button-small tracker-edit" onClick={onEdit}>{t("Continue application")}</button> : <button className="button button-outline button-small tracker-edit" onClick={onEdit}>{editing ? t("Close") : t("Update tracker")}</button>}<button className="icon-button timeline-toggle" onClick={() => setTimelineOpen((value) => !value)} aria-label={t("View application timeline")} title={t("View application timeline")}><History size={17} /></button></div>
    {application.status === "submitted" && <div className="application-pending-note"><Clock3 size={16} /><span>{t("Your application is pending college verification.")}</span></div>}
    {application.status === "college_verified" && <div className="application-pending-note"><Clock3 size={16} /><span>{t("College verification is complete. Your application is pending administrator approval.")}</span></div>}
    {application.status === "approved" && <div className="approved-funds-note"><CheckCircle2 size={18} /><div><strong>{t("Approved — fund distribution pending")}</strong><p>{application.admin_note || t("The administrator approved your application. Fund distribution has not yet been recorded.")}</p></div></div>}
    {application.status === "paid" && application.distribution_mode === "simulated" && <div className="distribution-demo-note"><CheckCircle2 size={17} /><span>{t("Demo payment recorded:")} ₹{application.distributed_amount}. {t("No money was transferred.")}</span></div>}
    {application.application_form && Object.keys(application.application_form).length > 0 && <div className="application-submitted-details"><strong>{t("Application details")}</strong><span>{application.application_form.full_name} · {application.application_form.district} · {application.application_form.course} · {application.application_form.college}</span></div>}
    {application.documents?.length > 0 && <div className="checklist-chips">{application.documents.map((item) => <span className="checklist-done" key={item.id}><CheckCircle2 size={14} />{t(item.name)}</span>)}</div>}
    {checklist.length > 0 && <div className="tracker-progress"><div className="progress-heading"><span>{t("Required documents")}</span><strong>{completed} {t("of")} {checklist.length} {t("uploaded")}</strong></div><div className="progress-track"><span style={{ width: `${Math.round(completed / checklist.length * 100)}%` }} /></div></div>}
    {application.status === "correction_required" && <div className="rejection-note"><CircleHelp size={17} /><div><strong>{t(application.correction_requested_by === "admin" ? "Administrator requested changes" : "College requested a correction")}</strong><p>{application.correction_requested_by === "admin" ? application.admin_note : application.college_note || t("Update the requested information and resubmit.")}</p><button className="button button-outline button-small" onClick={onEdit}>{t("Edit and resubmit")}</button></div></div>}
    {application.college_note && application.status !== "correction_required" && <div className="application-admin-note"><strong>{t("College verifier note")}</strong><p>{application.college_note}</p></div>}
    {application.status === "rejected" && (application.rejection_reason || application.college_note) && <div className="rejection-note"><CircleHelp size={17} /><div><strong>{t("Rejection reason")}</strong><p>{application.rejection_reason || application.college_note}</p></div></div>}
    {application.admin_note && application.status !== "approved" && application.status !== "correction_required" && <div className="application-admin-note"><strong>{t("Administrator note")}</strong><p>{application.admin_note}</p></div>}
    {application.reminder_date && <div className="reminder-note"><Bell size={15} /> Reminder set for {formatDate(application.reminder_date)}</div>}
    {timelineOpen && <ApplicationTimeline applicationId={application.id} token={token} />}
    {editing && application.status !== "draft" && application.status !== "correction_required" && <form className="tracker-edit-form" onSubmit={(event) => { event.preventDefault(); onSave({ reminder_date: reminder || null, notes }); }}>
      <div className="form-grid"><label>{t("Reminder date")}<input type="date" value={reminder} onChange={(event) => setReminder(event.target.value)} /></label><label className="form-span">{t("Private notes")}<textarea value={notes} onChange={(event) => setNotes(event.target.value)} rows="2" /></label></div>
      <button className="button button-primary button-small" type="submit"><Check size={15} /> {t("Save changes")}</button>
    </form>}
  </article>;
}

const OPTIONAL_DOCUMENTS = [
  "Bank passbook",
  "Income certificate",
  "Domicile certificate",
  "Admission receipt",
];

function DocumentCheckUpload({ token, documentName, onCheckComplete }) {
  const [file, setFile] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [progress, setProgress] = useState(0);
  const [checking, setChecking] = useState(false);

  function chooseFile(event) {
    setFile(event.target.files?.[0] || null);
    setResult(null);
    setError("");
    setProgress(0);
  }

  function checkFile() {
    setError("");
    setResult(null);
    if (!file) {
      setError(t("Choose a PDF, JPG or PNG file before running the check."));
      return;
    }
    const supported = ["application/pdf", "image/jpeg", "image/png"].includes(file.type)
      || /\.(pdf|jpe?g|png)$/i.test(file.name);
    if (!supported) {
      setError(t("This file type isn't supported. Choose a PDF, JPG or PNG scan."));
      return;
    }
    if (file.size > 8 * 1024 * 1024) {
      setError(t("This file is larger than 8 MB. Crop it or export a smaller scan and retry."));
      return;
    }
    if (file.size === 0) {
      setError(t("This file is empty. Choose another scan and retry."));
      return;
    }

    onCheckComplete?.(false);
    setChecking(true);
    setProgress(0);
    const request = new XMLHttpRequest();
    request.open("POST", "/api/applications/documents/check");
    request.setRequestHeader("Authorization", `Bearer ${token}`);
    request.upload.onprogress = (event) => {
      if (event.lengthComputable) setProgress(Math.round((event.loaded / event.total) * 100));
    };
    request.onload = () => {
      let data = {};
      try {
        data = JSON.parse(request.responseText);
      } catch {
        setError(t("The checker returned an unreadable response. Please retry."));
        setChecking(false);
        return;
      }
      if (request.status < 200 || request.status >= 300) {
        setError(data.error || t("The document could not be checked. Please retry."));
      } else {
        setProgress(100);
        setResult(data);
        onCheckComplete?.(Boolean(data.valid));
      }
      setChecking(false);
    };
    request.onerror = () => {
      setError(t("Upload failed. Check your internet connection and retry. Your file is not stored."));
      setChecking(false);
    };
    request.onabort = () => {
      setError(t("Upload was cancelled. You can try again."));
      setChecking(false);
    };
    const formData = new FormData();
    formData.append("file", file);
    request.send(formData);
  }

  function downloadProcessedFile() {
    if (!result?.processed_file_base64 || !file) return;
    const binary = atob(result.processed_file_base64);
    const bytes = Uint8Array.from(binary, (character) => character.charCodeAt(0));
    const blob = new Blob([bytes], { type: result.file_type || file.type });
    const extension = result.file_type === "application/pdf" ? "pdf" : result.file_type === "image/png" ? "png" : "jpg";
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `${file.name.replace(/\.[^.]+$/, "")}-checked.${extension}`;
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(link.href), 1000);
  }

  return <div className="application-document-upload">
    <label>{t(documentName)}<input type="file" accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png" onChange={chooseFile} disabled={checking} /></label>
    <button className="button button-outline button-small" type="button" onClick={checkFile} disabled={!file || checking}>{checking ? <LoaderCircle size={14} className="spin" /> : <Upload size={14} />}{checking ? t("Checking…") : result || error ? t("Retry check") : t("Check")}</button>
    {checking && <div className="upload-progress"><div><span>{t("Uploading and checking…")}</span><strong>{progress}%</strong></div><div className="progress-track"><span style={{ width: `${progress}%` }} /></div></div>}
    {error && <span className="document-upload-error" role="alert">{error}</span>}
    {result && <div className={`document-upload-result ${result.valid ? "document-valid" : "document-invalid"}`} role="status"><span>{result.guidance}</span>{result.processed_file_base64 && <button className="text-link" type="button" onClick={downloadProcessedFile}>{t("Download checked copy")} <ArrowDownToLine size={14} /></button>}</div>}
  </div>;
}

function ApplicationTimeline({ applicationId, token }) {
  const [timeline, setTimeline] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    api(`/api/applications/${applicationId}/timeline`, {}, token)
      .then(setTimeline)
      .catch((requestError) => setError(requestError.message));
  }, [applicationId, token]);
  if (error) return <ErrorMessage>{error}</ErrorMessage>;
  if (!timeline) return <Loading label="Loading application timeline…" />;
  return <div className="application-timeline"><div className="eyebrow">{t("APPLICATION JOURNEY")}</div>{timeline.timeline.map((stage, index) => <div className="timeline-entry" key={`${stage.status}-${stage.at}-${index}`}><div className="timeline-marker">{index === timeline.timeline.length - 1 ? <Check size={12} /> : null}</div><div><strong>{t(STATUS_LABELS[stage.status] || stage.status)}</strong><span>{new Date(stage.at).toLocaleString()}</span><p>{t(stage.guidance)}</p></div></div>)}<p className="timeline-disclaimer">{t(timeline.payment_guidance)}</p></div>;
}

function Profile({ token, user, onUserChange, notify, language }) {
  const [form, setForm] = useState(EMPTY_PROFILE);
  const [savedForm, setSavedForm] = useState(EMPTY_PROFILE);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [profileSaved, setProfileSaved] = useState(false);
  const [editing, setEditing] = useState(true);

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), 10000);
    setLoading(true);
    setError("");

    api("/api/profile", { signal: controller.signal }, token)
      .then(({ profile }) => {
        if (!active) return;
        if (!profile || typeof profile !== "object" || Array.isArray(profile)) {
          throw new Error("Something went wrong. Please try again.");
        }
        const profileForm = {
          ...EMPTY_PROFILE,
          ...Object.fromEntries(PROFILE_FIELDS.filter((field) => field in profile).map((field) => [field, profile[field]])),
          minority: profile.minority == null ? "" : String(profile.minority),
          divyang: profile.divyang == null ? "" : String(profile.divyang),
          maharashtra_domicile: profile.maharashtra_domicile == null ? "" : String(profile.maharashtra_domicile),
          year_of_study: profile.year_of_study || "",
          previous_percentage: profile.previous_percentage ?? "",
        };
        const hasSavedProfile = Boolean(profile.updated_at) || PROFILE_FIELDS.some(
          (field) => field !== "preferred_language" && profile[field] !== null && profile[field] !== undefined && profile[field] !== "",
        );
        setForm(profileForm);
        setSavedForm(profileForm);
        setProfileSaved(hasSavedProfile);
        setEditing(!hasSavedProfile);
      })
      .catch((requestError) => {
        if (active) {
          setError(controller.signal.aborted
            ? "Something went wrong. Please try again."
            : requestError.message);
        }
      })
      .finally(() => {
        window.clearTimeout(timeoutId);
        if (active) setLoading(false);
      });

    return () => {
      active = false;
      window.clearTimeout(timeoutId);
      controller.abort();
    };
  }, [token, loadAttempt]);

  const setField = (field, value) => setForm((current) => ({ ...current, [field]: value }));
  async function save(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    const payload = Object.fromEntries(PROFILE_FIELDS.map((field) => [field, form[field]]));
    for (const field of ["minority", "divyang", "maharashtra_domicile"]) payload[field] = form[field] === "" ? null : form[field] === "true";
    payload.year_of_study = form.year_of_study === "" ? null : Number(form.year_of_study);
    payload.previous_percentage = form.previous_percentage === "" ? null : Number(form.previous_percentage);
    for (const field of ["category", "family_income_range", "district", "course", "college", "university"]) if (payload[field] === "") payload[field] = null;
    try {
      const { profile } = await api("/api/profile", { method: "PATCH", body: JSON.stringify(payload) }, token);
      const saved = {
        ...form,
        ...Object.fromEntries(PROFILE_FIELDS.filter((field) => field in profile).map((field) => [field, profile[field]])),
        minority: profile.minority == null ? "" : String(profile.minority),
        divyang: profile.divyang == null ? "" : String(profile.divyang),
        maharashtra_domicile: profile.maharashtra_domicile == null ? "" : String(profile.maharashtra_domicile),
        year_of_study: profile.year_of_study || "",
        previous_percentage: profile.previous_percentage ?? "",
      };
      setForm(saved);
      setSavedForm(saved);
      setProfileSaved(true);
      setEditing(false);
      notify("Your profile has been saved.");
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <PageHeading eyebrow="A LITTLE ABOUT YOU" title="Your student profile" description="Add what you're comfortable sharing to get more relevant scholarship matches." />
      <div className="profile-layout"><div className="profile-main">
        <section className="panel identity-panel"><div className="avatar avatar-large">{initials(user.full_name)}</div><div><h2>{user.full_name}</h2><p>{user.email}</p><span className="verified-pill"><CheckCircle2 size={14} /> Email verified</span></div><div className="student-id"><span>STUDENT ID</span><strong>{user.user_id}</strong></div></section>
        {error && <ErrorMessage onRetry={() => setLoadAttempt((attempt) => attempt + 1)}>{error}</ErrorMessage>}
        {loading ? <Loading label="Loading your profile…" /> : <form className="panel profile-form" onSubmit={save}>
          <div className="section-heading"><div><div className="eyebrow">PERSONALIZE YOUR DISCOVERY</div><h2>Study & eligibility details</h2></div></div>
          <p className="form-intro">These details help match you with relevant schemes. All fields are optional.</p>
          <fieldset className="profile-fields" disabled={!editing || saving}>
          <div className="form-grid">
            <label>Category<select value={form.category || ""} onChange={(event) => setField("category", event.target.value)}><option value="">Choose category</option>{["open", "obc", "sc", "st", "vjnt", "sbc", "ews", "minority"].map((value) => <option value={value} key={value}>{value.toUpperCase()}</option>)}</select></label>
            <label>Family annual income<select value={form.family_income_range || ""} onChange={(event) => setField("family_income_range", event.target.value)}><option value="">Choose income range</option><option value="below_1_lakh">Below ₹1 lakh</option><option value="1_to_2_5_lakh">₹1–2.5 lakh</option><option value="2_5_to_5_lakh">₹2.5–5 lakh</option><option value="5_to_8_lakh">₹5–8 lakh</option><option value="above_8_lakh">Above ₹8 lakh</option></select></label>
            <label>Education level<select value={form.education_level || ""} onChange={(event) => setField("education_level", event.target.value)}><option value="">Choose level</option><option value="school">School</option><option value="undergraduate">Undergraduate</option><option value="postgraduate">Postgraduate</option><option value="doctoral">Doctoral</option><option value="other">Other</option></select></label>
            <label>Course<input value={form.course || ""} onChange={(event) => setField("course", event.target.value)} placeholder="e.g. B.Tech Computer Engineering" maxLength="120" /></label>
            <label>Year of study<select value={form.year_of_study || ""} onChange={(event) => setField("year_of_study", event.target.value)}><option value="">Choose year</option>{Array.from({ length: 12 }, (_, index) => <option value={index + 1} key={index + 1}>Year {index + 1}</option>)}</select></label>
            <label>Previous exam percentage<input type="number" min="0" max="100" step="0.01" value={form.previous_percentage} onChange={(event) => setField("previous_percentage", event.target.value)} placeholder="e.g. 82.5" /></label>
            <label>{t("District")}<select value={form.district || ""} onChange={(event) => setField("district", event.target.value)}><option value="">{t("Choose district")}</option>{form.district && !MAHARASHTRA_DISTRICTS.some((item) => item.name.toLowerCase() === form.district.toLowerCase()) && <option value={form.district}>{form.district}</option>}{MAHARASHTRA_DISTRICTS.map((item) => <option value={item.name} key={item.name}>{districtLabel(item.name, language)}</option>)}</select></label>
            <label>Preferred language<select value={form.preferred_language || "en"} onChange={(event) => setField("preferred_language", event.target.value)}>{LANGUAGES.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
            <label>College<input value={form.college || ""} onChange={(event) => setField("college", event.target.value)} placeholder="College name" maxLength="200" /></label>
            <label>University<input value={form.university || ""} onChange={(event) => setField("university", event.target.value)} placeholder="University name" maxLength="200" /></label>
            <BooleanSelect label="Maharashtra domicile" value={form.maharashtra_domicile} onChange={(value) => setField("maharashtra_domicile", value)} />
            <BooleanSelect label="Minority community" value={form.minority} onChange={(value) => setField("minority", value)} />
            <BooleanSelect label="Person with disability" value={form.divyang} onChange={(value) => setField("divyang", value)} />
          </div>
          <div className="privacy-callout"><ShieldCheck size={18} /><span><strong>Your privacy comes first.</strong> {t("Aadhaar is encrypted if provided at signup. PAN and bank details are not requested here.")}</span></div>
          </fieldset>
          <div className="form-actions"><span>{profileSaved && !editing ? t("Your profile is saved.") : t("Update your profile anytime.")}</span>{profileSaved && !editing ? <button className="button button-primary" type="button" onClick={() => setEditing(true)}>{t("Edit profile")}</button> : <>{profileSaved && <button className="button button-outline" type="button" onClick={() => { setForm(savedForm); setEditing(false); }} disabled={saving}>{t("Cancel changes")}</button>}<button className="button button-primary" type="submit" disabled={saving}>{saving ? <LoaderCircle size={16} className="spin" /> : <Check size={16} />}{saving ? "Saving…" : "Save profile"}</button></>}</div>
        </form>}
      </div>
      <aside className="profile-aside"><div className="profile-tip"><div className="profile-tip-icon"><Sparkles size={20} /></div><h3>Better details, better matches</h3><p>A few optional details can help you focus on schemes that align with your studies and eligibility.</p><div className="tip-rule" /><span><ShieldCheck size={16} /> Your profile is private to your account.</span></div><div className="profile-tip simple-tip"><div className="eyebrow">YOUR ACCOUNT</div><div className="account-detail"><span>Mobile</span><strong>{user.mobile}</strong></div><div className="account-detail"><span>Date of birth</span><strong>{formatDate(user.date_of_birth)}</strong></div></div></aside></div>
    </>
  );
}

function BooleanSelect({ label, value, onChange }) {
  return <label>{label}<select value={value} onChange={(event) => onChange(event.target.value)}><option value="">Prefer not to say</option><option value="true">Yes</option><option value="false">No</option></select></label>;
}

function Assistant({ language }) {
  const starters = ["Scholarships for undergraduate students", "What documents might I need?", "Show schemes for Maharashtra students"].map(t);
  const introduction = useMemo(() => ({
    role: "assistant",
    answer: t("Namaste! I can help you explore schemes from our verified scholarship directory. Ask me about eligibility, deadlines, study level or categories."),
    sources: [],
    disclaimer: t("Answers use administrator-reviewed scholarship records only. Confirm current details on the official scheme website."),
  }), [language]);
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState([introduction]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setMessages((current) => current.some((message) => message.role === "user") ? current : [introduction]);
  }, [introduction]);

  async function ask(value = question) {
    const text = value.trim();
    if (!text || loading) return;
    setMessages((current) => [...current, { role: "user", question: text }]);
    setQuestion("");
    setError("");
    setLoading(true);
    try {
      const result = await api(`/api/chat?q=${encodeURIComponent(text)}&lang=${language}`);
      setMessages((current) => [...current, { role: "assistant", ...result }]);
    } catch (requestError) {
      setError(requestError.message);
      setMessages((current) => [...current, { role: "assistant", answer: t("I couldn't reach the scholarship directory just now. Please try again in a moment."), sources: [] }]);
    } finally {
      setLoading(false);
    }
  }

  return <div className="assistant-page"><div className="assistant-main"><PageHeading eyebrow="TRUSTED, SOURCE-BASED GUIDANCE" title="Scholarship assistant" description="Ask a question and explore schemes from the admin-verified directory." /><div className="chat-panel"><div className="chat-header"><div className="assistant-avatar"><Sparkles size={19} /></div><div><strong>Scholarship guide</strong><span><i /> Verified directory assistant</span></div><span className="chat-language">{LANGUAGES.find((item) => item.value === language)?.label}</span></div><div className="chat-messages" aria-live="polite">{messages.map((message, index) => <div className={`chat-message ${message.role === "user" ? "chat-user" : ""}`} key={`${message.role}-${index}`}><div className={message.role === "user" ? "chat-user-avatar" : "assistant-avatar small-assistant"}>{message.role === "user" ? <UserRound size={15} /> : <Sparkles size={15} />}</div><div className="message-content">{message.role === "user" ? <p>{message.question}</p> : <AssistantAnswer message={message} />}</div></div>)}{loading && <div className="chat-message"><div className="assistant-avatar small-assistant"><Sparkles size={15} /></div><div className="typing-indicator"><i /><i /><i /></div></div>}</div><div className="suggested-prompts">{messages.length === 1 && starters.map((starter) => <button key={starter} onClick={() => ask(starter)}>{starter}<ArrowUpRight size={14} /></button>)}</div><form className="chat-composer" onSubmit={(event) => { event.preventDefault(); ask(); }}><input value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Ask about scholarships, eligibility or deadlines…" maxLength="500" aria-label="Ask the scholarship assistant" /><button className="button button-primary" type="submit" disabled={!question.trim() || loading} aria-label="Send question">{loading ? <LoaderCircle size={18} className="spin" /> : <Send size={17} />}</button></form>{error && <p className="chat-error">{error}</p>}</div></div><aside className="assistant-aside"><div className="assistant-info-card"><div className="assistant-info-icon"><ShieldCheck size={20} /></div><div className="eyebrow">BUILT FOR TRUST</div><h3>Verified information. Clear boundaries.</h3><p>This assistant only answers from schemes whose details have been verified by an administrator.</p><ul><li><CheckCircle2 size={15} /> No made-up scheme facts</li><li><CheckCircle2 size={15} /> Answers in English, Hindi & Marathi</li><li><CheckCircle2 size={15} /> Official links included where available</li></ul></div><div className="assistant-disclaimer"><CircleHelp size={16} /><span>Always confirm eligibility, deadlines and application steps on the official scheme website.</span></div></aside></div>;
}

function AssistantAnswer({ message }) {
  if (typeof message.answer === "string") return <><p>{message.answer}</p>{message.review_pending_count > 0 && <p className="assistant-review-notice"><ShieldCheck size={15} /><span><strong>{message.review_pending_count}</strong> {t("active scholarships are awaiting administrator review. Scheme details will appear here after review.")}</span></p>}{message.disclaimer && <p className="answer-disclaimer">{message.disclaimer}</p>}</>;
  return <>{message.answer?.map((scheme) => <div className="answer-scheme" key={scheme.id}><div className="eyebrow">{scheme.verified_at ? "VERIFIED SCHEME" : "DIRECTORY MATCH"}</div><h3>{scheme.title}</h3><p>{scheme.description}</p><div className="answer-eligibility"><strong>Eligibility overview</strong><span>{scheme.eligibility_summary}</span></div>{scheme.deadline && <span className="answer-deadline"><CalendarDays size={14} /> Deadline {formatDate(scheme.deadline)}</span>}</div>)}{message.sources?.length > 0 && <div className="answer-sources"><strong>Official sources</strong>{[...new Set(message.sources)].map((source) => <a href={source} target="_blank" rel="noreferrer" key={source}>{new URL(source).hostname}<ArrowUpRight size={13} /></a>)}</div>}{message.disclaimer && <p className="answer-disclaimer">{message.disclaimer}</p>}</>;
}

function DocumentChecker({ token }) {
  const [file, setFile] = useState(null);
  const [result, setResult] = useState(null);
  const [guide, setGuide] = useState(null);
  const [error, setError] = useState("");
  const [progress, setProgress] = useState(0);
  const [checking, setChecking] = useState(false);

  useEffect(() => {
    api("/api/applications/documents/upload-guide")
      .then(setGuide)
      .catch((requestError) => setError(requestError.message));
  }, []);

  function chooseFile(event) {
    setFile(event.target.files?.[0] || null);
    setResult(null);
    setError("");
    setProgress(0);
  }

  function checkFile() {
    setError("");
    setResult(null);
    if (!file) {
      setError("Choose a PDF, JPG or PNG file before running the check.");
      return;
    }
    const supported = ["application/pdf", "image/jpeg", "image/png"].includes(file.type)
      || /\.(pdf|jpe?g|png)$/i.test(file.name);
    if (!supported) {
      setError("This file type isn't supported. Choose a PDF, JPG or PNG scan.");
      return;
    }
    if (file.size > 8 * 1024 * 1024) {
      setError("This file is larger than 8 MB. Crop it or export a smaller scan and retry.");
      return;
    }
    if (file.size === 0) {
      setError("This file is empty. Choose another scan and retry.");
      return;
    }
    setChecking(true);
    setProgress(0);
    const request = new XMLHttpRequest();
    request.open("POST", "/api/applications/documents/check");
    request.setRequestHeader("Authorization", `Bearer ${token}`);
    request.upload.onprogress = (event) => {
      if (event.lengthComputable) setProgress(Math.round((event.loaded / event.total) * 100));
    };
    request.onload = () => {
      let data = {};
      try {
        data = JSON.parse(request.responseText);
      } catch {
        setError("The checker returned an unreadable response. Please retry.");
        setChecking(false);
        return;
      }
      if (request.status < 200 || request.status >= 300) {
        setError(data.error || "The document could not be checked. Please retry.");
      } else {
        setProgress(100);
        setResult(data);
      }
      setChecking(false);
    };
    request.onerror = () => {
      setError("Upload failed. Check your internet connection and retry. Your file is not stored.");
      setChecking(false);
    };
    request.onabort = () => {
      setError("Upload was cancelled. You can try again.");
      setChecking(false);
    };
    const formData = new FormData();
    formData.append("file", file);
    request.send(formData);
  }

  function downloadProcessedFile() {
    if (!result?.processed_file_base64) return;
    const binary = atob(result.processed_file_base64);
    const bytes = Uint8Array.from(binary, (character) => character.charCodeAt(0));
    const blob = new Blob([bytes], { type: result.file_type || file.type });
    const extension = result.file_type === "application/pdf" ? "pdf" : result.file_type === "image/png" ? "png" : "jpg";
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `${file.name.replace(/\.[^.]+$/, "")}-checked.${extension}`;
    link.click();
    URL.revokeObjectURL(link.href);
  }

  return <>
    <PageHeading eyebrow="CHECK BEFORE YOU UPLOAD" title="Document checker" description="Check file type, size and image clarity. Images are resized/compressed when needed; files are processed in memory and never stored." />
    <div className="document-layout"><section className="panel document-main"><div className="document-intro"><div className="document-intro-icon"><FileCheck2 size={21} /></div><div><h2>Make sure your scan is ready</h2><p>We check a temporary copy and return the processed file for you to download.</p></div></div><label className={`upload-dropzone ${file ? "upload-has-file" : ""}`} htmlFor="document-file"><input id="document-file" type="file" accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png" onChange={chooseFile} disabled={checking} /><div className="upload-icon"><Upload size={23} /></div>{file ? <><strong>{file.name}</strong><span>{(file.size / (1024 * 1024)).toFixed(2)} MB · Ready to check</span></> : <><strong>Choose a document to check</strong><span>PDF, JPG or PNG · Maximum 8 MB</span><em>Browse files</em></>}</label>{error && <ErrorMessage>{error}</ErrorMessage>}{checking && <div className="upload-progress"><div><span>Uploading and checking…</span><strong>{progress}%</strong></div><div className="progress-track"><span style={{ width: `${progress}%` }} /></div></div>}{result && <div className={`document-result ${result.valid ? "document-valid" : "document-invalid"}`}><div className="document-result-head"><div className="document-result-icon">{result.valid ? <CheckCircle2 size={20} /> : <CircleHelp size={20} />}</div><div><strong>{result.valid ? "Your document passed the checks" : "This scan may need attention"}</strong><span>{result.guidance}</span></div></div><div className="document-result-details"><span><strong>Type</strong>{result.file_type}</span><span><strong>File size</strong>{((result.processed_size_bytes || result.size_bytes || 0) / (1024 * 1024)).toFixed(2)} MB</span>{result.dimensions && <span><strong>Image size</strong>{result.dimensions.width} × {result.dimensions.height}</span>}<span><strong>Storage</strong>Not stored</span></div>{result.processed_file_base64 && <button className="button button-outline button-small" onClick={downloadProcessedFile}><FileCheck2 size={15} /> Download processed file</button>}</div>}<div className="document-actions"><span>Your document stays in memory during the check only.</span><button className="button button-primary" onClick={checkFile} disabled={!file || checking}>{checking ? <LoaderCircle size={16} className="spin" /> : <Upload size={16} />}{checking ? "Checking…" : result || error ? "Retry check" : "Check document"}</button></div></section><aside className="document-aside"><div className="privacy-card"><div className="privacy-card-icon"><ShieldCheck size={20} /></div><div className="eyebrow">PRIVATE BY DESIGN</div><h3>Never stored. Never shared.</h3><p>Your file is checked in memory and discarded immediately after the response. It is not uploaded to MahaDBT.</p><div className="privacy-seal"><CheckCircle2 size={16} /> Temporary processing only</div></div><div className="panel upload-guide-card"><div className="section-heading"><div><div className="eyebrow">QUICK CHECKLIST</div><h2>Before you upload</h2></div></div><ul><li><Check size={14} /> Use a clear, complete scan</li><li><Check size={14} /> Keep the file under 8 MB</li><li><Check size={14} /> Check document expiry dates</li><li><Check size={14} /> Follow the scheme checklist</li></ul></div></aside></div>
    <section className="panel common-errors-panel"><div className="section-heading"><div><div className="eyebrow">QUICK FIXES</div><h2>Common upload errors</h2></div><CircleHelp size={18} className="heading-icon" /></div>{guide?.errors ? <div className="upload-error-grid">{guide.errors.map((item) => <div className="upload-error-item" key={item.code}><strong>{t(item.code.replaceAll("_", " "))}</strong><p>{t(item.message)}</p></div>)}</div> : <Loading label="Loading upload guidance…" />}</section>
  </>;
}

function SurveyInsights() {
  const [surveys, setSurveys] = useState([]);
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const load = useCallback(() => {
    setLoading(true);
    setError("");
    api("/api/surveys/results")
      .then((data) => { setSurveys(data.results || []); setNote(data.note || ""); })
      .catch((requestError) => setError(requestError.message))
      .finally(() => setLoading(false));
  }, []);
  useEffect(() => { load(); }, [load]);
  return <>
    <PageHeading eyebrow="RESEARCH, MADE CLEAR" title="Survey insights" description="Explore published research results with their respondent counts and source links." action={<button className="button button-outline" onClick={load}><ArrowDownUp size={15} /> Refresh results</button>} />
    {note && <div className="verified-note survey-source-note"><ShieldCheck size={16} /> {note}</div>}
    {error && <ErrorMessage onRetry={load}>{error}</ErrorMessage>}
    {loading ? <Loading label="Loading published survey results…" /> : surveys.length ? <div className="survey-grid">{surveys.map((survey) => {
      const max = Math.max(1, ...survey.chart.values);
      return <article className="panel survey-card" key={survey.id}><div className="survey-card-head"><span className="survey-language">{LANGUAGES.find((item) => item.value === survey.language)?.label || survey.language}</span><span>{formatDate(survey.survey_date)}</span></div><h2>{survey.title}</h2><p className="survey-question">{survey.question}</p><div className="survey-respondents"><UserRound size={15} /> {survey.respondents} respondents</div><div className="survey-bars">{survey.chart.labels.map((label, index) => <div className="survey-bar-row" key={label}><div className="survey-bar-label"><span>{label}</span><strong>{survey.chart.values[index]}</strong></div><div className="survey-bar-track"><span style={{ width: `${Math.max(3, (survey.chart.values[index] / max) * 100)}%` }} /></div></div>)}</div><a className="survey-source-link" href={survey.source_url} target="_blank" rel="noreferrer">View research source <ArrowUpRight size={14} /></a></article>;
    })}</div> : <EmptyState icon={TrendingUp} title="No published research yet">Survey charts will appear here after sourced results are published by an administrator.</EmptyState>}
  </>;
}

function HelpCenter({ token, notify, language }) {
  const [activeTab, setActiveTab] = useState("guides");
  const [guide, setGuide] = useState("payment");
  const [guideData, setGuideData] = useState(null);
  const [tutorials, setTutorials] = useState([]);
  const [tutorialError, setTutorialError] = useState("");
  const [tickets, setTickets] = useState([]);
  const [grievances, setGrievances] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [subject, setSubject] = useState("");
  const [message, setMessage] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const loadRecords = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [ticketData, grievanceData] = await Promise.all([api("/api/tickets", {}, token), api("/api/grievances", {}, token)]);
      setTickets(ticketData.tickets || []);
      setGrievances(grievanceData.grievances || []);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }, [token]);
  useEffect(() => { if (activeTab === "tickets" || activeTab === "grievance") loadRecords(); }, [activeTab, loadRecords]);

  useEffect(() => {
    if (activeTab !== "guides") return;
    const endpoint = guide === "payment" ? "/api/guides/payment" : guide === "college" ? "/api/guides/college-verification" : "/api/guides/rejection";
    api(endpoint).then(setGuideData).catch((requestError) => setError(requestError.message));
  }, [activeTab, guide]);

  useEffect(() => {
    let active = true;
    setTutorialError("");
    api(`/api/tutorials?lang=${language}`)
      .then(({ tutorials: entries }) => { if (active) setTutorials(entries || []); })
      .catch((requestError) => { if (active) setTutorialError(requestError.message); });
    return () => { active = false; };
  }, [language]);

  async function submitRecord(event) {
    event.preventDefault();
    setSubmitting(true);
    const isGrievance = activeTab === "grievance";
    try {
      const response = await api(isGrievance ? "/api/grievances" : "/api/tickets", { method: "POST", body: JSON.stringify(isGrievance ? { subject, description: message } : { subject, message }) }, token);
      notify(`${isGrievance ? "Grievance" : "Support ticket"} submitted. Reference: ${isGrievance ? response.grievance.id : response.ticket.id}`);
      setSubject("");
      setMessage("");
      loadRecords();
    } catch (requestError) {
      notify(requestError.message);
    } finally {
      setSubmitting(false);
    }
  }

  return <>
    <PageHeading eyebrow="HERE WHEN YOU NEED US" title="Help & support" description="Find practical guidance or reach out to the support team." />
    <div className="help-tabs" role="tablist"><button className={activeTab === "guides" ? "tab-active" : ""} onClick={() => setActiveTab("guides")}>Guides</button><button className={activeTab === "tickets" ? "tab-active" : ""} onClick={() => setActiveTab("tickets")}>Help tickets</button><button className={activeTab === "grievance" ? "tab-active" : ""} onClick={() => setActiveTab("grievance")}>Grievance</button></div>
    {activeTab === "guides" && <><div className="help-layout"><section className="panel guide-panel"><div className="guide-selector"><button className={guide === "payment" ? "guide-selected" : ""} onClick={() => setGuide("payment")}><ArrowUpRight size={16} /> Payment & DBT</button><button className={guide === "college" ? "guide-selected" : ""} onClick={() => setGuide("college")}><GraduationCap size={16} /> College verification</button><button className={guide === "rejection" ? "guide-selected" : ""} onClick={() => setGuide("rejection")}><FileCheck2 size={16} /> Rejection guidance</button></div>{guideData ? <div className="guide-content"><div className="eyebrow">STEP-BY-STEP GUIDANCE</div>    <h2>{t(guide === "payment" ? "Understand your payment journey" : guide === "college" ? "What happens during college verification?" : "If your application was rejected")}</h2><div className="guide-timeline">{(guideData.stages || guideData.guidance || []).map((item, index) => <div className="guide-step" key={item.stage || item.reason}><div className="guide-step-index">{String(index + 1).padStart(2, "0")}</div><div><strong>{t((item.stage || item.reason || "").replaceAll("_", " "))}</strong><p>{t(item.guidance || item.next_step || item.fix || item.meaning)}</p></div></div>)}</div>{guideData.notice && <div className="privacy-callout"><CircleHelp size={17} /><span>{t(guideData.notice)}</span></div>}</div> : error ? <div className="guide-content"><ErrorMessage>{error}</ErrorMessage></div> : <Loading label="Loading guidance…" />}</section><aside className="help-callout"><div className="help-callout-icon"><HeartHandshake size={22} /></div><div className="eyebrow">NEED PERSONAL HELP?</div><h3>We’re here to help you move forward.</h3><p>Share your question with the support team and keep a reference to follow up.</p><button className="button button-dark button-full" onClick={() => setActiveTab("tickets")}>Create a support ticket <ArrowRight size={16} /></button></aside></div><section className="panel tutorials-panel"><div className="section-heading"><div><div className="eyebrow">WATCH & LEARN</div><h2>Video tutorials</h2></div><BookOpen size={18} className="heading-icon" /></div>{tutorialError ? <ErrorMessage>{tutorialError}</ErrorMessage> : tutorials.length ? <div className="tutorial-grid">{tutorials.map((tutorial) => <a className="tutorial-card" href={tutorial.video_url} target="_blank" rel="noreferrer" key={tutorial.id}><div className="tutorial-play"><ArrowUpRight size={17} /></div><div><strong>{tutorial.title}</strong><span>{tutorial.description}</span></div></a>)}</div> : <div className="small-empty">Tutorials will appear here when published by an administrator.</div>}</section></>}
    {(activeTab === "tickets" || activeTab === "grievance") && <div className="support-layout"><section className="panel support-form-panel"><div className="eyebrow">{activeTab === "grievance" ? "RAISE A CONCERN" : "WE'LL GET BACK TO YOU"}</div><h2>{activeTab === "grievance" ? "Submit a grievance" : "Create a help ticket"}</h2><p>{activeTab === "grievance" ? "Share an issue about your scholarship process. Never include bank details or OTPs." : "Describe what you need help with. Your private ticket will have a reference ID."}</p><form onSubmit={submitRecord}><label>Subject<input value={subject} onChange={(event) => setSubject(event.target.value)} maxLength="160" required placeholder={activeTab === "grievance" ? "What is your concern about?" : "What do you need help with?"} /></label><label>{activeTab === "grievance" ? "Description" : "Message"}<textarea value={message} onChange={(event) => setMessage(event.target.value)} rows="5" maxLength={activeTab === "grievance" ? 5000 : 4000} required placeholder="Add enough detail so we can assist…" /></label><button className="button button-primary" disabled={submitting}>{submitting ? <LoaderCircle size={16} className="spin" /> : <Send size={16} />}{submitting ? "Sending…" : "Submit securely"}</button></form></section><section className="panel support-records"><div className="section-heading"><div><div className="eyebrow">YOUR REQUESTS</div><h2>{activeTab === "grievance" ? "Grievance history" : "Ticket history"}</h2></div><button className="icon-button" onClick={loadRecords} aria-label="Refresh requests"><ArrowDownUp size={17} /></button></div>{error && <ErrorMessage onRetry={loadRecords}>{error}</ErrorMessage>}{loading ? <Loading label="Loading requests…" /> : (activeTab === "grievance" ? grievances : tickets).length ? <div className="support-record-list">{(activeTab === "grievance" ? grievances : tickets).map((record) => <div key={record.id} className="support-record"><div><strong>{record.subject}</strong><span>{record.id} · {formatDate(record.created_at?.slice(0, 10))}</span></div><span className="record-status">{record.status.replaceAll("_", " ")}</span></div>)}</div> : <div className="small-empty">Your submitted requests will show up here.</div>}</section></div>}
  </>;
}

function AuthScreen({ onAuthenticated, notify, toast, theme, onToggleTheme }) {
  const [mode, setMode] = useState("login");
  const [step, setStep] = useState("form");
  const [form, setForm] = useState({ full_name: "", email: "", mobile: "", aadhaar: "", aadhaar_consent: false, password: "", confirm_password: "", date_of_birth: "", gender: "prefer_not_to_say", consent: false });
  const [otp, setOtp] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const setField = (key, value) => setForm((current) => ({ ...current, [key]: value }));

  async function login() {
    const result = await api("/api/auth/login", { method: "POST", body: JSON.stringify({ identifier: form.email, password: form.password }) });
    onAuthenticated(result.access_token, result.user);
  }

  async function submit(event) {
    event.preventDefault();
    setError("");
    setLoading(true);
    try {
      if (mode === "login") {
        await login();
      } else if (mode === "forgot") {
        await api("/api/auth/forgot-password", { method: "POST", body: JSON.stringify({ email: form.email }) });
        setStep("reset");
      } else {
        await api("/api/auth/register", { method: "POST", body: JSON.stringify(form) });
        setField("aadhaar", "");
        setField("aadhaar_consent", false);
        setStep("verify");
      }
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }

  async function resetPassword(event) {
    event.preventDefault();
    setError("");
    setLoading(true);
    try {
      await api("/api/auth/reset-password", {
        method: "POST",
        body: JSON.stringify({
          email: form.email,
          otp,
          password: form.password,
          confirm_password: form.confirm_password,
        }),
      });
      setMode("login");
      setStep("form");
      setField("password", "");
      setField("confirm_password", "");
      setOtp("");
      notify(t("Password reset successful. Please sign in with your new password."));
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }

  async function verify(event) {
    event.preventDefault();
    setError("");
    setLoading(true);
    try {
      await api("/api/auth/verify-email", { method: "POST", body: JSON.stringify({ email: form.email, otp }) });
      await login();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }

  const isRegistration = mode === "register";
  const isLogin = mode === "login";
  const welcome = isLogin
    ? "Your next opportunity starts here."
    : isRegistration
      ? "Create your student account."
      : step === "reset"
        ? t("Choose a new password.")
        : t("Reset your password.");

  return <div className="auth-page">
    <button className="icon-button theme-toggle auth-theme-toggle" onClick={onToggleTheme} aria-label={t(theme === "dark" ? "Switch to light mode" : "Switch to dark mode")} title={t(theme === "dark" ? "Switch to light mode" : "Switch to dark mode")}>{theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}</button>
    <div className="auth-visual">
      <div className="auth-brand"><div className="brand-mark"><GraduationCap size={23} /></div><div className="brand-copy"><strong>Scholarship</strong><span>SUPPORT</span></div></div>
      <div className="auth-visual-content"><div className="auth-pill"><Sparkles size={14} /> YOUR FUTURE, IN FOCUS</div><h1>Make room for<br /><em>what’s next.</em></h1><p>Find scholarship opportunities, stay on top of applications and take your next step with confidence.</p><div className="auth-art"><Suspense fallback={<div className="auth-scene-fallback" />}><AuthScene /></Suspense><div className="auth-sticker sticker-one"><CheckCircle2 size={17} /> Verified schemes</div><div className="auth-sticker sticker-two"><BookOpen size={17} /> Your journey</div><span className="auth-sparkle spark-a">✦</span><span className="auth-sparkle spark-b">✧</span></div></div>
      <div className="auth-visual-foot"><ShieldCheck size={16} /> Guidance you can trust. Privacy you can count on.</div>
    </div>
    <main className="auth-main"><div className="auth-form-wrap">
      <div className="auth-mobile-brand"><div className="brand-mark"><GraduationCap size={21} /></div><div className="brand-copy"><strong>Scholarship</strong><span>SUPPORT</span></div></div>
      <div className="auth-form-heading">
        <div className="eyebrow">{step === "verify" || step === "reset" ? "ONE QUICK SECURITY CHECK" : "WELCOME TO YOUR SCHOLARSHIP SPACE"}</div>
        <h2>{step === "verify" ? "Check your email" : welcome}</h2>
        <p>{step === "verify" || step === "reset" ? `Enter the 6-digit code we sent to ${form.email}. It expires in 10 minutes.` : isLogin ? "Sign in to pick up where you left off." : isRegistration ? "A few details are all we need to get started." : t("Enter the email address linked to your account. We’ll send you a one-time reset code.")}</p>
      </div>
      {error && <div className="auth-error" role="alert"><CircleHelp size={17} />{error}</div>}
      {step === "verify" ? <form className="auth-form" onSubmit={verify}>
        <label>Verification code<input className="otp-input" inputMode="numeric" pattern="[0-9]{6}" maxLength="6" required value={otp} onChange={(event) => setOtp(event.target.value.replace(/\D/g, "").slice(0, 6))} placeholder="000000" autoComplete="one-time-code" /></label>
        <button className="button button-primary button-full auth-submit" disabled={loading || otp.length !== 6}>{loading ? <LoaderCircle size={17} className="spin" /> : <Check size={17} />}{loading ? "Verifying…" : "Verify email"}</button>
        <button className="auth-back" type="button" onClick={() => { setStep("form"); setError(""); }}>← Back to registration details</button>
      </form> : step === "reset" ? <form className="auth-form" onSubmit={resetPassword}>
        <label>Verification code<input className="otp-input" inputMode="numeric" pattern="[0-9]{6}" maxLength="6" required value={otp} onChange={(event) => setOtp(event.target.value.replace(/\D/g, "").slice(0, 6))} placeholder="000000" autoComplete="one-time-code" /></label>
        <label>{t("New password")}<input type="password" required minLength="10" maxLength="128" value={form.password} onChange={(event) => setField("password", event.target.value)} placeholder={t("At least 10 characters")} autoComplete="new-password" /></label>
        <label>Confirm password<input type="password" required minLength="10" maxLength="128" value={form.confirm_password} onChange={(event) => setField("confirm_password", event.target.value)} placeholder="Enter your password again" autoComplete="new-password" /></label>
        <button className="button button-primary button-full auth-submit" disabled={loading || otp.length !== 6}>{loading ? <LoaderCircle size={17} className="spin" /> : <Check size={17} />}{loading ? t("Updating password…") : t("Verify code and change password")}</button>
        <button className="auth-back" type="button" onClick={() => { setMode("login"); setStep("form"); setOtp(""); setError(""); }}>{t("← Back to sign in")}</button>
      </form> : <form className="auth-form" onSubmit={submit}>
        {isRegistration && <>
          <label>Full name<input required minLength="2" maxLength="120" value={form.full_name} onChange={(event) => setField("full_name", event.target.value)} placeholder="As shown on your marksheet" autoComplete="name" /></label>
          <div className="auth-form-row"><label>Mobile number<input required pattern="\+?[0-9]{10,15}" value={form.mobile} onChange={(event) => setField("mobile", event.target.value)} placeholder="10-digit number" autoComplete="tel" /></label><label>Date of birth<input type="date" required max={new Date().toISOString().slice(0, 10)} value={form.date_of_birth} onChange={(event) => setField("date_of_birth", event.target.value)} /></label></div>
          <label>Gender<select value={form.gender} onChange={(event) => setField("gender", event.target.value)}><option value="prefer_not_to_say">Prefer not to say</option><option value="female">Female</option><option value="male">Male</option><option value="other">Other</option></select></label>
          <div className="aadhaar-field"><label htmlFor="signup-aadhaar">Aadhaar number (optional)</label><input id="signup-aadhaar" inputMode="numeric" pattern="[0-9]{12}" maxLength="12" value={form.aadhaar} onChange={(event) => { setField("aadhaar", event.target.value.replace(/\D/g, "").slice(0, 12)); setField("aadhaar_consent", false); }} placeholder="12-digit number" autoComplete="off" /><small>Only if you choose: stored encrypted, never shown in your profile or sent by email.</small>{form.aadhaar && <label className="consent-label"><input type="checkbox" required checked={form.aadhaar_consent} onChange={(event) => setField("aadhaar_consent", event.target.checked)} /><span>I consent to encrypted storage of my Aadhaar number for this account.</span></label>}</div>
        </>}
        <label>{isLogin ? "Email, Student ID, or College ID" : "Email address"}<input type={isLogin ? "text" : "email"} required value={form.email} onChange={(event) => setField("email", event.target.value)} placeholder={isLogin ? "Email, SS-2026-000123, or CV-ABC123DEF456" : "you@example.com"} autoComplete={isLogin ? "username" : "email"} /></label>
        {mode !== "forgot" && <label>Password<input type="password" required minLength="10" maxLength="128" value={form.password} onChange={(event) => setField("password", event.target.value)} placeholder={isRegistration ? "At least 10 characters" : "Enter your password"} autoComplete={isRegistration ? "new-password" : "current-password"} /></label>}
        {isLogin && <button className="auth-forgot-link" type="button" onClick={() => { setMode("forgot"); setField("email", form.email.includes("@") ? form.email : ""); setField("password", ""); setError(""); }}>{t("Forgot password?")}</button>}
        {isRegistration && <>
          <label>Confirm password<input type="password" required minLength="10" maxLength="128" value={form.confirm_password} onChange={(event) => setField("confirm_password", event.target.value)} placeholder="Enter your password again" autoComplete="new-password" /></label>
          <label className="consent-label"><input type="checkbox" required checked={form.consent} onChange={(event) => setField("consent", event.target.checked)} /><span>I agree to the <a href="#privacy" onClick={(event) => { event.preventDefault(); notify("Aadhaar is optional. If provided, it is encrypted; PAN and bank details are not requested."); }}>privacy notice</a> and terms of use.</span></label>
        </>}
        <button className="button button-primary button-full auth-submit" disabled={loading}>{loading ? <LoaderCircle size={17} className="spin" /> : isLogin ? <ArrowRight size={17} /> : <Send size={16} />}{loading ? "Please wait…" : isLogin ? "Sign in securely" : isRegistration ? "Create account" : t("Send reset code")}</button>
      </form>}
      {step === "form" && <div className="auth-switch">{isLogin ? "New to Scholarship Support?" : isRegistration ? "Already have an account?" : t("Remembered your password?")}<button onClick={() => { setMode(isLogin ? "register" : "login"); setStep("form"); setOtp(""); setError(""); }}> {isLogin ? "Create an account" : "Sign in"}</button></div>}
      <div className="auth-security"><ShieldCheck size={15} /> Your password is securely hashed and never sent by email.</div>
      <div className="auth-privacy-note">This is a scholarship guidance and tracker service, not the official MahaDBT application portal.</div>
    </div></main>{toast && <div className="toast"><CheckCircle2 size={18} />{toast}</div>}
  </div>;
}

export default App;
