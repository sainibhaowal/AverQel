"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import {
  Mic,
  Play,
  Square,
  Upload,
  Sliders,
  Check,
  Loader2,
  Trash2,
  Headphones,
} from "lucide-react";

import { fetchWithAuth } from "@/lib/api";
import DashboardSectionHeader from "@/app/components/ui/DashboardSectionHeader";
import RoundedSelect from "@/app/components/ui/RoundedSelect";
import { convertVoiceSampleToWav } from "./audio-utils";

const VOICES = [
  { id: "alba", name: "Alba", desc: "Warm, natural female", lang: "en" },
  { id: "cosette", name: "Cosette", desc: "Soft, gentle female", lang: "en" },
  { id: "jean", name: "Jean", desc: "Clear male", lang: "en" },
  { id: "marius", name: "Marius", desc: "Deep male", lang: "en" },
  { id: "javert", name: "Javert", desc: "Authoritative male", lang: "en" },
  { id: "anna", name: "Anna", desc: "Bright female", lang: "en" },
  { id: "vera", name: "Vera", desc: "Calm female", lang: "en" },
  { id: "fantine", name: "Fantine", desc: "Expressive female", lang: "en" },
  { id: "charles", name: "Charles", desc: "Professional male", lang: "en" },
  { id: "paul", name: "Paul", desc: "Casual male", lang: "en" },
  { id: "eponine", name: "Eponine", desc: "Young female", lang: "en" },
  { id: "azelma", name: "Azelma", desc: "Soft young female", lang: "en" },
  { id: "george", name: "George", desc: "Mature male", lang: "en" },
  { id: "mary", name: "Mary", desc: "Warm mature female", lang: "en" },
  { id: "jane", name: "Jane", desc: "Friendly female", lang: "en" },
  { id: "michael", name: "Michael", desc: "Friendly male", lang: "en" },
  { id: "eve", name: "Eve", desc: "Bright young female", lang: "en" },
  { id: "bill_boerst", name: "Bill Boerst", desc: "American male", lang: "en" },
  { id: "peter_yearsley", name: "Peter Yearsley", desc: "British male", lang: "en" },
  { id: "stuart_bell", name: "Stuart Bell", desc: "Scottish male", lang: "en" },
  { id: "caro_davy", name: "Caro Davy", desc: "Australian female", lang: "en" },
];

type VoiceSettings = {
  voice: string;
  speed: number;
  pitch: number;
  volume: number;
  clonedVoiceId: string | null;
  clonedVoiceName: string | null;
};

const DEFAULT_SETTINGS: VoiceSettings = {
  voice: "alba",
  speed: 1.0,
  pitch: 1.0,
  volume: 1.0,
  clonedVoiceId: null,
  clonedVoiceName: null,
};

export default function VoiceSettingsPage() {
  const [settings, setSettings] = useState<VoiceSettings>(DEFAULT_SETTINGS);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [cloning, setCloning] = useState(false);
  const [recordedBlob, setRecordedBlob] = useState<Blob | null>(null);
  const [recording, setRecording] = useState(false);
  const [mediaRecorder, setMediaRecorder] = useState<MediaRecorder | null>(null);
  const [testAudioUrl, setTestAudioUrl] = useState<string | null>(null);
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  // Load settings
  useEffect(() => {
    const load = async () => {
      try {
        const res = await fetchWithAuth("/deepspace/voice/settings");
        if (res.ok) {
          const data = await res.json();
          setSettings({ ...DEFAULT_SETTINGS, ...data });
        }
      } catch {
        // Use defaults
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, []);

  useEffect(
    () => () => {
      if (testAudioUrl) URL.revokeObjectURL(testAudioUrl);
    },
    [testAudioUrl],
  );

  // Save settings
  const saveSettings = useCallback(async () => {
    setSaving(true);
    setMessage(null);
    try {
      const res = await fetchWithAuth("/deepspace/voice/settings", {
        method: "PUT",
        body: JSON.stringify(settings),
      });
      if (res.ok) {
        setMessage({ type: "success", text: "Voice settings saved successfully." });
      } else {
        const err = await res.json().catch(() => null);
        setMessage({ type: "error", text: err?.detail?.message ?? "Failed to save settings." });
      }
    } catch {
      setMessage({ type: "error", text: "Network error. Please try again." });
    } finally {
      setSaving(false);
    }
  }, [settings]);

  // Test voice
  const testVoice = useCallback(async () => {
    setTesting(true);
    setMessage(null);
    setTestAudioUrl(null);
    try {
      const res = await fetchWithAuth("/deepspace/voice/test", {
        method: "POST",
        timeoutMs: 120_000,
        body: JSON.stringify({
          text: "Hello.",
          voice: settings.voice,
          speed: settings.speed,
          pitch: settings.pitch,
          volume: settings.volume,
        }),
      });
      if (res.ok) {
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        setTestAudioUrl(url);
      } else {
        const err = await res.json().catch(() => null);
        setMessage({ type: "error", text: err?.error?.message ?? err?.detail?.message ?? "Voice test failed." });
      }
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : "Network error. Please try again.";
      setMessage({ type: "error", text: errMsg });
    } finally {
      setTesting(false);
    }
  }, [settings]);

  // Start recording
  const startRecording = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = ["audio/ogg;codecs=opus", "audio/webm;codecs=opus", "audio/mp4"].find(
        (candidate) => MediaRecorder.isTypeSupported(candidate),
      );
      const recorder = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream);
      const chunks: Blob[] = [];
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunks.push(e.data);
      };
      recorder.onstop = () => {
        const blob = new Blob(chunks, { type: recorder.mimeType || "application/octet-stream" });
        setRecordedBlob(blob);
        stream.getTracks().forEach((t) => t.stop());
      };
      recorder.start();
      setMediaRecorder(recorder);
      setRecording(true);
      setRecordedBlob(null);
    } catch {
      setMessage({ type: "error", text: "Microphone access denied. Please allow microphone access." });
    }
  }, []);

  // Stop recording
  const stopRecording = useCallback(() => {
    if (mediaRecorder && mediaRecorder.state !== "inactive") {
      mediaRecorder.stop();
    }
    setRecording(false);
    setMediaRecorder(null);
  }, [mediaRecorder]);

  // Clone voice
  const cloneVoice = useCallback(async () => {
    if (!recordedBlob) return;
    setCloning(true);
    setMessage(null);
    try {
      const formData = new FormData();
      const wavSample = await convertVoiceSampleToWav(recordedBlob);
      formData.append("audio", wavSample, "voice_sample.wav");
      formData.append("name", `Cloned Voice ${new Date().toLocaleDateString()}`);
      const res = await fetchWithAuth("/deepspace/voice/clone", {
        method: "POST",
        body: formData,
      });
      if (res.ok) {
        const data = await res.json();
        setSettings((prev) => ({
          ...prev,
          clonedVoiceId: data.voice_id,
          clonedVoiceName: data.name,
          voice: `clone:${data.voice_id}`,
        }));
        setMessage({ type: "success", text: "Voice cloned successfully! Select it from the voice list." });
        setRecordedBlob(null);
      } else {
        const err = await res.json().catch(() => null);
        setMessage({ type: "error", text: err?.detail?.message ?? "Voice cloning failed." });
      }
    } catch (error) {
      setMessage({
        type: "error",
        text: error instanceof Error ? error.message : "Network error. Please try again.",
      });
    } finally {
      setCloning(false);
    }
  }, [recordedBlob]);

  // Delete cloned voice
  const deleteClonedVoice = useCallback(async () => {
    if (!settings.clonedVoiceId) return;
    try {
      const res = await fetchWithAuth(`/deepspace/voice/clone/${settings.clonedVoiceId}`, {
        method: "DELETE",
      });
      if (res.ok) {
        setSettings((prev) => ({
          ...prev,
          clonedVoiceId: null,
          clonedVoiceName: null,
          voice: "alba",
        }));
        setMessage({ type: "success", text: "Cloned voice deleted." });
      }
    } catch {
      setMessage({ type: "error", text: "Failed to delete cloned voice." });
    }
  }, [settings.clonedVoiceId]);

  // Upload audio file
  const handleFileUpload = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setRecordedBlob(file);
    }
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <div className="w-full space-y-6">
      <DashboardSectionHeader
        title="Voice Studio"
        subtitle="Configure TTS Voice, Cloning, and Playback Settings"
        icon={Mic}
        accentClassName="bg-violet-500 text-violet-500"
        accentGlowClassName="shadow-[0_0_20px_rgba(139,92,246,0.4)]"
        backHref="/dashboard/settings"
        backLabel="Back To Settings"
      />

      {message && (
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          className={`rounded-xl border px-4 py-3 text-sm font-medium ${
            message.type === "success"
              ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
              : "border-rose-500/30 bg-rose-500/10 text-rose-700 dark:text-rose-300"
          }`}
        >
          {message.text}
        </motion.div>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Voice Selection Card */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="rounded-2xl border border-border bg-surface-1 p-6 shadow-sm"
        >
          <div className="mb-4 flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-violet-500/10 text-violet-500">
              <Headphones size={20} />
            </div>
            <div>
              <h3 className="text-lg font-bold text-foreground">Voice Selection</h3>
              <p className="text-xs text-muted-foreground">Choose your TTS voice</p>
            </div>
          </div>

          <div className="space-y-3">
            <label className="text-sm font-medium text-foreground">Built-in Voices</label>
            <RoundedSelect
              label="Built-in voices"
              value={settings.voice.startsWith("clone:") ? "" : settings.voice}
              onChange={(voice) => setSettings((prev) => ({ ...prev, voice }))}
              options={VOICES.map((voice) => ({
                value: voice.id,
                label: voice.name,
                description: voice.desc,
              }))}
              matchTriggerWidth
              showSelectionCheck
              menuMaxHeight={420}
              estimatedOptionHeight={50}
              triggerClassName="min-h-12 w-full !rounded-xl border-border bg-surface-2 px-4 text-sm font-medium focus-visible:outline-violet-500"
              menuClassName="border-border !rounded-2xl"
              optionClassName="min-h-12 !rounded-xl px-4 text-sm leading-5"
            />

            {settings.clonedVoiceId && (
              <div className="mt-3">
                <label className="text-sm font-medium text-foreground">Cloned Voice</label>
                <div className="mt-1 flex items-center justify-between rounded-xl border border-emerald-500/30 bg-emerald-500/5 px-4 py-3">
                  <div className="flex items-center gap-2">
                    <Check size={16} className="text-emerald-500" />
                    <span className="text-sm font-medium text-foreground">{settings.clonedVoiceName}</span>
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={() => setSettings((prev) => ({ ...prev, voice: `clone:${prev.clonedVoiceId}` }))}
                      className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
                        settings.voice.startsWith("clone:")
                          ? "bg-emerald-500 text-white"
                          : "bg-surface-2 text-foreground hover:bg-emerald-500/20"
                      }`}
                    >
                      {settings.voice.startsWith("clone:") ? "Active" : "Use"}
                    </button>
                    <button
                      onClick={deleteClonedVoice}
                      className="rounded-lg bg-rose-500/10 px-3 py-1.5 text-xs font-semibold text-rose-600 transition hover:bg-rose-500/20"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        </motion.div>

        {/* Voice Playback Settings Card */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
          className="rounded-2xl border border-border bg-surface-1 p-6 shadow-sm"
        >
          <div className="mb-4 flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-cyan-500/10 text-cyan-500">
              <Sliders size={20} />
            </div>
            <div>
              <h3 className="text-lg font-bold text-foreground">Playback Settings</h3>
              <p className="text-xs text-muted-foreground">Preview speed and volume</p>
            </div>
          </div>

          <div className="space-y-5">
            {/* Speed */}
            <div>
              <div className="mb-2 flex items-center justify-between">
                <label className="text-sm font-medium text-foreground">Speed</label>
                <span className="text-xs font-mono text-muted-foreground">{settings.speed.toFixed(1)}x</span>
              </div>
              <input
                type="range"
                min="0.5"
                max="2.0"
                step="0.1"
                value={settings.speed}
                onChange={(e) => setSettings((prev) => ({ ...prev, speed: parseFloat(e.target.value) }))}
                className="w-full accent-violet-500"
              />
              <div className="mt-1 flex justify-between text-[10px] text-muted-foreground">
                <span>0.5x</span>
                <span>1.0x</span>
                <span>2.0x</span>
              </div>
            </div>

            <p className="rounded-xl border border-border bg-surface-2 px-4 py-3 text-xs text-muted-foreground">
              Pitch adjustment is not supported by the current voice engine.
            </p>

            {/* Volume */}
            <div>
              <div className="mb-2 flex items-center justify-between">
                <label className="text-sm font-medium text-foreground">Volume</label>
                <span className="text-xs font-mono text-muted-foreground">{Math.round(settings.volume * 100)}%</span>
              </div>
              <input
                type="range"
                min="0"
                max="1"
                step="0.05"
                value={settings.volume}
                onChange={(e) => setSettings((prev) => ({ ...prev, volume: parseFloat(e.target.value) }))}
                className="w-full accent-violet-500"
              />
              <div className="mt-1 flex justify-between text-[10px] text-muted-foreground">
                <span>0%</span>
                <span>50%</span>
                <span>100%</span>
              </div>
            </div>
          </div>
        </motion.div>

        {/* Voice Cloning Card */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="rounded-2xl border border-border bg-surface-1 p-6 shadow-sm"
        >
          <div className="mb-4 flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-500/10 text-emerald-500">
              <Mic size={20} />
            </div>
            <div>
              <h3 className="text-lg font-bold text-foreground">Voice Cloning</h3>
              <p className="text-xs text-muted-foreground">Record or upload a 5-10s voice sample</p>
            </div>
          </div>

          <div className="space-y-4">
            {/* Recording controls */}
            <div className="flex flex-wrap gap-3">
              {!recording ? (
                <button
                  onClick={startRecording}
                  className="flex items-center gap-2 rounded-xl bg-rose-500/10 px-4 py-2.5 text-sm font-semibold text-rose-600 transition hover:bg-rose-500/20"
                >
                  <Mic size={16} />
                  Record Voice
                </button>
              ) : (
                <button
                  onClick={stopRecording}
                  className="flex items-center gap-2 rounded-xl bg-rose-500 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-rose-600"
                >
                  <Square size={16} />
                  Stop Recording
                </button>
              )}
              <button
                onClick={() => fileInputRef.current?.click()}
                className="flex items-center gap-2 rounded-xl bg-surface-2 px-4 py-2.5 text-sm font-semibold text-foreground transition hover:bg-surface-3"
              >
                <Upload size={16} />
                Upload Audio
              </button>
              <input
                ref={fileInputRef}
                type="file"
                accept="audio/*"
                onChange={handleFileUpload}
                className="hidden"
              />
            </div>

            {recording && (
              <div className="flex items-center gap-2 rounded-xl border border-rose-500/30 bg-rose-500/5 px-4 py-3">
                <div className="h-3 w-3 animate-pulse rounded-full bg-rose-500" />
                <span className="text-sm font-medium text-rose-600">Recording... Click Stop when done.</span>
              </div>
            )}

            {recordedBlob && (
              <div className="space-y-3">
                <div className="flex items-center gap-2 rounded-xl border border-emerald-500/30 bg-emerald-500/5 px-4 py-3">
                  <Check size={16} className="text-emerald-500" />
                  <span className="text-sm font-medium text-foreground">
                    Audio ready ({Math.round(recordedBlob.size / 1024)}KB)
                  </span>
                </div>
                <div className="flex gap-3">
                  <button
                    onClick={cloneVoice}
                    disabled={cloning}
                    className="flex items-center gap-2 rounded-xl bg-emerald-500 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-emerald-600 disabled:opacity-50"
                  >
                    {cloning ? <Loader2 size={16} className="animate-spin" /> : <Mic size={16} />}
                    {cloning ? "Cloning..." : "Clone Voice"}
                  </button>
                  <button
                    onClick={() => setRecordedBlob(null)}
                    className="flex items-center gap-2 rounded-xl bg-surface-2 px-4 py-2.5 text-sm font-semibold text-foreground transition hover:bg-surface-3"
                  >
                    <Trash2 size={16} />
                    Discard
                  </button>
                </div>
              </div>
            )}

            <p className="text-xs text-muted-foreground">
              Record 5 to 10 seconds of clear speech in a quiet environment. Samples must be WAV
              audio between 1 and 30 seconds and under 10 MB. Only upload a voice sample you own or
              have permission to use. Cloned voices are available for preview and are not used in
              realtime conversations.
            </p>
          </div>
        </motion.div>

        {/* Test Voice Card */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.25 }}
          className="rounded-2xl border border-border bg-surface-1 p-6 shadow-sm lg:col-span-2"
        >
          <div className="mb-4 flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-amber-500/10 text-amber-500">
              <Play size={20} />
            </div>
            <div>
              <h3 className="text-lg font-bold text-foreground">Test Voice</h3>
              <p className="text-xs text-muted-foreground">Preview how your voice settings sound</p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-4">
            <button
              onClick={testVoice}
              disabled={testing}
              className="flex items-center gap-2 rounded-xl bg-amber-500 px-6 py-3 text-sm font-semibold text-white transition hover:bg-amber-600 disabled:opacity-50"
            >
              {testing ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}
              {testing ? "Preparing preview..." : "Play Test Sound"}
            </button>
          </div>
          <p className="text-muted-foreground mt-3 text-xs">
            The first preview may take longer while the speech model loads. After generation, use
            the audio controls if your browser blocks automatic playback.
          </p>
          {testAudioUrl && (
            <audio
              key={testAudioUrl}
              controls
              aria-label="Voice preview audio"
              className="mt-4 h-10 w-full"
              src={testAudioUrl}
              onCanPlay={(event) => {
                const audio = event.currentTarget;
                if (audio.dataset.playAttempted) return;
                audio.dataset.playAttempted = "true";
                void audio.play().catch(() => {
                  // Browser autoplay can be blocked after the network request.
                  // Keep the native controls available as the reliable fallback.
                  setMessage({
                    type: "success",
                    text: "Preview ready. Press play if it did not start.",
                  });
                });
              }}
              onError={() =>
                setMessage({ type: "error", text: "The preview audio could not be played." })
              }
            />
          )}
        </motion.div>

        {/* Save Button */}
        <div className="flex justify-end lg:col-span-2">
          <button
            onClick={saveSettings}
            disabled={saving}
            className="flex items-center gap-2 rounded-xl bg-violet-500 px-8 py-3 text-sm font-semibold text-white transition hover:bg-violet-600 disabled:opacity-50"
          >
            {saving ? <Loader2 size={16} className="animate-spin" /> : <Check size={16} />}
            {saving ? "Saving..." : "Save Voice Settings"}
          </button>
        </div>
      </div>
    </div>
  );
}
