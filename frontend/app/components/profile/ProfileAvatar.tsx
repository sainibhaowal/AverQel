"use client";

import { useState } from "react";

interface ProfileAvatarProps {
  avatar?: string | null;
  displayName?: string | null;
  fallbackLabel?: string | null;
  className?: string;
}

function safeAvatarSource(value: string | null | undefined): string | null {
  const source = value?.trim();
  if (!source) return null;
  if (source.startsWith("data:image/")) return source;

  try {
    const parsed = new URL(source);
    return parsed.protocol === "https:" ? source : null;
  } catch {
    return null;
  }
}

function getInitials(label: string): string {
  const parts = label
    .trim()
    .split(/[\s.@_-]+/)
    .filter(Boolean);
  return (
    parts
      .slice(0, 2)
      .map((part) => part[0]?.toUpperCase() ?? "")
      .join("") || "U"
  );
}

export default function ProfileAvatar({
  avatar,
  displayName,
  fallbackLabel,
  className = "h-10 w-10 rounded-full",
}: ProfileAvatarProps) {
  const source = safeAvatarSource(avatar);
  const [failedSource, setFailedSource] = useState<string | null>(null);
  const identity = displayName?.trim() || fallbackLabel?.trim() || "User";

  return (
    <span
      aria-hidden="true"
      className={`text-foreground relative inline-flex shrink-0 items-center justify-center overflow-hidden font-semibold ${className}`}
    >
      {source && source !== failedSource ? (
        // Profile URLs and image data are validated by the profile API.
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={source}
          alt=""
          referrerPolicy="no-referrer"
          className="absolute inset-0 h-full w-full object-cover"
          onError={() => setFailedSource(source)}
        />
      ) : (
        <span className="text-[0.72em] leading-none">{getInitials(identity)}</span>
      )}
    </span>
  );
}
