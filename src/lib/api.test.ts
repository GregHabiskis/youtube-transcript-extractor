import { describe, expect, it, vi } from "vitest";
import { getHealth, ApiRequestError } from "./api";

describe("API client errors", () => {
  it("keeps API calls same-origin and identifies a missing deployment function", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      expect(input).toBe("/api/health");
      return new Response("The page could not be found", { status: 404 });
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(getHealth()).rejects.toEqual(
      expect.objectContaining({
        name: "ApiRequestError",
        message: "API endpoint not found. The deployment may not include the FastAPI function.",
        status: 404,
      }),
    );
  });

  it("reports network failures without exposing implementation details", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("Failed to fetch"); }));

    await expect(getHealth()).rejects.toEqual(
      expect.objectContaining({
        name: "ApiRequestError",
        message: "The API could not be reached. Check your connection and try again.",
        status: 0,
      } satisfies Partial<ApiRequestError>),
    );
  });
});
