"use client";

import { useState, useEffect } from "react";
import { Activity } from "lucide-react";
import { fetchWithAuth } from "@/lib/api";
import { useVisibilityAwareInterval } from "@/app/hooks/useVisibilityAwareInterval";

function healthVersionInfo(data: Record<string, unknown>): string | null {
  const version = typeof data.version === "string" ? data.version.trim() : "";
  const sha = typeof data.git_sha === "string" ? data.git_sha.trim() : "";
  const hasSha = sha.length > 0 && sha.toLowerCase() !== "unknown";
  if (!version) return null;
  return `${version}${hasSha ? ` • ${sha.slice(0, 7)}` : ""}`;
}

export default function SystemStatus() {
  const [isHealthy, setIsHealthy] = useState<boolean>(true);
  const [errorDetails, setErrorDetails] = useState<string | null>(null);
  const [versionInfo, setVersionInfo] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;

    const checkHealth = async () => {
      try {
        const res = await fetchWithAuth("/health/ready");
        if (!mounted) return;

        if (res.ok) {
          const data = (await res.json().catch(() => ({}))) as Record<string, unknown>;
          setVersionInfo(healthVersionInfo(data));
          setIsHealthy(true);
          setErrorDetails(null);
          return;
        }

        const data = (await res.json().catch(() => ({}))) as Record<string, unknown>;
        setVersionInfo(healthVersionInfo(data));
        setIsHealthy(false);
        const errorPayload =
          data.error && typeof data.error === "object"
            ? (data.error as Record<string, unknown>)
            : null;
        setErrorDetails(
          typeof errorPayload?.message === "string"
            ? errorPayload.message
            : `HTTP ${res.status} Error`,
        );
      } catch (error: unknown) {
        if (!mounted) return;
        const message = error instanceof Error ? error.message : "Network Error";
        setIsHealthy(false);
        setErrorDetails(message);
      }
    };

    checkHealth();

    return () => {
      mounted = false;
    };
  }, []);

  useVisibilityAwareInterval(() => {
    void fetchWithAuth("/health/ready")
      .then((res) => {
        if (res.ok) {
          res
            .json()
            .catch(() => ({}))
            .then((data: Record<string, unknown>) => {
              setVersionInfo(healthVersionInfo(data));
            });
          setIsHealthy(true);
          setErrorDetails(null);
          return;
        }

        return res
          .json()
          .catch(() => ({}))
          .then((data) => {
            setIsHealthy(false);
            const errorPayload =
              data.error && typeof data.error === "object"
                ? (data.error as Record<string, unknown>)
                : null;
            setErrorDetails(
              typeof errorPayload?.message === "string"
                ? errorPayload.message
                : `HTTP ${res.status} Error`,
            );
          });
      })
      .catch((error: unknown) => {
        const message = error instanceof Error ? error.message : "Network Error";
        setIsHealthy(false);
        setErrorDetails(message);
      });
  }, 30000);

  const label = isHealthy
    ? "System operational"
    : `System degraded: ${errorDetails ?? "unknown issue"}`;

  const tooltip = versionInfo
    ? `${isHealthy ? "System Operational" : "System Degraded"} • ${versionInfo}`
    : isHealthy
      ? "System Operational"
      : "System Degraded";

  return (
    <div
      className="ui-tooltip bg-muted border-glass-border relative inline-flex h-9 w-9 cursor-help items-center justify-center rounded-xl border"
      data-tooltip={tooltip}
      aria-label={`${label}${versionInfo ? ` • ${versionInfo}` : ""}`}
      role="status"
      tabIndex={0}
    >
      <Activity size={16} className={isHealthy ? "text-green-500" : "text-red-500"} />
      <span className="absolute top-1 right-1 flex h-2 w-2">
        <span
          className={`absolute inline-flex h-full w-full animate-ping rounded-full opacity-75 ${isHealthy ? "bg-green-400" : "bg-red-400"}`}
        />
        <span
          className={`relative inline-flex h-2 w-2 rounded-full ${isHealthy ? "bg-green-500" : "bg-red-500"}`}
        />
      </span>
    </div>
  );
}
