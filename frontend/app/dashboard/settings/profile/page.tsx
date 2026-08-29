"use client";

import { motion, AnimatePresence } from "framer-motion";
import Image from "next/image";
import Link from "next/link";
import QRCode from "qrcode";
import {
  User,
  Mail,
  Shield,
  Clock,
  Key,
  Building2,
  Lock,
  Unlock,
  CheckCircle2,
  AlertCircle,
  Loader2,
  ShieldCheck,
  ChevronRight,
  Eye,
  EyeOff,
  Copy,
  ArrowRight,
} from "lucide-react";
import { useState, useEffect } from "react";
import toast from "react-hot-toast";
import { fetchWithAuth } from "@/lib/api";
import { getRoleLabel } from "@/lib/roles";
import DashboardSectionHeader from "@/app/components/ui/DashboardSectionHeader";

interface ProfileData {
  user_id: string;
  tenant_id: string;
  collection_code: string;
  email: string;
  roles: string[];
  status: string;
  created_at: string;
  last_login_at: string | null;
  totp_enabled: boolean;
}

const sectionVariants = {
  hidden: { opacity: 0, y: 28 },
  show: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: {
      type: "spring" as const,
      stiffness: 280,
      damping: 26,
      delay: 0.1 + i * 0.08,
    },
  }),
};

export default function ProfilePage() {
  const [profile, setProfile] = useState<ProfileData | null>(null);
  const [loading, setLoading] = useState(true);
  const [showPasswordModal, setShowPasswordModal] = useState(false);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [changing, setChanging] = useState(false);
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showPasswords, setShowPasswords] = useState(false);

  // 2FA state
  const [show2faSetup, setShow2faSetup] = useState(false);
  const [totpSecret, setTotpSecret] = useState("");
  const [totpUri, setTotpUri] = useState("");
  const [totpQrCode, setTotpQrCode] = useState("");
  const [totpCode, setTotpCode] = useState("");
  const [backupCodes, setBackupCodes] = useState<string[]>([]);
  const [twoFaStep, setTwoFaStep] = useState<"setup" | "confirm" | "backup">("setup");
  const [twoFaLoading, setTwoFaLoading] = useState(false);
  const [twoFaError, setTwoFaError] = useState<string | null>(null);
  const [showDisable2fa, setShowDisable2fa] = useState(false);
  const [disablePassword, setDisablePassword] = useState("");
  const [logoutAllLoading, setLogoutAllLoading] = useState(false);

  useEffect(() => {
    const fetchProfile = async () => {
      try {
        const res = (await fetchWithAuth("/auth/profile")) as Response;
        if (res.ok) {
          const data = await res.json();
          setProfile(data);
        } else {
          const status = res.status;
          const body = await res.text();
          console.error(`[Profile] Load failed with status ${status}:`, body);
          setError("Failed to load profile data.");
        }
      } catch {
        setError("Connection to profile service failed.");
      } finally {
        setLoading(false);
      }
    };
    fetchProfile();
  }, []);

  useEffect(() => {
    let cancelled = false;

    const generateQrCode = async () => {
      if (!totpUri) {
        setTotpQrCode("");
        return;
      }
      try {
        const dataUrl = await QRCode.toDataURL(totpUri, {
          errorCorrectionLevel: "M",
          margin: 1,
          width: 220,
        });
        if (!cancelled) {
          setTotpQrCode(dataUrl);
        }
      } catch {
        if (!cancelled) {
          setTotpQrCode("");
        }
      }
    };

    generateQrCode();

    return () => {
      cancelled = true;
    };
  }, [totpUri]);

  const handleChangePassword = async () => {
    if (newPassword !== confirmPassword) {
      setMessage({ type: "error", text: "New passwords do not match." });
      return;
    }
    setChanging(true);
    setMessage(null);
    try {
      const res = (await fetchWithAuth("/auth/change-password", {
        method: "POST",
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword,
        }),
      })) as Response;
      if (res.ok) {
        setMessage({
          type: "success",
          text: "Password changed successfully! Please log in again if required.",
        });
        setTimeout(() => setShowPasswordModal(false), 2000);
        setCurrentPassword("");
        setNewPassword("");
        setConfirmPassword("");
      } else {
        const err = await res.json();
        setMessage({ type: "error", text: err.detail || "Failed to change password." });
      }
    } catch {
      setMessage({ type: "error", text: "An unexpected error occurred." });
    } finally {
      setChanging(false);
    }
  };

  const handleSetup2fa = async () => {
    setTwoFaLoading(true);
    setTwoFaError(null);
    try {
      const res = (await fetchWithAuth("/auth/2fa/setup", { method: "POST" })) as Response;
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || err.message || "Failed to start 2FA setup.");
      }
      const data = await res.json();
      setTotpSecret(data.secret);
      setTotpUri(data.provisioning_uri);
      setTotpQrCode("");
      setTwoFaStep("confirm");
    } catch (e) {
      setTwoFaError(e instanceof Error ? e.message : "Setup failed.");
    } finally {
      setTwoFaLoading(false);
    }
  };

  const handleConfirm2fa = async () => {
    setTwoFaLoading(true);
    setTwoFaError(null);
    try {
      const res = (await fetchWithAuth("/auth/2fa/confirm", {
        method: "POST",
        body: JSON.stringify({ code: totpCode }),
      })) as Response;
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || err.message || "Invalid code.");
      }
      const data = await res.json();
      setBackupCodes(data.backup_codes);
      setTwoFaStep("backup");
      if (profile) setProfile({ ...profile, totp_enabled: true });
    } catch (e) {
      setTwoFaError(e instanceof Error ? e.message : "Confirmation failed.");
    } finally {
      setTwoFaLoading(false);
    }
  };

  const handleDisable2fa = async () => {
    setTwoFaLoading(true);
    setTwoFaError(null);
    try {
      const res = (await fetchWithAuth("/auth/2fa/disable", {
        method: "POST",
        body: JSON.stringify({ password: disablePassword }),
      })) as Response;
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || err.message || "Failed to disable 2FA.");
      }
      if (profile) setProfile({ ...profile, totp_enabled: false });
      setShowDisable2fa(false);
      setDisablePassword("");
    } catch (e) {
      setTwoFaError(e instanceof Error ? e.message : "Disable failed.");
    } finally {
      setTwoFaLoading(false);
    }
  };

  const handleLogoutAll = async () => {
    setLogoutAllLoading(true);
    try {
      const res = (await fetchWithAuth("/auth/logout-all", { method: "POST" })) as Response;
      if (res.ok) {
        window.location.replace("/auth/login");
      }
    } catch {
      // still redirect — token is likely revoked
      window.location.replace("/auth/login");
    } finally {
      setLogoutAllLoading(false);
    }
  };

  const handleCopyCollectionCode = async () => {
    const collectionCode = profile?.collection_code;
    if (!collectionCode) {
      return;
    }
    try {
      await navigator.clipboard.writeText(collectionCode);
      toast.success("Collection ID copied.");
    } catch {
      toast.error("Failed to copy collection ID.");
    }
  };

  if (loading) {
    return (
      <div className="flex min-h-[400px] items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="text-primary animate-spin" size={32} />
          <p className="text-muted-foreground text-sm">Loading profile...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex min-h-[400px] flex-col items-center justify-center space-y-4">
        <AlertCircle className="text-red-500" size={48} />
        <p className="text-foreground font-medium">{error}</p>
        <button
          onClick={() => window.location.reload()}
          className="bg-primary text-primary-foreground rounded-xl px-6 py-2 text-xs font-bold tracking-widest uppercase transition-colors hover:brightness-110"
        >
          Retry
        </button>
      </div>
    );
  }

  if (!profile) return null;

  return (
    <div className="w-full space-y-8">
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: "easeOut" }}
      >
        <DashboardSectionHeader
          title="Account Profile"
          subtitle="Identity And Security Preference"
          icon={User}
          accentClassName="bg-indigo-500 text-indigo-500"
          accentGlowClassName="shadow-[0_0_20px_rgba(99,102,241,0.4)]"
          backHref="/dashboard/settings"
          backLabel="Back To Settings"
        />
      </motion.div>

      <div className="grid grid-cols-1 gap-8 xl:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)]">
        {/* Core Identity */}
        <motion.div
          custom={0}
          variants={sectionVariants}
          initial="hidden"
          animate="show"
          className="settings-section space-y-6 p-8"
        >
          <h3 className="text-foreground flex items-center gap-3 pb-4 text-sm font-semibold tracking-[0.18em] uppercase">
            <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-emerald-500/10">
              <ShieldCheck size={15} className="text-emerald-400" />
            </div>
            Core Identity
          </h3>
          <div className="settings-divider -mx-8" />

          <div className="space-y-5">
            <div className="settings-info-row hover:bg-primary/[0.03] flex items-center gap-4 rounded-xl p-2 transition-colors">
              <div className="settings-icon-glow border-primary/20 bg-primary/10 text-primary flex h-12 w-12 items-center justify-center rounded-2xl border">
                <Mail size={20} />
              </div>
              <div>
                <p className="text-muted-foreground text-[10px] font-bold tracking-tighter uppercase">
                  Primary Email
                </p>
                <p className="text-foreground font-medium">{profile.email}</p>
              </div>
            </div>

            <div className="settings-info-row flex items-center gap-4 rounded-xl p-2 transition-colors hover:bg-purple-500/[0.03]">
              <div className="settings-icon-glow flex h-12 w-12 items-center justify-center rounded-2xl border border-purple-500/20 bg-purple-500/10 text-purple-400">
                <Building2 size={20} />
              </div>
              <div>
                <p className="text-muted-foreground text-[10px] font-bold tracking-tighter uppercase">
                  Collection ID
                </p>
                <div className="mt-1 flex items-center gap-2">
                  <p className="text-muted-foreground font-mono text-xs tracking-[0.2em] uppercase">
                    {profile.collection_code}
                  </p>
                  <button
                    type="button"
                    onClick={() => void handleCopyCollectionCode()}
                    className="border-glass-border text-muted-foreground hover:text-primary hover:border-primary/30 hover:bg-primary/10 rounded-lg border px-2 py-1 transition-all"
                    aria-label="Copy collection ID"
                  >
                    <Copy size={12} />
                  </button>
                </div>
              </div>
            </div>

            <div className="settings-info-row flex items-center gap-4 rounded-xl p-2 transition-colors hover:bg-purple-500/[0.03]">
              <div className="settings-icon-glow flex h-12 w-12 items-center justify-center rounded-2xl border border-purple-500/20 bg-purple-500/10 text-purple-400">
                <Building2 size={20} />
              </div>
              <div>
                <p className="text-muted-foreground text-[10px] font-bold tracking-tighter uppercase">
                  Tenant ID
                </p>
                <p className="text-muted-foreground font-mono text-xs">{profile.tenant_id}</p>
              </div>
            </div>

            <div className="settings-info-row flex items-center gap-4 rounded-xl p-2 transition-colors hover:bg-orange-500/[0.03]">
              <div className="settings-icon-glow flex h-12 w-12 items-center justify-center rounded-2xl border border-orange-500/20 bg-orange-500/10 text-orange-400">
                <Shield size={20} />
              </div>
              <div>
                <p className="text-muted-foreground text-[10px] font-bold tracking-tighter uppercase">
                  Assigned Roles
                </p>
                <div className="mt-1 flex gap-2">
                  {profile.roles.map((role) => (
                    <span
                      key={role}
                      className="settings-role-badge rounded-md px-2.5 py-0.5 text-[9px] font-bold tracking-widest uppercase"
                    >
                      {getRoleLabel(role)}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </motion.div>

        {/* Security & Access */}
        <motion.div
          custom={1}
          variants={sectionVariants}
          initial="hidden"
          animate="show"
          className="settings-section space-y-6 p-8"
        >
          <h3 className="text-foreground flex items-center gap-3 pb-4 text-sm font-semibold tracking-[0.18em] uppercase">
            <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-red-500/10">
              <Lock size={15} className="text-red-400" />
            </div>
            Security & Access
          </h3>
          <div className="settings-divider -mx-8" />

          <div className="space-y-5">
            <div className="settings-info-row flex items-center gap-4 rounded-xl p-2 transition-colors hover:bg-green-500/[0.03]">
              <div
                className={`settings-icon-glow flex h-12 w-12 items-center justify-center rounded-2xl border transition-colors ${profile.status === "active" ? "border-green-500/20 bg-green-500/10 text-green-400" : "border-red-500/20 bg-red-500/10 text-red-400"}`}
              >
                {profile.status === "active" ? <Unlock size={20} /> : <Lock size={20} />}
              </div>
              <div>
                <p className="text-muted-foreground text-[10px] font-bold tracking-tighter uppercase">
                  Account Status
                </p>
                <div className="flex items-center gap-2">
                  <span
                    className={`settings-status-dot ${profile.status === "active" ? "text-green-400" : "text-red-400"}`}
                  />
                  <p
                    className={`text-[11px] font-bold tracking-widest uppercase ${profile.status === "active" ? "text-green-400" : "text-red-400"}`}
                  >
                    {profile.status}
                  </p>
                </div>
              </div>
            </div>

            <div className="settings-info-row flex items-center gap-4 rounded-xl p-2 transition-colors hover:bg-slate-500/[0.03]">
              <div className="settings-icon-glow bg-muted border-glass-border text-muted-foreground flex h-12 w-12 items-center justify-center rounded-2xl border">
                <Clock size={20} />
              </div>
              <div>
                <p className="text-muted-foreground text-[10px] font-bold tracking-tighter uppercase">
                  Last Authentication
                </p>
                <p className="text-foreground text-sm">
                  {profile.last_login_at
                    ? new Date(profile.last_login_at).toLocaleString()
                    : "Never"}
                </p>
              </div>
            </div>

            <motion.button
              onClick={() => setShowPasswordModal(true)}
              whileHover={{ scale: 1.01 }}
              whileTap={{ scale: 0.99 }}
              className="settings-card group mt-2 flex w-full items-center justify-between px-6 py-4"
            >
              <div className="relative z-[1] flex items-center gap-3">
                <Key size={16} className="text-primary" />
                <span className="text-foreground text-sm font-bold">Change Credentials</span>
              </div>
              <ChevronRight
                size={14}
                className="text-muted-foreground relative z-[1] transition-transform group-hover:translate-x-1"
              />
            </motion.button>
          </div>
        </motion.div>
      </div>

      <div className="grid grid-cols-1 gap-8 xl:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)]">
        {/* Two-Factor Authentication */}
        <motion.div
          custom={2}
          variants={sectionVariants}
          initial="hidden"
          animate="show"
          className="settings-section space-y-6 p-8"
        >
          <h3 className="text-foreground flex items-center gap-3 pb-4 text-sm font-semibold tracking-[0.18em] uppercase">
            <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-purple-500/10">
              <Shield size={15} className="text-purple-400" />
            </div>
            Two-Factor Authentication
          </h3>
          <div className="settings-divider -mx-8" />

          {profile.totp_enabled ? (
            <div className="space-y-4">
              <div className="flex items-center gap-3">
                <CheckCircle2 size={18} className="text-green-400" />
                <span className="text-foreground text-sm font-bold">2FA is active</span>
              </div>
              <p className="text-muted-foreground text-xs leading-relaxed">
                Your account is protected with TOTP-based two-factor authentication.
              </p>
              {!showDisable2fa ? (
                <motion.button
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                  onClick={() => {
                    setShowDisable2fa(true);
                    setTwoFaError(null);
                  }}
                  className="rounded-xl border border-red-500/25 bg-red-500/8 px-6 py-2.5 text-xs font-bold tracking-widest text-red-400 uppercase transition-all hover:border-red-500/40 hover:bg-red-500/12"
                >
                  Disable 2FA
                </motion.button>
              ) : (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: "auto" }}
                  className="space-y-3"
                >
                  {twoFaError && (
                    <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-300">
                      {twoFaError}
                    </div>
                  )}
                  <input
                    type="password"
                    placeholder="Enter your password to confirm"
                    value={disablePassword}
                    onChange={(e) => setDisablePassword(e.target.value)}
                    className="bg-muted border-glass-border text-foreground w-full rounded-xl border px-4 py-3 text-sm outline-none focus:border-red-500/50"
                  />
                  <div className="flex gap-3">
                    <button
                      onClick={() => {
                        setShowDisable2fa(false);
                        setDisablePassword("");
                        setTwoFaError(null);
                      }}
                      className="bg-muted text-muted-foreground border-glass-border rounded-xl border px-4 py-2 text-xs font-bold uppercase"
                    >
                      Cancel
                    </button>
                    <button
                      onClick={handleDisable2fa}
                      disabled={twoFaLoading || !disablePassword}
                      className="rounded-xl bg-red-600 px-4 py-2 text-xs font-bold text-white uppercase transition-all hover:bg-red-500 disabled:opacity-50"
                    >
                      {twoFaLoading ? "Disabling..." : "Confirm Disable"}
                    </button>
                  </div>
                </motion.div>
              )}
            </div>
          ) : !show2faSetup ? (
            <div className="space-y-4">
              <p className="text-muted-foreground text-xs leading-relaxed">
                Add an extra layer of security by enabling TOTP-based two-factor authentication with
                any authenticator app (Google Authenticator, Authy, etc).
              </p>
              <motion.button
                whileHover={{ scale: 1.03 }}
                whileTap={{ scale: 0.98 }}
                onClick={() => {
                  setShow2faSetup(true);
                  setTwoFaStep("setup");
                  setTwoFaError(null);
                }}
                className="settings-btn-glow rounded-xl bg-gradient-to-r from-purple-600 to-purple-500 px-6 py-2.5 text-xs font-bold text-white uppercase shadow-lg shadow-purple-900/20 transition-all hover:from-purple-500 hover:to-purple-400"
              >
                Enable 2FA
              </motion.button>
            </div>
          ) : (
            <div className="space-y-4">
              {twoFaError && (
                <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-300">
                  {twoFaError}
                </div>
              )}

              {twoFaStep === "setup" && (
                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="space-y-4"
                >
                  <p className="text-muted-foreground text-xs">
                    Click below to generate a TOTP secret for your authenticator app.
                  </p>
                  <button
                    onClick={handleSetup2fa}
                    disabled={twoFaLoading}
                    className="rounded-xl bg-purple-600 px-6 py-2.5 text-xs font-bold text-white uppercase transition-all hover:bg-purple-500 disabled:opacity-50"
                  >
                    {twoFaLoading ? "Generating..." : "Generate Secret"}
                  </button>
                  <button
                    onClick={() => setShow2faSetup(false)}
                    className="text-muted-foreground ml-3 text-xs hover:underline"
                  >
                    Cancel
                  </button>
                </motion.div>
              )}

              {twoFaStep === "confirm" && (
                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="space-y-4"
                >
                  <p className="text-muted-foreground text-xs leading-relaxed">
                    Scan this QR code with Google Authenticator, Authy, or another TOTP app. You can
                    still enter the secret manually if needed.
                  </p>
                  <div className="settings-section flex justify-center p-4">
                    {totpQrCode ? (
                      <Image
                        src={totpQrCode}
                        alt="TOTP QR code for authenticator app setup"
                        width={220}
                        height={220}
                        className="h-[220px] w-[220px] rounded-lg bg-white p-2"
                        unoptimized
                      />
                    ) : (
                      <div className="text-muted-foreground flex h-[220px] w-[220px] items-center justify-center text-xs">
                        Generating QR code...
                      </div>
                    )}
                  </div>
                  <div className="settings-section p-4">
                    <p className="text-muted-foreground mb-1 text-[10px] font-bold tracking-widest uppercase">
                      Manual Entry Key
                    </p>
                    <p className="text-foreground font-mono text-sm tracking-wider break-all">
                      {totpSecret}
                    </p>
                  </div>
                  <div className="settings-section p-4">
                    <p className="text-muted-foreground mb-1 text-[10px] font-bold tracking-widest uppercase">
                      Provisioning URI
                    </p>
                    <p className="text-muted-foreground font-mono text-[10px] break-all">
                      {totpUri}
                    </p>
                  </div>
                  <div>
                    <label className="text-muted-foreground mb-2 block text-[10px] font-bold tracking-widest uppercase">
                      Enter code from authenticator
                    </label>
                    <input
                      type="text"
                      maxLength={6}
                      value={totpCode}
                      onChange={(e) => setTotpCode(e.target.value.replace(/\D/g, ""))}
                      className="bg-muted border-glass-border text-foreground w-full rounded-xl border px-4 py-3 text-center font-mono text-lg tracking-[0.5em] outline-none focus:border-purple-500/50"
                      placeholder="000000"
                      autoComplete="one-time-code"
                    />
                  </div>
                  <div className="flex gap-3">
                    <button
                      onClick={() => {
                        setShow2faSetup(false);
                        setTotpCode("");
                      }}
                      className="bg-muted text-muted-foreground border-glass-border rounded-xl border px-4 py-2 text-xs font-bold uppercase"
                    >
                      Cancel
                    </button>
                    <button
                      onClick={handleConfirm2fa}
                      disabled={twoFaLoading || totpCode.length !== 6}
                      className="rounded-xl bg-purple-600 px-6 py-2.5 text-xs font-bold text-white uppercase transition-all hover:bg-purple-500 disabled:opacity-50"
                    >
                      {twoFaLoading ? "Verifying..." : "Verify & Enable"}
                    </button>
                  </div>
                </motion.div>
              )}

              {twoFaStep === "backup" && (
                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="space-y-4"
                >
                  <div className="rounded-xl border border-yellow-500/30 bg-yellow-500/10 p-4">
                    <p className="mb-2 text-xs font-bold text-yellow-300">
                      Save these backup codes in a safe place. Each code can only be used once.
                    </p>
                    <div className="grid grid-cols-2 gap-2">
                      {backupCodes.map((code) => (
                        <span
                          key={code}
                          className="bg-muted text-foreground rounded border border-yellow-500/20 px-3 py-1.5 text-center font-mono text-xs"
                        >
                          {code}
                        </span>
                      ))}
                    </div>
                  </div>
                  <button
                    onClick={() => {
                      setShow2faSetup(false);
                      setBackupCodes([]);
                      setTotpCode("");
                    }}
                    className="rounded-xl bg-green-600 px-6 py-2.5 text-xs font-bold text-white uppercase transition-all hover:bg-green-500"
                  >
                    Done
                  </button>
                </motion.div>
              )}
            </div>
          )}
        </motion.div>

        <div className="space-y-8">
          {/* Logout All Devices */}
          <motion.div
            custom={3}
            variants={sectionVariants}
            initial="hidden"
            animate="show"
            className="settings-section space-y-4 p-8"
          >
            <h3 className="text-foreground flex items-center gap-3 pb-4 text-sm font-semibold tracking-[0.18em] uppercase">
              <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-red-500/10">
                <AlertCircle size={15} className="text-red-400" />
              </div>
              Session Management
            </h3>
            <div className="settings-divider -mx-8" />
            <p className="text-muted-foreground text-xs leading-relaxed">
              Sign out from all devices and invalidate all active sessions. You will be redirected
              to the login page.
            </p>
            <motion.button
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              onClick={handleLogoutAll}
              disabled={logoutAllLoading}
              className="rounded-xl border border-red-500/25 bg-red-500/8 px-6 py-2.5 text-xs font-bold text-red-400 uppercase transition-all hover:border-red-500/40 hover:bg-red-500/12 disabled:opacity-50"
            >
              {logoutAllLoading ? "Signing out..." : "Logout All Devices"}
            </motion.button>
          </motion.div>

          <motion.div
            custom={4}
            variants={sectionVariants}
            initial="hidden"
            animate="show"
            className="settings-featured p-8"
          >
            <div className="relative z-[1] space-y-4">
              <h3 className="text-foreground flex items-center gap-3 pb-4 text-sm font-semibold tracking-[0.18em] uppercase">
                <div className="bg-primary/10 flex h-8 w-8 items-center justify-center rounded-xl">
                  <Shield size={15} className="text-primary" />
                </div>
                Trust & Privacy
              </h3>
              <div className="settings-divider -mx-8" />
              <p className="text-muted-foreground text-xs leading-7">
                AverQel needs account and security metadata to keep your login, sessions, and
                recovery safe. Documents, prompts, and chat history are product content and should
                not be casually accessed outside support, security, abuse, or legal handling.
              </p>
              <div className="flex flex-wrap gap-3">
                <Link
                  href="/dashboard/settings/privacy"
                  className="bg-primary/10 text-primary border-primary/25 hover:border-primary/35 hover:bg-primary/15 inline-flex items-center gap-2 rounded-xl border px-4 py-2.5 text-xs font-bold tracking-widest uppercase transition-all"
                >
                  Open Trust Center
                  <ArrowRight size={12} />
                </Link>
                <Link
                  href="/legal/privacy"
                  className="bg-muted text-muted-foreground border-glass-border hover:text-foreground rounded-xl border px-4 py-2.5 text-xs font-bold tracking-widest uppercase transition-all hover:border-white/15"
                >
                  Privacy Policy
                </Link>
              </div>
            </div>
          </motion.div>
        </div>
      </div>

      {/* Password Modal */}
      <AnimatePresence>
        {showPasswordModal && (
          <div className="fixed inset-0 z-[100] flex items-center justify-center p-6">
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              onClick={() => {
                if (!changing) setShowPasswordModal(false);
              }}
              className="absolute inset-0 bg-black/50 backdrop-blur-md"
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.92, y: 30 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.92, y: 30 }}
              transition={{ type: "spring" as const, stiffness: 340, damping: 30 }}
              className="settings-section relative w-full max-w-md space-y-8 p-10 shadow-2xl"
            >
              <div className="space-y-2">
                <h3 className="text-foreground text-2xl font-bold tracking-tight">
                  Update Password
                </h3>
                <p className="text-muted-foreground text-sm">
                  Ensure your new password contains at least 8 characters.
                </p>
              </div>

              <div className="settings-divider" />

              <div className="space-y-4">
                <div className="relative">
                  <label className="text-muted-foreground mb-2 block text-[10px] font-bold tracking-widest uppercase">
                    Current Password
                  </label>
                  <input
                    type={showPasswords ? "text" : "password"}
                    value={currentPassword}
                    onChange={(e) => setCurrentPassword(e.target.value)}
                    className="bg-muted border-glass-border text-foreground w-full rounded-xl border px-4 py-3 text-sm transition-colors outline-none focus:border-blue-500/50"
                  />
                  <button
                    onClick={() => setShowPasswords(!showPasswords)}
                    className="text-muted-foreground hover:text-foreground absolute top-9 right-4 transition-colors"
                  >
                    {showPasswords ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </div>

                <div className="space-y-3">
                  <div className="relative">
                    <label className="text-muted-foreground mb-2 block text-[10px] font-bold tracking-widest uppercase">
                      New Password
                    </label>
                    <input
                      type={showPasswords ? "text" : "password"}
                      value={newPassword}
                      onChange={(e) => setNewPassword(e.target.value)}
                      className="bg-muted border-glass-border text-foreground w-full rounded-xl border px-4 py-3 text-sm transition-colors outline-none focus:border-blue-500/50"
                    />
                  </div>
                  <div className="relative">
                    <label className="text-muted-foreground mb-2 block text-[10px] font-bold tracking-widest uppercase">
                      Confirm New Password
                    </label>
                    <input
                      type={showPasswords ? "text" : "password"}
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                      className="bg-muted border-glass-border text-foreground w-full rounded-xl border px-4 py-3 text-sm transition-colors outline-none focus:border-blue-500/50"
                    />
                  </div>
                </div>
              </div>

              {message && (
                <motion.div
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  className={`flex items-center gap-3 rounded-xl p-4 text-xs font-bold tracking-widest uppercase ${message.type === "success" ? "border border-green-500/20 bg-green-500/10 text-green-300" : "border border-red-500/20 bg-red-500/10 text-red-300"}`}
                >
                  {message.type === "success" ? (
                    <CheckCircle2 size={16} />
                  ) : (
                    <AlertCircle size={16} />
                  )}
                  {message.text}
                </motion.div>
              )}

              <div className="flex gap-4">
                <motion.button
                  whileHover={{ scale: 1.01 }}
                  whileTap={{ scale: 0.99 }}
                  onClick={() => setShowPasswordModal(false)}
                  disabled={changing}
                  className="bg-muted text-muted-foreground hover:bg-muted/80 border-glass-border flex-1 rounded-xl border px-6 py-3 text-sm font-bold tracking-widest uppercase transition-all"
                >
                  Cancel
                </motion.button>
                <motion.button
                  whileHover={{ scale: 1.01 }}
                  whileTap={{ scale: 0.99 }}
                  onClick={handleChangePassword}
                  disabled={changing || !currentPassword || !newPassword || !confirmPassword}
                  className="disabled:bg-muted disabled:text-muted-foreground flex flex-1 items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-blue-600 to-blue-500 px-6 py-3 text-sm font-bold tracking-widest text-white uppercase shadow-lg shadow-blue-900/20 transition-all hover:from-blue-500 hover:to-blue-400"
                >
                  {changing ? (
                    <Loader2 size={16} className="animate-spin" />
                  ) : (
                    <ShieldCheck size={16} />
                  )}
                  {changing ? "Updating..." : "Update"}
                </motion.button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
}
