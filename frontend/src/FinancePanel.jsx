import { useCallback, useEffect, useState } from "react";
import { Banknote, CheckCircle2, Eye, EyeOff, RefreshCw, ShieldCheck } from "lucide-react";
import { t } from "./i18n.js";

async function financeApi(path, token, options = {}) {
  const headers = new Headers(options.headers || {});
  if (options.body) headers.set("Content-Type", "application/json");
  headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(path, { ...options, headers });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || "The finance request failed.");
  return data;
}

function FinancePanel({ token, notify }) {
  const [items, setItems] = useState([]);
  const [blockedCount, setBlockedCount] = useState(0);
  const [revealed, setRevealed] = useState({});
  const [loading, setLoading] = useState(true);
  const [processingId, setProcessingId] = useState("");
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const result = await financeApi("/api/applications/finance", token);
      setItems(result.items || []);
      setBlockedCount(result.blocked_count || 0);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => { refresh(); }, [refresh]);

  async function simulateDisbursement(item) {
    const confirmed = window.confirm(
      `${t("Simulate disbursement")} ₹${item.payout_amount} ${t("for this application? No money will be transferred.")}`,
    );
    if (!confirmed) return;
    setProcessingId(item.id);
    try {
      const result = await financeApi(
        `/api/applications/finance/${item.id}/simulate-disbursement`,
        token,
        { method: "POST" },
      );
      notify(result.email_status === "sent"
        ? t("Demo payment recorded; student email sent.")
        : t("Demo payment recorded; student email queued for retry."));
      await refresh();
    } catch (requestError) {
      notify(requestError.message);
    } finally {
      setProcessingId("");
    }
  }

  return <>
    <div className="finance-heading">
      <div>
        <div className="eyebrow">{t("FINANCE WORKSPACE · SIMULATION ONLY")}</div>
        <h1>{t("Approved scholarship payments")}</h1>
        <p>{t("Only approved applications and the minimum bank details for this demo are shown. Student profile and documents are not available here.")}</p>
      </div>
      <button className="button button-outline" onClick={refresh} disabled={loading}>
        <RefreshCw size={15} className={loading ? "spin" : ""} /> {t("Refresh queue")}
      </button>
    </div>
    <div className="finance-simulation-banner">
      <ShieldCheck size={19} />
      <div>
        <strong>{t("Demo payment flow — no real transfer")}</strong>
        <p>{t("This screen records a simulated disbursement only. It does not connect to a bank, send money, or verify a bank credit.")}</p>
      </div>
    </div>
    {blockedCount > 0 && <div className="finance-blocked-note">{t("Some approved applications are missing encrypted bank details or a fixed payout amount and cannot enter this queue.")} ({blockedCount})</div>}
    {error && <div className="admin-error" role="alert"><span>{error}</span><button onClick={refresh}>{t("Retry")}</button></div>}
    {loading ? <div className="admin-loading">{t("Loading finance queue…")}</div>
      : items.length ? <div className="finance-queue">{items.map((item) => {
        const accountRevealed = Boolean(revealed[item.id]);
        const displayAccount = accountRevealed
          ? item.bank_account_number
          : `•••• •••• ${item.bank_account_number.slice(-4)}`;
        return <article className="finance-payment-card" key={item.id}>
          <div className="finance-payment-head">
            <div className="finance-icon"><Banknote size={19} /></div>
            <div><div className="eyebrow">{t("APPROVED APPLICATION")} · {item.id.slice(0, 8)}</div><h2>{item.scholarship_title}</h2></div>
            <span className="admin-chip chip-active">{t("Ready for demo")}</span>
          </div>
          <div className="finance-amount-card">
            <span>{t("Fixed scholarship amount")}</span>
            <strong>₹{item.payout_amount}</strong>
            <small>{t("Automatically set from the scholarship record")}</small>
          </div>
          <div className="finance-bank-details">
            <div><span>{t("Bank account number")}</span><strong>{displayAccount}</strong></div>
            <button className="button button-outline button-small" onClick={() => setRevealed((state) => ({ ...state, [item.id]: !accountRevealed }))} aria-label={t(accountRevealed ? "Hide account number" : "Reveal account number")}>
              {accountRevealed ? <EyeOff size={14} /> : <Eye size={14} />}{t(accountRevealed ? "Hide" : "Reveal")}
            </button>
            <div><span>{t("IFSC code")}</span><strong>{item.ifsc}</strong></div>
          </div>
          <div className="finance-receipt-note">{t("Demo receipt: this records the configured amount and sends a clearly labeled simulation email to the student.")}</div>
          <button className="button button-primary finance-pay-button" disabled={processingId === item.id} onClick={() => simulateDisbursement(item)}>
            <CheckCircle2 size={16} />{processingId === item.id ? t("Recording demo payment…") : t("Simulate disbursement")}
          </button>
        </article>;
      })}</div> : <div className="finance-empty"><Banknote size={25} /><strong>{t("No approved applications in the finance queue.")}</strong><span>{t("Once the first administrator approves an application with a fixed amount, it will appear here.")}</span></div>}
  </>;
}

export default FinancePanel;
