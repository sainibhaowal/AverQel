"use client";

import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { motion } from "framer-motion";
import {
  ArrowRight,
  CheckCircle2,
  LockKeyhole,
  LoaderCircle,
  Mail,
  MessageSquareText,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import Link from "next/link";
import styles from "./ContactSection.module.css";
import { useLandingReducedMotion } from "./landingMotion";

type ContactFields = {
  name: string;
  email: string;
  subject: string;
  message: string;
  website: string;
};

type ContactFieldName = "name" | "email" | "subject" | "message";
type ContactFieldErrors = Partial<Record<ContactFieldName, string>>;

const EMPTY_FIELDS: ContactFields = {
  name: "",
  email: "",
  subject: "",
  message: "",
  website: "",
};

const SUBJECT_STARTERS = ["Product question", "Report an issue", "Share an idea"];
const MESSAGE_LIMIT = 8_000;

export default function ContactSection() {
  const id = useId();
  const reduceMotion = useLandingReducedMotion();
  const fieldToFocus = useRef<ContactFieldName | null>(null);
  const [available, setAvailable] = useState<boolean | null>(null);
  const [fields, setFields] = useState<ContactFields>(EMPTY_FIELDS);
  const [fieldErrors, setFieldErrors] = useState<ContactFieldErrors>({});
  const [sending, setSending] = useState(false);
  const [requestingCode, setRequestingCode] = useState(false);
  const [checkingCode, setCheckingCode] = useState(false);
  const [challengeId, setChallengeId] = useState("");
  const [verificationCode, setVerificationCode] = useState("");
  const [verificationToken, setVerificationToken] = useState("");
  const [feedback, setFeedback] = useState("");
  const [sent, setSent] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/v1/contact/status", {
      cache: "no-store",
      credentials: "omit",
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) throw new Error("Contact status could not be loaded.");
        const result = (await response.json()) as { available?: unknown };
        setAvailable(result.available === true);
      })
      .catch(() => {
        if (!controller.signal.aborted) setAvailable(false);
      });

    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!fieldToFocus.current) return;
    document.getElementById(id + "-" + fieldToFocus.current)?.focus();
    fieldToFocus.current = null;
  }, [fieldErrors, id]);

  const completedFields = [
    fields.name.trim(),
    fields.email.trim(),
    fields.subject.trim(),
    fields.message.trim(),
  ].filter(Boolean).length;
  const completionPercent = (completedFields / 4) * 100;
  const statusText =
    available === null
      ? "Checking delivery settings"
      : available
        ? "Delivery settings configured"
        : "Temporarily unavailable";

  function updateField(field: keyof ContactFields, value: string) {
    setFields((current) => ({ ...current, [field]: value }));
    if (field === "email") {
      setChallengeId("");
      setVerificationCode("");
      setVerificationToken("");
    }
    if (field !== "website") {
      setFieldErrors((current) => {
        if (!current[field]) return current;
        const next = { ...current };
        delete next[field];
        return next;
      });
    }
    setFeedback("");
    setSent(false);
  }

  async function requestVerificationCode() {
    if (available !== true || requestingCode || checkingCode || sending) return;
    const emailInput = document.getElementById(id + "-email") as HTMLInputElement | null;
    if (!fields.email.trim() || emailInput?.validity.typeMismatch) {
      setFieldErrors((current) => ({
        ...current,
        email: "Enter a valid email address, such as you@example.com.",
      }));
      emailInput?.focus();
      return;
    }

    setRequestingCode(true);
    setFeedback("");
    try {
      const response = await fetch("/api/v1/contact/verification/request", {
        method: "POST",
        credentials: "omit",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: fields.email.trim() }),
      });
      if (response.status === 429) {
        setFeedback("Too many code requests. Please wait before trying again.");
        return;
      }
      if (!response.ok) throw new Error("A verification code could not be sent.");
      const result = (await response.json()) as { challenge_id?: unknown };
      if (typeof result.challenge_id !== "string") {
        throw new Error("A verification code could not be sent.");
      }
      setChallengeId(result.challenge_id);
      setVerificationToken("");
      setVerificationCode("");
      setFeedback("A code was sent. Check your inbox and spam folder.");
    } catch {
      setFeedback("We could not send a verification code right now. Please try again later.");
    } finally {
      setRequestingCode(false);
    }
  }

  async function confirmVerificationCode() {
    if (!challengeId || checkingCode || sending) return;
    if (!/^[0-9]{6}$/.test(verificationCode)) {
      setFeedback("Enter the six-digit code from the email.");
      return;
    }

    setCheckingCode(true);
    setFeedback("");
    try {
      const response = await fetch("/api/v1/contact/verification/confirm", {
        method: "POST",
        credentials: "omit",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: fields.email.trim(),
          challenge_id: challengeId,
          code: verificationCode,
        }),
      });
      if (response.status === 429) {
        setFeedback("Too many verification attempts. Please wait before trying again.");
        return;
      }
      if (!response.ok) throw new Error("That code is invalid or expired.");
      const result = (await response.json()) as {
        verified?: unknown;
        verification_token?: unknown;
      };
      if (result.verified !== true || typeof result.verification_token !== "string") {
        throw new Error("That code is invalid or expired.");
      }
      setVerificationToken(result.verification_token);
      setFeedback("");
    } catch {
      setFeedback("That code is invalid or expired. Request a new code and try again.");
    } finally {
      setCheckingCode(false);
    }
  }

  function changeEmailAddress() {
    setChallengeId("");
    setVerificationCode("");
    setVerificationToken("");
    setFeedback("");
    setFieldErrors((current) => {
      const next = { ...current };
      delete next.email;
      return next;
    });
    document.getElementById(id + "-email")?.focus();
  }

  async function submitContact(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (available !== true || sending || !verificationToken) return;

    const errors: ContactFieldErrors = {};
    if (!fields.name.trim()) errors.name = "Enter your name so I know how to address you.";
    if (!fields.subject.trim()) errors.subject = "Add a short subject for your message.";
    if (!fields.message.trim()) errors.message = "Write a message before sending.";

    if (Object.keys(errors).length > 0) {
      const firstInvalid = (Object.keys(errors) as ContactFieldName[])[0];
      fieldToFocus.current = firstInvalid;
      setFieldErrors(errors);
      return;
    }

    setFieldErrors({});

    setSending(true);
    setSent(false);
    setFeedback("");
    try {
      const response = await fetch("/api/v1/contact", {
        method: "POST",
        credentials: "omit",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...fields, verification_token: verificationToken }),
      });
      if (response.status === 429) {
        setFeedback("Please wait a little before sending another message.");
        return;
      }
      if (!response.ok) {
        setVerificationToken("");
        setChallengeId("");
        setVerificationCode("");
        throw new Error("Message could not be sent. Verify your email again before retrying.");
      }

      setSent(true);
      setFields(EMPTY_FIELDS);
      setVerificationToken("");
      setChallengeId("");
      setVerificationCode("");
      setFeedback("Your message was accepted by the email service. Thank you for reaching out.");
    } catch {
      setFeedback("We could not send your message. Verify your email again before retrying.");
    } finally {
      setSending(false);
    }
  }

  return (
    <motion.section
      id="contact"
      aria-labelledby={id + "-title"}
      className={styles.contactSection}
      initial={reduceMotion ? false : { opacity: 0, y: 24 }}
      whileInView={reduceMotion ? undefined : { opacity: 1, y: 0 }}
      viewport={{ once: false, amount: 0.16 }}
      transition={{ duration: 0.6, ease: "easeOut" }}
    >
      <div className={styles.contactFrame}>
        <div className={styles.contactIntro}>
          <div className={styles.contactEyebrow}>
            <Sparkles size={14} aria-hidden="true" />A DIRECT LINE TO AVERQEL
          </div>
          <h2 id={id + "-title"} className={styles.contactTitle}>
            Have a question?
            <span>Let’s talk.</span>
          </h2>
          <p className={styles.contactLead}>
            Send a question, report a problem, or share an idea. Your message goes straight to the
            developer, who can reply to the email address you provide.
          </p>

          <div className={styles.contactSignal} aria-hidden="true">
            <div className={styles.signalOrbit + " " + styles.signalOrbitOuter}>
              <span className={styles.signalOrbitNode} />
            </div>
            <div className={styles.signalOrbit + " " + styles.signalOrbitInner}>
              <span className={styles.signalOrbitNode} />
            </div>
            <div className={styles.signalCore}>
              <MessageSquareText size={27} strokeWidth={1.7} />
            </div>
            <span className={styles.signalSpark + " " + styles.signalSparkOne} />
            <span className={styles.signalSpark + " " + styles.signalSparkTwo} />
          </div>

          <div className={styles.contactSignalCaption}>
            <span className={styles.signalCaptionStatus}>
              <i aria-hidden="true" />
              SERVER-SIDE DELIVERY
            </span>
            <span>NO PUBLIC EMAIL ADDRESS</span>
          </div>

          <div className={styles.contactPrivacyCard}>
            <span className={styles.contactPrivacyIcon}>
              <LockKeyhole size={17} aria-hidden="true" />
            </span>
            <p>
              Your reply address is used to respond to you. The message is sent through the
              configured mail service and is not stored in AverQel’s app database.
            </p>
          </div>
          <p className={styles.contactPrivacyLink}>
            Please don’t include passwords, API keys, or private documents. Read the{" "}
            <Link href="/legal/privacy">privacy notice</Link>.
          </p>
        </div>

        <form
          className={styles.contactForm}
          onSubmit={submitContact}
          aria-busy={sending}
          noValidate
        >
          <div className={styles.contactFormHeader}>
            <div className={styles.formTitleGroup}>
              <span className={styles.formIcon}>
                <Mail size={16} aria-hidden="true" />
              </span>
              <div>
                <h3>Send a message</h3>
                <p>Usually takes less than a minute</p>
              </div>
            </div>
            <span className={styles.contactAvailability} data-state={String(available)}>
              <i aria-hidden="true" />
              {statusText}
            </span>
          </div>

          <div
            className={styles.formProgress}
            role="progressbar"
            aria-label={completedFields + " of 4 message fields completed"}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={completionPercent}
          >
            <span style={{ width: completionPercent + "%" }} />
          </div>

          <div className={styles.verificationBlock}>
            <div className={styles.contactField}>
              <label htmlFor={id + "-email"}>Email for my reply</label>
              <div className={styles.emailVerificationRow}>
                <input
                  id={id + "-email"}
                  type="email"
                  autoComplete="email"
                  inputMode="email"
                  maxLength={254}
                  placeholder="you@example.com"
                  required
                  readOnly={Boolean(challengeId || verificationToken)}
                  disabled={available !== true || requestingCode || checkingCode || sending}
                  aria-invalid={fieldErrors.email ? true : undefined}
                  aria-describedby={fieldErrors.email ? id + "-email-error" : undefined}
                  value={fields.email}
                  onChange={(event) => updateField("email", event.target.value)}
                />
                {verificationToken && (
                  <span className={styles.verifiedBadge}>
                    <CheckCircle2 size={15} aria-hidden="true" /> Verified
                  </span>
                )}
              </div>
              {fieldErrors.email && (
                <span id={id + "-email-error"} className={styles.fieldError}>
                  {fieldErrors.email}
                </span>
              )}
            </div>

            {!verificationToken && !challengeId && (
              <div className={styles.verificationActions}>
                <p className={styles.verificationHint}>
                  We’ll email a one-time code before you can write your message.
                </p>
                <button
                  type="button"
                  className={styles.verifyButton}
                  onClick={requestVerificationCode}
                  disabled={available !== true || requestingCode || checkingCode || sending}
                >
                  {requestingCode ? (
                    <>
                      Sending code
                      <LoaderCircle className={styles.submitSpinner} size={15} aria-hidden="true" />
                    </>
                  ) : (
                    "Email me a code"
                  )}
                </button>
              </div>
            )}

            {challengeId && !verificationToken && (
              <div className={styles.codeVerification}>
                <p id={id + "-code-hint"} className={styles.verificationHint}>
                  Enter the six-digit code sent to this address. It expires in 10 minutes.
                </p>
                <div className={styles.codeVerificationRow}>
                  <div className={styles.contactField}>
                    <label htmlFor={id + "-verification-code"}>Verification code</label>
                    <input
                      id={id + "-verification-code"}
                      type="text"
                      inputMode="numeric"
                      autoComplete="one-time-code"
                      pattern="[0-9]{6}"
                      maxLength={6}
                      placeholder="000000"
                      aria-describedby={id + "-code-hint"}
                      value={verificationCode}
                      onChange={(event) =>
                        setVerificationCode(event.target.value.replace(/\D/g, "").slice(0, 6))
                      }
                    />
                  </div>
                  <button
                    type="button"
                    className={styles.verifyButton}
                    onClick={confirmVerificationCode}
                    disabled={verificationCode.length !== 6 || checkingCode || requestingCode}
                  >
                    {checkingCode ? "Checking code" : "Verify email"}
                  </button>
                </div>
                <div className={styles.verificationSecondaryActions}>
                  <button type="button" onClick={requestVerificationCode} disabled={requestingCode}>
                    {requestingCode ? "Sending…" : "Send a new code"}
                  </button>
                  <button type="button" onClick={changeEmailAddress}>
                    Change email
                  </button>
                </div>
              </div>
            )}

            {verificationToken && (
              <p className={styles.verificationComplete} role="status">
                Email verified. You can now write and send your message.
                <button type="button" onClick={changeEmailAddress}>
                  Change email
                </button>
              </p>
            )}
          </div>

          {verificationToken ? (
            <fieldset className={styles.contactFields} disabled={available !== true || sending}>
              <legend className={styles.visuallyHidden}>Message details</legend>

              <div className={styles.contactFieldGrid}>
                <div className={styles.contactField}>
                  <label htmlFor={id + "-name"}>Your name</label>
                  <input
                    id={id + "-name"}
                    autoComplete="name"
                    maxLength={100}
                    placeholder="How should I address you?"
                    required
                    aria-invalid={fieldErrors.name ? true : undefined}
                    aria-describedby={fieldErrors.name ? id + "-name-error" : undefined}
                    value={fields.name}
                    onChange={(event) => updateField("name", event.target.value)}
                  />
                  {fieldErrors.name && (
                    <span id={id + "-name-error"} className={styles.fieldError}>
                      {fieldErrors.name}
                    </span>
                  )}
                </div>
                <div className={styles.contactField}>
                  <label htmlFor={id + "-subject"}>Subject</label>
                  <input
                    id={id + "-subject"}
                    maxLength={120}
                    placeholder="What would you like to discuss?"
                    required
                    aria-invalid={fieldErrors.subject ? true : undefined}
                    aria-describedby={fieldErrors.subject ? id + "-subject-error" : undefined}
                    value={fields.subject}
                    onChange={(event) => updateField("subject", event.target.value)}
                  />
                  {fieldErrors.subject && (
                    <span id={id + "-subject-error"} className={styles.fieldError}>
                      {fieldErrors.subject}
                    </span>
                  )}
                </div>
              </div>

              <div className={styles.subjectStarters} aria-label="Subject suggestions">
                {SUBJECT_STARTERS.map((subject) => (
                  <button
                    key={subject}
                    type="button"
                    aria-pressed={fields.subject === subject}
                    onClick={() => updateField("subject", subject)}
                  >
                    {subject}
                  </button>
                ))}
              </div>

              <div className={styles.contactField}>
                <label className={styles.messageLabel} htmlFor={id + "-message"}>
                  <span>Your message</span>
                  <span className={styles.messageCount} aria-hidden="true">
                    {fields.message.length} / 8,000
                  </span>
                </label>
                <textarea
                  id={id + "-message"}
                  aria-label="Your message"
                  rows={5}
                  maxLength={MESSAGE_LIMIT}
                  placeholder="Share the details that will help me respond."
                  required
                  aria-invalid={fieldErrors.message ? true : undefined}
                  aria-describedby={fieldErrors.message ? id + "-message-error" : undefined}
                  value={fields.message}
                  onChange={(event) => updateField("message", event.target.value)}
                />
                {fieldErrors.message && (
                  <span id={id + "-message-error"} className={styles.fieldError}>
                    {fieldErrors.message}
                  </span>
                )}
              </div>

              <div className={styles.contactHoneypot} aria-hidden="true">
                <label htmlFor={id + "-website"}>Leave this field empty</label>
                <input
                  id={id + "-website"}
                  name="website"
                  tabIndex={-1}
                  autoComplete="off"
                  value={fields.website}
                  onChange={(event) => updateField("website", event.target.value)}
                />
              </div>
            </fieldset>
          ) : (
            <p className={styles.verificationLocked}>
              Verify your email address to unlock the message fields.
            </p>
          )}

          <div className={styles.contactSubmitRow}>
            <div className={styles.submitNote}>
              <ShieldCheck size={15} aria-hidden="true" />
              <p
                role="status"
                aria-live="polite"
                className={sent ? styles.contactSuccess : styles.contactFeedback}
              >
                {feedback ||
                  (available === null
                    ? "Checking whether contact delivery is configured."
                    : available
                      ? "Email verification and contact delivery are configured."
                      : "Contact delivery is temporarily unavailable. Please check back later.")}
              </p>
            </div>
            {verificationToken && (
              <button
                type="submit"
                className={styles.contactSubmit}
                disabled={available !== true || sending}
              >
                <span>{sending ? "Sending message" : sent ? "Send another" : "Send message"}</span>
                {sending ? (
                  <LoaderCircle className={styles.submitSpinner} size={17} aria-hidden="true" />
                ) : sent ? (
                  <CheckCircle2 size={17} aria-hidden="true" />
                ) : (
                  <ArrowRight size={17} aria-hidden="true" />
                )}
              </button>
            )}
          </div>
        </form>
      </div>
    </motion.section>
  );
}
