export type VideoStatus = "waiting" | "processing" | "complete" | "no_captions" | "failed";

export interface VideoMetadata {
  id: string;
  title: string;
  url: string;
  channel: string;
  channel_url?: string | null;
  upload_date?: string | null;
  duration_seconds?: number | null;
  duration?: string | null;
  thumbnail?: string | null;
  index?: number | null;
}

export interface InspectionResult {
  kind: "channel" | "video";
  source_url: string;
  channel: string;
  channel_url?: string | null;
  requested_count: number;
  found_count: number;
  videos: VideoMetadata[];
}

export interface TranscriptBlock {
  start_ms: number;
  end_ms: number;
  text: string;
}

export interface TranscriptResult {
  status: "complete" | "no_captions";
  video: VideoMetadata;
  source?: "manual" | "automatic" | null;
  language?: string | null;
  transcript: string;
  blocks: TranscriptBlock[];
  reason?: string | null;
}

export interface BatchItem {
  video: VideoMetadata;
  status: VideoStatus;
  result?: TranscriptResult;
  error?: string;
  attempts: number;
}
