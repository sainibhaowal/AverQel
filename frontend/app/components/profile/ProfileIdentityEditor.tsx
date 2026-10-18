"use client";

import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { Check, ImagePlus, LoaderCircle, Upload, UserRound } from "lucide-react";
import { PROFILE_AVATAR_PRESETS } from "@/lib/profile-avatars";

export type ProfileIdentityDraft = {
  display_name: string | null;
  avatar?: string | null;
};

type Props = {
  displayName?: string | null;
  avatar?: string | null;
  onSave: (draft: ProfileIdentityDraft) => Promise<void>;
  submitLabel?: string;
  onSaved?: () => void;
};

const MAX_PHOTO_SIZE = 8 * 1024 * 1024;
const ALLOWED_PHOTO_TYPES = new Set(["image/jpeg", "image/png", "image/webp", "image/avif"]);

async function makeCroppedPhoto(file: File, zoom: number): Promise<string> {
  let image: CanvasImageSource & { width: number; height: number };
  let disposeImage: () => void;
  if (typeof createImageBitmap === "function") {
    const bitmap = await createImageBitmap(file);
    image = bitmap;
    disposeImage = () => bitmap.close();
  } else {
    const objectUrl = URL.createObjectURL(file);
    const fallbackImage = new Image();
    fallbackImage.src = objectUrl;
    try {
      await fallbackImage.decode();
    } catch {
      URL.revokeObjectURL(objectUrl);
      throw new Error("This browser could not open the profile photo.");
    }
    image = fallbackImage;
    disposeImage = () => URL.revokeObjectURL(objectUrl);
  }
  try {
    const canvas = document.createElement("canvas");
    canvas.width = 256;
    canvas.height = 256;
    const context = canvas.getContext("2d");
    if (!context) throw new Error("This browser could not prepare the profile photo.");

    const shortestSide = Math.min(image.width, image.height);
    const cropSize = shortestSide / zoom;
    const sourceX = (image.width - cropSize) / 2;
    const sourceY = (image.height - cropSize) / 2;
    context.drawImage(image, sourceX, sourceY, cropSize, cropSize, 0, 0, 256, 256);

    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, "image/jpeg", 0.82),
    );
    if (!blob) throw new Error("This browser could not prepare the profile photo.");

    return await new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () =>
        typeof reader.result === "string"
          ? resolve(reader.result)
          : reject(new Error("The profile photo could not be read."));
      reader.onerror = () => reject(new Error("The profile photo could not be read."));
      reader.readAsDataURL(blob);
    });
  } finally {
    disposeImage();
  }
}

export default function ProfileIdentityEditor({
  displayName,
  avatar,
  onSave,
  submitLabel = "Save profile",
  onSaved,
}: Props) {
  const [name, setName] = useState(displayName ?? "");
  const [selectedAvatar, setSelectedAvatar] = useState(avatar ?? null);
  const [avatarChanged, setAvatarChanged] = useState(false);
  const [photo, setPhoto] = useState<File | null>(null);
  const [photoUrl, setPhotoUrl] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const editorId = useId().replace(/:/g, "");
  const displayNameId = `profile-display-name-${editorId}`;
  const displayNameHelpId = `profile-display-name-help-${editorId}`;
  const photoUploadId = `profile-photo-upload-${editorId}`;

  useEffect(() => {
    if (!photoUrl) return;
    return () => URL.revokeObjectURL(photoUrl);
  }, [photoUrl]);

  const avatarPreview = photoUrl || selectedAvatar;

  const handlePhoto = (file: File | undefined) => {
    if (!file) return;
    if (!ALLOWED_PHOTO_TYPES.has(file.type)) {
      setError("Choose a JPEG, PNG, WebP, or AVIF photo.");
      return;
    }
    if (file.size > MAX_PHOTO_SIZE) {
      setError("Choose a photo smaller than 8 MB.");
      return;
    }
    setError("");
    setPhoto(file);
    setPhotoUrl(URL.createObjectURL(file));
    setSelectedAvatar(null);
    setAvatarChanged(true);
    setZoom(1);
  };

  const choosePreset = (src: string) => {
    setPhoto(null);
    setPhotoUrl(null);
    setSelectedAvatar(src);
    setAvatarChanged(true);
    setZoom(1);
    setError("");
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      const nextAvatar = photo ? await makeCroppedPhoto(photo, zoom) : selectedAvatar;
      const draft: ProfileIdentityDraft = {
        display_name: name.trim() || null,
      };
      if (avatarChanged) draft.avatar = nextAvatar;
      await onSave(draft);
      onSaved?.();
    } catch (saveError) {
      setError(
        saveError instanceof Error ? saveError.message : "Profile changes could not be saved.",
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={submit} className="space-y-5">
      <div className="block space-y-2">
        <label htmlFor={displayNameId} className="text-foreground text-sm font-medium">
          Display name
        </label>
        <input
          id={displayNameId}
          value={name}
          onChange={(event) => setName(event.target.value.slice(0, 48))}
          maxLength={48}
          autoComplete="nickname"
          placeholder="How should AverQel address you?"
          className="theme-input h-11 w-full rounded-xl border px-3 text-sm"
          aria-describedby={displayNameHelpId}
        />
        <span id={displayNameHelpId} className="text-muted-foreground block text-xs">
          Your email and account role stay unchanged.
        </span>
      </div>

      <div className="grid gap-5 sm:grid-cols-[116px_minmax(0,1fr)] sm:items-center">
        <div className="flex justify-center sm:justify-start">
          <div className="border-glass-border bg-muted flex h-24 w-24 items-center justify-center overflow-hidden rounded-full border-2 shadow-inner">
            {avatarPreview ? (
              // User avatars include saved image data or trusted provider profile URLs.
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={avatarPreview}
                alt="Profile avatar preview"
                className="h-full w-full object-cover"
              />
            ) : (
              <UserRound className="text-muted-foreground" size={32} aria-hidden="true" />
            )}
          </div>
        </div>
        <div className="space-y-3">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-foreground text-sm font-medium">Choose an avatar</p>
              <p className="text-muted-foreground mt-1 text-xs">12 calm, colorful designs</p>
            </div>
            {photo ? (
              <span className="text-primary inline-flex items-center gap-1 text-xs">
                <Check size={13} /> Photo selected
              </span>
            ) : null}
          </div>
          <div className="flex flex-wrap gap-2" role="group" aria-label="Preset profile avatars">
            {PROFILE_AVATAR_PRESETS.map((preset) => (
              <button
                key={preset.id}
                type="button"
                aria-label={`${preset.label} avatar`}
                aria-pressed={!photo && selectedAvatar === preset.src}
                onClick={() => choosePreset(preset.src)}
                className={`focus-visible:ring-primary h-10 w-10 overflow-hidden rounded-full border-2 transition hover:-translate-y-0.5 focus-visible:ring-2 ${selectedAvatar === preset.src && !photo ? "border-primary shadow-[0_0_0_3px_rgba(45,212,191,.16)]" : "border-glass-border"}`}
              >
                {/* Static, locally generated avatar artwork. */}
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={preset.src} alt="" className="h-full w-full object-cover" />
              </button>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <input
              ref={fileInputRef}
              id={photoUploadId}
              type="file"
              accept="image/jpeg,image/png,image/webp,image/avif"
              className="sr-only"
              onChange={(event) => handlePhoto(event.currentTarget.files?.[0])}
            />
            <label
              htmlFor={photoUploadId}
              className="theme-chip inline-flex h-9 cursor-pointer items-center gap-2 rounded-lg px-3 text-xs font-medium"
            >
              <ImagePlus size={14} /> Upload photo
            </label>
            {photo ? (
              <label className="text-muted-foreground flex min-w-[150px] flex-1 items-center gap-2 text-xs">
                Crop
                <input
                  type="range"
                  min="1"
                  max="2.5"
                  step="0.05"
                  value={zoom}
                  onChange={(event) => setZoom(Number(event.target.value))}
                  aria-label="Zoom profile photo crop"
                  className="accent-primary w-full"
                />
              </label>
            ) : null}
          </div>
        </div>
      </div>

      {error ? (
        <p
          role="alert"
          className="rounded-lg border border-red-400/20 bg-red-400/5 px-3 py-2 text-sm text-red-300"
        >
          {error}
        </p>
      ) : null}

      <div className="flex justify-end">
        <button
          type="submit"
          disabled={saving}
          className="bg-primary text-primary-foreground inline-flex h-10 items-center justify-center gap-2 rounded-xl px-4 text-sm font-semibold transition hover:brightness-110 disabled:cursor-wait disabled:opacity-60"
        >
          {saving ? <LoaderCircle size={15} className="animate-spin" /> : <Upload size={14} />}
          {saving ? "Saving…" : submitLabel}
        </button>
      </div>
    </form>
  );
}
