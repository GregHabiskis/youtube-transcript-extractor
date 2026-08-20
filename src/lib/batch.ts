import { extractTranscript } from "./api";
import type { TranscriptResult, VideoMetadata, VideoStatus } from "./types";

interface PoolOptions {
  videos: VideoMetadata[];
  language: string;
  indices: number[];
  concurrency?: number;
  onStatus: (index: number, status: VideoStatus, result?: TranscriptResult, error?: string) => void;
}

export async function runTranscriptPool({
  videos,
  language,
  indices,
  concurrency = 2,
  onStatus,
}: PoolOptions): Promise<void> {
  let cursor = 0;
  const queue = [...indices];

  async function worker() {
    while (cursor < queue.length) {
      const queuePosition = cursor;
      cursor += 1;
      const index = queue[queuePosition];
      const video = videos[index];
      if (!video) continue;

      onStatus(index, "processing");
      try {
        const result = await extractTranscript(video.url, language);
        onStatus(index, result.status === "no_captions" ? "no_captions" : "complete", result);
      } catch (error) {
        onStatus(index, "failed", undefined, error instanceof Error ? error.message : "Request failed.");
      }
    }
  }

  const workerCount = Math.max(1, Math.min(concurrency, queue.length || 1));
  await Promise.all(Array.from({ length: workerCount }, () => worker()));
}
