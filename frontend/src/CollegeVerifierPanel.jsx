import { useCallback, useEffect, useState } from "react";
import { CheckCircle2, CircleHelp, FileText, RefreshCw, X } from "lucide-react";
import { t } from "./i18n.js";

async function collegeApi(path, token, options = {}) {
  const headers = new Headers(options.headers || {});
  if (options.body) headers.set("Content-Type", "application/json");
  headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(path, { ...options, headers });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || t("The college request failed."));
  return data;
}

export default function CollegeVerifierPanel({ token, user, notify }) {
  const [college, setCollege] = useState(null);
  const [applications, setApplications] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await collegeApi("/api/colleges/applications", token);
      setCollege(data.college);
      setApplications(data.applications || []);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => { refresh(); }, [refresh]);

  async function review(application, status) {
    const note = status === "college_verified"
      ? ""
      : window.prompt(t(status === "rejected" ? "Enter the reason for rejecting this application:" : "Describe what the student should correct:"))?.trim();
    if (status !== "college_verified" && !note) return;
    try {
      const result = await collegeApi(`/api/colleges/applications/${application.id}/review`, token, {
        method: "POST",
        body: JSON.stringify({ status, note }),
      });
      const statusMessage = t(status === "college_verified"
        ? "Application verified and sent for department review."
        : status === "rejected"
          ? "Application rejected with a reason."
          : "Correction request sent to the student.");
      const emailMessage = result.email_status === "sent"
        ? t("Email sent to student.")
        : result.email_status === "failed"
          ? t("Email could not be sent; it is queued for retry.")
          : "";
      notify([statusMessage, emailMessage].filter(Boolean).join(" "));
      refresh();
    } catch (requestError) {
      notify(requestError.message);
    }
  }

  async function downloadDocument(application, document) {
    try {
      const response = await fetch(`/api/colleges/applications/${application.id}/documents/${document.id}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.error || t("Could not load this document."));
      }
      const url = URL.createObjectURL(await response.blob());
      const link = window.document.createElement("a");
      link.href = url;
      link.download = document.filename;
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (requestError) {
      notify(requestError.message);
    }
  }

  return (
    <>
      <div className="admin-heading">
        <div>
          <div className="eyebrow">{t("COLLEGE VERIFICATION")}</div>
          <h1>{college?.name || user.college_name || t("College applications")}</h1>
          <p>{t("Review student details and documents before forwarding eligible applications to the department.")}</p>
        </div>
        <button className="button button-outline" onClick={refresh} disabled={loading}>
          <RefreshCw size={15} className={loading ? "spin" : ""} /> {t("Refresh queue")}
        </button>
      </div>
      <div className="college-demo-notice">
        <CircleHelp size={17} />
        <span>{t("This is an internal project verification workflow, not an official MahaDBT submission.")}</span>
      </div>
      {error && <div className="admin-error"><CircleHelp size={17} /><span>{error}</span><button onClick={refresh}>{t("Retry")}</button></div>}
      {loading ? <div className="admin-loading"><RefreshCw size={18} className="spin" /> {t("Loading applications…")}</div> : applications.length ? (
        <div className="application-review-list">
          <div className="admin-application-status-summary">
            <span>{t("Applications waiting for college review")} <strong>{applications.length}</strong></span>
            <span>{t("Verifier account")} <strong>{user.user_id}</strong></span>
          </div>
          {applications.map((application) => (
            <article className="panel application-review-card" key={application.id}>
              <header>
                <div>
                  <div className="eyebrow">{t("Application")} · {application.id.slice(0, 8)}</div>
                  <h2>{application.scholarship_title}</h2>
                  <p>{application.student?.full_name} · {application.student?.email} · {application.student?.mobile}</p>
                </div>
                <span className="admin-chip chip-inactive">{t(application.status.replaceAll("_", " "))}</span>
              </header>
              <div className="application-review-details">
                {Object.entries(application.application_form || {}).filter(([, value]) => value).map(([field, value]) => (
                  <div key={field}><span>{t(field.replaceAll("_", " "))}</span><strong>{value}</strong></div>
                ))}
              </div>
              {application.college_note && <div className="application-admin-note"><strong>{t("Previous college note")}</strong><p>{application.college_note}</p></div>}
              <div className="application-review-documents">
                <strong>{t("Submitted documents")}</strong>
                {application.documents?.length ? application.documents.map((document) => (
                  <div key={document.id}>
                    <span><FileText size={15} />{document.name}{document.required && <em>{t("Required")}</em>}</span>
                    <button className="button button-outline button-small" onClick={() => downloadDocument(application, document)}>{t("Download document")}</button>
                  </div>
                )) : <p>{t("No documents were attached.")}</p>}
              </div>
              <footer>
                <button className="button button-primary button-small" onClick={() => review(application, "college_verified")}><CheckCircle2 size={15} />{t("Verify and forward")}</button>
                <button className="button button-outline button-small" onClick={() => review(application, "correction_required")}><RefreshCw size={14} />{t("Request correction")}</button>
                <button className="button button-outline button-small review-reject" onClick={() => review(application, "rejected")}><X size={15} />{t("Reject application")}</button>
              </footer>
            </article>
          ))}
        </div>
      ) : !error && <div className="panel college-empty-state"><CheckCircle2 size={25} /><h2>{t("No applications waiting for verification")}</h2><p>{t("New student submissions for your registered college will appear here.")}</p></div>}
    </>
  );
}
