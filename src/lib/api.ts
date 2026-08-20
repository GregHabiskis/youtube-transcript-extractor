import type { InspectionResult, TranscriptResult } from "./types";

export class ApiRequestError extends Error {
  constructor(message: string, public readonly status: number) {
    super(message);
    this.name = "ApiRequestError";
  }
}

async function requestJson<T>(path: string, body?: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      method: body === undefined ? "GET" : "POST",
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiRequestError("The API could not be reached. Check your connection and try again.", 0);
  }

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
    const fallbackMessage =
      response.status === 404
        ? "API endpoint not found. The deployment may not include the FastAPI function."
        : response.status >= 500
          ? "The server could not complete the request. Try again shortly."
          : "The request was not accepted. Check the URL and options.";
    const message =
      (payload && typeof payload.detail === "string" && payload.detail) ||
      (payload && typeof payload.error === "string" && payload.error) ||
      validationMessage ||
      fallbackMessage;
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
