import { afterEach, describe, expect, it, vi } from "vitest";

import { convertVoiceSampleToWav } from "../app/dashboard/settings/voice/audio-utils";

function createAudioBlob(): Blob {
  const blob = new Blob(["sample"], { type: "audio/webm" });
  Object.defineProperty(blob, "arrayBuffer", {
    value: vi.fn().mockResolvedValue(new ArrayBuffer(1)),
  });
  return blob;
}

function readBlob(blob: Blob): Promise<ArrayBuffer> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as ArrayBuffer);
    reader.onerror = () => reject(reader.error);
    reader.readAsArrayBuffer(blob);
  });
}

describe("convertVoiceSampleToWav", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("creates mono PCM WAV data from decoded browser audio", async () => {
    const close = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal(
      "AudioContext",
      class {
        decodeAudioData = vi.fn().mockResolvedValue({
          duration: 1,
          sampleRate: 24_000,
          length: 2,
          numberOfChannels: 2,
          getChannelData: (channel: number) =>
            channel === 0 ? new Float32Array([0.5, -0.5]) : new Float32Array([0.5, -0.5]),
        });
        close = close;
      },
    );

    const wav = await convertVoiceSampleToWav(createAudioBlob());
    const view = new DataView(await readBlob(wav));

    expect(wav.type).toBe("audio/wav");
    expect(view.getUint8(0)).toBe("R".charCodeAt(0));
    expect(view.getUint8(8)).toBe("W".charCodeAt(0));
    expect(view.getUint16(22, true)).toBe(1);
    expect(view.getUint32(24, true)).toBe(24_000);
    expect(view.getInt16(44, true)).toBeGreaterThan(0);
    expect(view.getInt16(46, true)).toBeLessThan(0);
    expect(close).toHaveBeenCalledOnce();
  });

  it("rejects samples outside the supported duration", async () => {
    vi.stubGlobal(
      "AudioContext",
      class {
        decodeAudioData = vi.fn().mockResolvedValue({ duration: 31 });
        close = vi.fn().mockResolvedValue(undefined);
      },
    );

    await expect(convertVoiceSampleToWav(createAudioBlob())).rejects.toThrow(
      "between 1 and 30 seconds",
    );
  });
});
