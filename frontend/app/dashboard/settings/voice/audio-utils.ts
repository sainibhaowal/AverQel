const MIN_SAMPLE_SECONDS = 1;
const MAX_SAMPLE_SECONDS = 30;

export async function convertVoiceSampleToWav(blob: Blob): Promise<Blob> {
  const context = new AudioContext();
  try {
    const decoded = await context.decodeAudioData(await blob.arrayBuffer());
    if (decoded.duration < MIN_SAMPLE_SECONDS || decoded.duration > MAX_SAMPLE_SECONDS) {
      throw new Error("Voice samples must be between 1 and 30 seconds long.");
    }

    const sampleRate = decoded.sampleRate;
    const sampleCount = decoded.length;
    const bytes = new ArrayBuffer(44 + sampleCount * 2);
    const view = new DataView(bytes);
    const writeText = (offset: number, value: string) => {
      for (let index = 0; index < value.length; index += 1) {
        view.setUint8(offset + index, value.charCodeAt(index));
      }
    };

    writeText(0, "RIFF");
    view.setUint32(4, 36 + sampleCount * 2, true);
    writeText(8, "WAVE");
    writeText(12, "fmt ");
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, 1, true);
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * 2, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    writeText(36, "data");
    view.setUint32(40, sampleCount * 2, true);

    const channels = Array.from({ length: decoded.numberOfChannels }, (_, index) =>
      decoded.getChannelData(index),
    );
    for (let index = 0; index < sampleCount; index += 1) {
      const mixedSample =
        channels.reduce((total, channel) => total + channel[index], 0) / channels.length;
      const sample = Math.max(-1, Math.min(1, mixedSample));
      view.setInt16(44 + index * 2, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true);
    }

    return new Blob([bytes], { type: "audio/wav" });
  } finally {
    await context.close();
  }
}
