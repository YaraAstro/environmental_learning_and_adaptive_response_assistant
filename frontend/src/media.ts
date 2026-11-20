import type { Attachment, Media, Model } from "./types";

const MAX_SECONDS = 30;
function base64(bytes: Uint8Array): string {
  let value = "";
  for (let i = 0; i < bytes.length; i += 8192)
    value += String.fromCharCode(...bytes.subarray(i, i + 8192));
  return btoa(value);
}
function filename(value: string): string {
  return value
    .replace(/[\\/\x00-\x1f]/g, "_")
    .replace(/^\.+/, "_")
    .slice(0, 220);
}
function duration(seconds: number) {
  if (!Number.isFinite(seconds) || seconds <= 0 || seconds > MAX_SECONDS)
    throw new Error(
      "Choose an audio or video clip up to 30 seconds. Trim longer clips first.",
    );
}
function frame(
  source: CanvasImageSource,
  width: number,
  height: number,
): string {
  if (!width || !height || width * height > 80_000_000)
    throw new Error("This image is too large or could not be decoded.");
  const scale = Math.min(1, 1536 / Math.max(width, height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.round(width * scale));
  canvas.height = Math.max(1, Math.round(height * scale));
  const context = canvas.getContext("2d");
  if (!context)
    throw new Error("Image preparation is unavailable in this browser.");
  context.fillStyle = "#ffffff";
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.drawImage(source, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL("image/jpeg", 0.86).split(",")[1];
}
function mediaEvent(
  element: HTMLMediaElement,
  event: string,
  action: () => void,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const cleanup = () => {
      clearTimeout(timer);
      element.removeEventListener(event, done);
      element.removeEventListener("error", fail);
    };
    const done = () => {
      cleanup();
      resolve();
    };
    const fail = () => {
      cleanup();
      reject(
        new Error(
          "This browser cannot decode the media. Try a common WAV, MP3, MP4, or WebM format.",
        ),
      );
    };
    const timer = setTimeout(fail, 15000);
    element.addEventListener(event, done, { once: true });
    element.addEventListener("error", fail, { once: true });
    action();
  });
}

async function audioPart(
  file: File,
  source: "audio" | "video_audio",
): Promise<Media> {
  // Read duration before allocating a decoded buffer for a potentially long file.
  // Video duration has already been checked by the frame sampler.
  if (source === "audio") {
    const probe = document.createElement("audio");
    const url = URL.createObjectURL(file);
    probe.preload = "metadata";
    try {
      await mediaEvent(probe, "loadedmetadata", () => {
        probe.src = url;
        probe.load();
      });
      duration(probe.duration);
    } finally {
      probe.removeAttribute("src");
      probe.load();
      URL.revokeObjectURL(url);
    }
  }
  const decoder = new OfflineAudioContext(1, 1, 16000);
  let decoded: AudioBuffer;
  try {
    decoded = await decoder.decodeAudioData(await file.arrayBuffer());
  } catch {
    throw new Error(
      source === "video_audio"
        ? "The soundtrack could not be decoded. Turn off “Include video sound” and attach the clip again for frames only."
        : "This browser cannot decode that audio. Try WAV, MP3, or a supported M4A file.",
    );
  }
  duration(decoded.duration);
  const count = Math.min(480000, Math.ceil(decoded.duration * 16000));
  const renderer = new OfflineAudioContext(1, count, 16000);
  const input = renderer.createBufferSource();
  input.buffer = decoded;
  input.connect(renderer.destination);
  input.start();
  const samples = (await renderer.startRendering()).getChannelData(0);
  const bytes = new Uint8Array(44 + samples.length * 2),
    view = new DataView(bytes.buffer);
  const write = (offset: number, text: string) =>
    [...text].forEach((char, i) =>
      view.setUint8(offset + i, char.charCodeAt(0)),
    );
  write(0, "RIFF");
  view.setUint32(4, bytes.length - 8, true);
  write(8, "WAVE");
  write(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, 16000, true);
  view.setUint32(28, 32000, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  write(36, "data");
  view.setUint32(40, samples.length * 2, true);
  samples.forEach((sample, i) => {
    const value = Math.max(-1, Math.min(1, sample));
    view.setInt16(
      44 + i * 2,
      Math.round(value * (value < 0 ? 32768 : 32767)),
      true,
    );
  });
  return {
    name: `${filename(file.name)}.wav`,
    mime_type: "audio/wav",
    data: base64(bytes),
    source,
  };
}

export async function prepareFile(
  file: File,
  model: Model | null,
  includeSound: boolean,
): Promise<Attachment> {
  const name = filename(file.name),
    id = crypto.randomUUID();
  if (/\.(txt|md|csv|json|toml)$/i.test(file.name)) {
    if (file.size > 65536)
      throw new Error("Text files must be at most 64 KiB.");
    const content = new TextDecoder("utf-8", { fatal: true }).decode(
      await file.arrayBuffer(),
    );
    if (content.includes("\0"))
      throw new Error("Choose a UTF-8 text file without binary data.");
    return {
      id,
      name,
      kind: "text",
      description: `${content.length.toLocaleString()} characters`,
      text: { path: name, content },
      media: [],
    };
  }
  if (file.size > 40 * 1024 * 1024)
    throw new Error("Choose a media file smaller than 40 MiB.");
  if (/^image\/(jpeg|png|webp)$/.test(file.type)) {
    if (!model?.inputs.images)
      throw new Error(
        "The selected model has not reported image support. Open Model details to check or retry.",
      );
    const bitmap = await createImageBitmap(file);
    let data: string;
    try {
      data = frame(bitmap, bitmap.width, bitmap.height);
    } finally {
      bitmap.close();
    }
    return {
      id,
      name,
      kind: "image",
      description: "Image · resized to fit 1536 px",
      preview: `data:image/jpeg;base64,${data}`,
      media: [{ name, mime_type: "image/jpeg", source: "image", data }],
    };
  }
  if (file.type.startsWith("video/") || /\.(mp4|webm|mov)$/i.test(file.name)) {
    if (!model?.inputs.video)
      throw new Error(
        "Video frame analysis requires a model with image support.",
      );
    if (includeSound && !model.inputs.audio)
      throw new Error(
        "This model has not reported audio support. Turn off “Include video sound” for frames only.",
      );
    const video = document.createElement("video"),
      url = URL.createObjectURL(file);
    video.muted = true;
    video.preload = "auto";
    video.playsInline = true;
    try {
      await mediaEvent(video, "loadeddata", () => {
        video.src = url;
        video.load();
      });
      duration(video.duration);
      const media: Media[] = [];
      const count = Math.min(6, Math.max(1, Math.ceil(video.duration)));
      for (let i = 0; i < count; i++) {
        const timestamp = Math.min(
          video.duration - 0.001,
          (video.duration * (i + 0.5)) / count,
        );
        await mediaEvent(video, "seeked", () => {
          video.currentTime = timestamp;
        });
        media.push({
          name: `${name}.frame-${i + 1}.jpg`,
          mime_type: "image/jpeg",
          data: frame(video, video.videoWidth, video.videoHeight),
          source: "video_frame",
          timestamp: Math.round(timestamp * 1000) / 1000,
        });
      }
      if (includeSound) media.push(await audioPart(file, "video_audio"));
      return {
        id,
        name,
        kind: "video",
        description: `${count} sampled frames · ${includeSound ? "sound included" : "no sound"}`,
        preview: `data:image/jpeg;base64,${media[0].data}`,
        media,
      };
    } finally {
      video.removeAttribute("src");
      video.load();
      URL.revokeObjectURL(url);
    }
  }
  if (
    file.type.startsWith("audio/") ||
    /\.(wav|mp3|m4a|ogg|flac)$/i.test(file.name)
  ) {
    if (!model?.inputs.audio)
      throw new Error(
        "The selected model has not reported audio support. Open Model details to check.",
      );
    const media = await audioPart(file, "audio");
    return {
      id,
      name,
      kind: "audio",
      description: "Audio · mono 16 kHz WAV",
      media: [media],
    };
  }
  throw new Error(
    "Choose PNG, JPEG, WebP, audio, a short video, or a UTF-8 text file.",
  );
}

export function validateAttachments(items: Attachment[]) {
  const texts = items.flatMap((item) => (item.text ? [item.text] : [])),
    media = items.flatMap((item) => item.media);
  if (
    texts.length > 8 ||
    texts.reduce((n, item) => n + item.content.length, 0) > 16000
  )
    throw new Error("Use up to eight text files, totaling 16,000 characters.");
  if (
    media.length > 10 ||
    media.reduce((n, item) => n + item.data.length, 0) > 16_000_000 ||
    media.some((item) => item.data.length > 5592408)
  )
    throw new Error(
      "Media is too large. Use fewer images or one short video (ten prepared parts, 16 MB total).",
    );
  if (media.filter((item) => item.mime_type === "audio/wav").length > 1)
    throw new Error("Use one audio clip or video soundtrack per message.");
}
