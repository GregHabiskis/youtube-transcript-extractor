import { describe, expect, it, vi } from "vitest";
import { runTranscriptPool } from "./batch";
import type { VideoMetadata } from "./types";

const videos: VideoMetadata[] = [
  { id: "BaW_jenozKc", title: "One", url: "https://www.youtube.com/watch?v=BaW_jenozKc", channel: "Test" },
  { id: "dQw4w9WgXcQ", title: "Two", url: "https://www.youtube.com/watch?v=dQw4w9WgXcQ", channel: "Test" },
  { id: "YE7VzlLtp-4", title: "Three", url: "https://www.youtube.com/watch?v=YE7VzlLtp-4", channel: "Test" },
];

describe("browser transcript pool", () => {
  it("never exceeds its configured concurrency and processes every queued item", async () => {
    let active = 0;
    let peak = 0;
    const fetchMock = vi.fn(async () => {
      active += 1;
      peak = Math.max(peak, active);
      await new Promise((resolve) => setTimeout(resolve, 10));
      active -= 1;
      return new Response(JSON.stringify({ status: "complete", transcript: "text", blocks: [], video: videos[0] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    const statuses: string[] = [];
    await runTranscriptPool({
      videos,
      language: "en",
      indices: [0, 1, 2],
      concurrency: 2,
      onStatus: (_index, status) => statuses.push(status),
    });

    expect(peak).toBe(2);
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(statuses.filter((status) => status === "processing")).toHaveLength(3);
    expect(statuses.filter((status) => status === "complete")).toHaveLength(3);
  });
});
