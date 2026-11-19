import assert from "node:assert/strict";
import fs from "node:fs";
import { createRequire } from "node:module";
import { afterEach, test } from "node:test";
import { getLocale, setLocale, t } from "../src/i18n.js";
import { MAHARASHTRA_DISTRICTS, normalizeDistrictNames } from "../src/districts.js";

const require = createRequire(import.meta.url);
const parser = require("@babel/parser");
const untranslatedTechnicalTerms = /\b(?:PDF|JPG|PNG|MB|DBT|MahaDBT|SMTP|SMS|WhatsApp|URL|JSON|OBC|SC|ST|open|ADMIN_EMAILS|en|hi|mr)\b|you@example\.com|https:\/\/[^\s]+/gi;

afterEach(() => setLocale("en"));

test("Hindi and Marathi translate interface phrases and admin labels", () => {
  setLocale("hi");
  assert.equal(t("My applications"), "मेरे आवेदन");
  assert.equal(t("Admin dashboard"), "प्रशासक डैशबोर्ड");

  setLocale("mr");
  assert.equal(t("My applications"), "माझे अर्ज");
  assert.equal(t("Admin dashboard"), "प्रशासक डॅशबोर्ड");
});

test("untranslated dynamic content is preserved instead of word-translated", () => {
  const message = "A new server response that has no reviewed translation.";
  setLocale("hi");
  assert.equal(t(message), message);
});

test("locale state falls back safely for unsupported language values", () => {
  setLocale("fr");
  assert.equal(getLocale(), "en");
  assert.equal(t("Scholarship assistant"), "Scholarship assistant");
});

test("static student and admin interface strings have Hindi and Marathi translations", () => {
  const interfaceStrings = new Set();
  for (const file of ["../src/App.jsx", "../src/AdminPanel.jsx"]) {
    const source = fs.readFileSync(new URL(file, import.meta.url), "utf8");
    const ast = parser.parse(source, { sourceType: "module", plugins: ["jsx"] });
    const visit = (node) => {
      if (!node || typeof node !== "object") return;
      if (node.type === "JSXText" && node.value.trim()) {
        interfaceStrings.add(node.value.trim().replace(/\s+/g, " "));
      }
      if (
        node.type === "JSXAttribute"
        && ["aria-label", "alt", "placeholder", "title"].includes(node.name?.name)
        && node.value?.type === "StringLiteral"
      ) {
        interfaceStrings.add(node.value.value);
      }
      for (const [key, value] of Object.entries(node)) {
        if (["loc", "start", "end"].includes(key)) continue;
        if (Array.isArray(value)) value.forEach(visit);
        else if (value && typeof value === "object") visit(value);
      }
    };
    visit(ast);
  }

  for (const locale of ["hi", "mr"]) {
    setLocale(locale);
    for (const source of interfaceStrings) {
      const visibleText = t(source).replace(untranslatedTechnicalTerms, "");
      assert.doesNotMatch(visibleText, /[A-Za-z]{3}/, `${locale} translation missing: ${source}`);
    }
  }
});

test("dynamic guidance and assistant messages are localized in Hindi and Marathi", () => {
  const dynamicMessages = [
    "Namaste! I can help you explore schemes from our verified scholarship directory. Ask me about eligibility, deadlines, study level or categories.",
    "Answers use administrator-reviewed scholarship records only. Confirm current details on the official scheme website.",
    "Confirm submission status and save the official application ID.",
    "The college is checking enrollment, course, documents, and scheme criteria.",
    "Use the official portal or college scholarship desk to clarify the notice. Reapply only if official rules allow it.",
    "Your application was sent to the administrator for eligibility and document review.",
    "Your application was sent to your college for verification.",
    "Approved applications are awaiting fund distribution. An administrator updates this tracker after the funds are disbursed; this portal does not transfer money.",
    "Track your application through college verification and department review. After approval, fund distribution remains pending until the administrator records it.",
    "Enter actual amount distributed in INR (up to 2 decimal places):",
    "Email sent to student.",
    "Email could not be sent; it is queued for retry.",
    "Switch to dark mode",
    "Switch to light mode",
    "Finance simulation",
    "Bank details for demo scholarship payment",
    "Enter the account that would receive the scholarship. These details are encrypted and visible only to the separate finance role after approval.",
    "I consent to encrypting my bank account and IFSC for this application. The separate finance role can access only these payout details and the fixed scheme amount. This demo does not transfer money.",
    "FINANCE WORKSPACE · SIMULATION ONLY",
    "Approved scholarship payments",
    "Demo payment flow — no real transfer",
    "This screen records a simulated disbursement only. It does not connect to a bank, send money, or verify a bank credit.",
    "Simulate disbursement",
    "Demo payment recorded; student email sent.",
    "Demo payment recorded; student email queued for retry.",
    "Demo payment recorded:",
    "No money was transferred.",
    "Fixed demo payout amount (₹)",
    "Exact amount loaded in the simulated finance flow. Not a real transfer.",
    "Internet connection check karke retry karein. This checker does not retain uploaded files.",
    "needs more information",
    "Cancel changes",
    "Your profile is saved.",
    "active scholarships are awaiting administrator review. Scheme details will appear here after review.",
  ];

  for (const locale of ["hi", "mr"]) {
    setLocale(locale);
    for (const message of dynamicMessages) {
      assert.notEqual(t(message), message, `${locale} translation missing: ${message}`);
    }
  }
});

test("assistant chat messages keep readable dark-theme contrast", () => {
  const styles = fs.readFileSync(new URL("../src/styles.css", import.meta.url), "utf8");
  assert.match(styles, /html\[data-theme="dark"\] \.app-shell \.chat-messages\s*\{\s*background-color: #111a2b;/);
  assert.match(styles, /html\[data-theme="dark"\] \.app-shell \.chat-panel \.message-content\s*\{[^}]*color: #d6deeb;[^}]*background-color: #1b2537;/);
  assert.match(styles, /html\[data-theme="dark"\] \.app-shell \.chat-panel \.message-content \.answer-scheme h3\s*\{\s*color: #f1f5fb;/);
});

test("saved profiles stay read-only until the user chooses Edit profile", () => {
  const source = fs.readFileSync(new URL("../src/App.jsx", import.meta.url), "utf8");
  assert.match(source, /<fieldset className="profile-fields" disabled=\{!editing \|\| saving\}>/);
  assert.match(source, /profileSaved && !editing \? <button className="button button-primary" type="button" onClick=\{\(\) => setEditing\(true\)\}>/);
  assert.match(source, /setProfileSaved\(true\);\s*setEditing\(false\);/);
});

test("phrase translation dictionaries do not contain duplicate keys", () => {
  const source = fs.readFileSync(new URL("../src/i18n.js", import.meta.url), "utf8");
  const ast = parser.parse(source, { sourceType: "module" });
  let dictionaries;
  const visit = (node) => {
    if (!node || typeof node !== "object") return;
    if (node.type === "VariableDeclarator" && node.id.name === "phraseTranslations") {
      dictionaries = node.init;
      return;
    }
    for (const value of Object.values(node)) {
      if (Array.isArray(value)) value.forEach(visit);
      else if (value && typeof value === "object") visit(value);
    }
  };
  visit(ast);
  assert.ok(dictionaries);
  for (const locale of dictionaries.properties) {
    const keys = new Set();
    const localeName = locale.key.name || locale.key.value;
    for (const property of locale.value.properties) {
      const key = property.key.value;
      assert.ok(!keys.has(key), `duplicate ${localeName} translation: ${key}`);
      keys.add(key);
    }
  }
});

test("district options include the 36 unique districts in English alphabetical order", () => {
  const names = MAHARASHTRA_DISTRICTS.map((district) => district.name);
  assert.equal(names.length, 36);
  assert.equal(new Set(names.map((name) => name.toLowerCase())).size, names.length);
  assert.deepEqual(names, [...names].sort((first, second) => first.localeCompare(second)));
  assert.equal(normalizeDistrictNames([" akola ", "PUNE"])[0], "Akola");
});

test("admin scholarship form uses selection controls and explains eligibility summary", () => {
  const source = fs.readFileSync(new URL("../src/AdminPanel.jsx", import.meta.url), "utf8");
  assert.match(source, /Categories \(directory tags\)[\s\S]*?multiple size="5"/);
  assert.match(source, /Eligible categories[\s\S]*?multiple size="5"/);
  assert.match(source, /Eligible courses[\s\S]*?multiple size="7"/);
  assert.match(source, /A short, student-friendly summary of the main eligibility rules/);
});

test("admin approval automatically retries after saving the missing fixed payout", () => {
  const source = fs.readFileSync(new URL("../src/AdminPanel.jsx", import.meta.url), "utf8");
  assert.match(source, /if \(status === "approved"\) \{\s*const scholarship = scholarships\.find/);
  assert.match(source, /if \(scholarship && !scholarship\.payout_amount\) \{\s*editScholarshipForApproval/);
  assert.match(source, /setPendingApproval\(\{ application, admin_note \}\)/);
  assert.match(source, /if \(approvalToRetry\) \{\s*await submitApplicationReview\(/);
  assert.match(source, /approvalToRetry\.application,\s*"approved",\s*approvalToRetry\.admin_note/);
});

test("login accepts an email address or student ID", () => {
  const source = fs.readFileSync(new URL("../src/App.jsx", import.meta.url), "utf8");
  assert.match(source, /isLogin \? "Email, Student ID, or College ID" : "Email address"/);
  assert.match(source, /type=\{isLogin \? "text" : "email"\}/);
  assert.match(source, /SS-2026-000123/);
  assert.match(source, /Forgot password\?/);
  assert.match(source, /api\("\/api\/auth\/forgot-password"/);
  assert.match(source, /api\("\/api\/auth\/reset-password"/);
});

test("password reset controls have Hindi and Marathi translations", () => {
  setLocale("hi");
  assert.equal(t("Forgot password?"), "पासवर्ड भूल गए?");
  setLocale("mr");
  assert.equal(t("Forgot password?"), "पासवर्ड विसरलात?");
});

test("signup makes Aadhaar optional and requires separate consent before submitting", () => {
  const source = fs.readFileSync(new URL("../src/App.jsx", import.meta.url), "utf8");
  assert.match(source, /Aadhaar number \(optional\)/);
  assert.match(source, /form\.aadhaar && <label className="consent-label">/);
  assert.match(source, /I consent to encrypted storage of my Aadhaar number for this account/);
  assert.match(source, /setField\("aadhaar", ""\)/);
});

test("scholarship applications are submitted to internal review, not redirected externally", () => {
  const source = fs.readFileSync(new URL("../src/App.jsx", import.meta.url), "utf8");
  assert.match(source, /t\("Apply for this scholarship"\)/);
  assert.match(source, /function ApplicationFormModal/);
  assert.match(source, /document_consent: documentConsent/);
  assert.match(source, /status: "submitted"/);
  assert.doesNotMatch(source, /https:\/\/mahadbt\.maharashtra\.gov\.in\//);
  assert.match(source, /function ApplicationTrackerCard/);
  assert.doesNotMatch(source, /label="Document checker"/);
  assert.match(source, /const isExpired = scholarship\.deadline/);
  assert.match(source, /You can still submit your application; an administrator must configure the amount before approval/);
});

test("application form converts saved numeric study years to text", () => {
  const source = fs.readFileSync(new URL("../src/App.jsx", import.meta.url), "utf8");
  assert.match(source, /String\(existingApplication\.application_form\.year_of_study\)/);
  assert.match(source, /profile\.year_of_study == null \? "" : String\(profile\.year_of_study\)/);
});

test("retries resume an existing draft and preserve already saved bank details", () => {
  const source = fs.readFileSync(new URL("../src/App.jsx", import.meta.url), "utf8");
  assert.match(source, /api\("\/api\/applications\/dashboard", \{\}, token\)/);
  assert.match(source, /application\.scholarship_id === id/);
  assert.match(source, /const \{ application, resumed \} = await api\("\/api\/applications"/);
  assert.match(source, /if \(resumed\) await saveDraftDetails\(id, savedBankDetails\)/);
  assert.match(source, /if \(!isCorrection && \(!bankDetailsAreSaved \|\| hasEnteredBankDetails\)\)/);
  assert.match(source, /required=\{!bankDetailsSaved\}/);
  assert.doesNotMatch(source, /api\("\/api\/admin\/analytics"/);
  assert.doesNotMatch(source, /api\("\/api\/applications\/finance"/);
});

test("admin application review handlers are available to the review tab", () => {
  const source = fs.readFileSync(new URL("../src/AdminPanel.jsx", import.meta.url), "utf8");
  const ast = parser.parse(source, { sourceType: "module", plugins: ["jsx"] });
  const adminPanel = ast.program.body.find((node) =>
    node.type === "FunctionDeclaration" && node.id.name === "AdminPanel"
  );
  const topLevelFunctions = adminPanel.body.body
    .filter((node) => node.type === "FunctionDeclaration")
    .map((node) => node.id.name);

  assert.ok(topLevelFunctions.includes("reviewApplication"));
  assert.ok(topLevelFunctions.includes("previewApplicationDocument"));
  assert.match(source, /error\.code = data\.code/);
  assert.match(source, /scholarshipToForm\(scholarship\)/);
  assert.match(source, /missing_fixed_payout_amount/);
});
