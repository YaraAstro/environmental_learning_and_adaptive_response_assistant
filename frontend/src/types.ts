export type TextAttachment = { path: string; content: string };
export type Media = {
  name: string;
  mime_type: "image/jpeg" | "image/png" | "image/webp" | "audio/wav";
  data: string;
  source: "image" | "audio" | "video_frame" | "video_audio";
  timestamp?: number;
};
export type Attachment = {
  id: string;
  name: string;
  kind: "text" | "image" | "audio" | "video";
  description: string;
  preview?: string;
  text?: TextAttachment;
  media: Media[];
};
export type Session = { id: string; title: string; created_at: string };
export type Turn = { role: "user" | "assistant"; content: string };
export type Memory = { key: string; value: string };
export type Status = { provider: "mock" | "ollama"; model: string | null };
export type Model = {
  model: string;
  capabilities: string[];
  details: Record<string, string | string[]>;
  model_info: Record<string, number>;
  inputs: { images: boolean; audio: boolean; video: boolean };
  limits?: {
    text_characters: number;
    output_tokens: number;
    timeout_seconds: number;
  };
};
