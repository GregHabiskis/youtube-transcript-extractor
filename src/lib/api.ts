import type { InspectionResult, TranscriptResult } from "./types";

export class ApiRequestError extends Error {
  constructor(message: string, public readonly status: number) {
    super(message);
    this.name = "ApiRequestError";
  }
}

async function requestJson<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(path, {
    method: body === undefined ? "GET" : "POST",
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const validationMessage =
      payload &&
      Array.isArray(payload.detail) &&
      payload.detail
        .map((item: unknown) =>
          item && typeof item === "object" && "msg" in item && typeof item.msg === "string"
            ? item.msg
            : null,
        )
        .filter((message: string | null): message is string => Boolean(message))
        .join(" ");
    const message =
      (payload && typeof payload.detail === "string" && payload.detail) ||
      (payload && typeof payload.error === "string" && payload.error) ||
      validationMessage ||
      "The API request could not be completed.";
    throw new ApiRequestError(message, response.status);
  }
  return payload as T;
}

export function inspectYouTube(url: string, latestVideos: number) {
  return requestJson<InspectionResult>("/api/inspect", {
    url,
    latest_videos: latestVideos,
  });
}

export function extractTranscript(url: string, language: string) {
  return requestJson<TranscriptResult>("/api/transcript", { url, language });
}

export function getHealth() {
  return requestJson<{ status: string }>("/api/health");
}
