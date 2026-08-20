import { describe, expect, it } from "vitest";
import { unzipSync, strFromU8 } from "fflate";
import { makeZip, sanitizeFilename, transcriptFilename } from "./export";

describe("browser export filenames", () => {
  it("removes path and operating-system characters", () => {
    expect(sanitizeFilename("../A: dangerous/title?")).toBe("A dangerous title");
  });

  it("avoids reserved Windows device names", () => {
    expect(sanitizeFilename("CON")).toBe("transcript-con");
  });

  it("keeps stable numbered transcript names", () => {
    expect(transcriptFilename(3, "Episode")).toBe("003-Episode.txt");
  });

  it("creates an ordered readable zip", () => {
    const archive = makeZip([
      { index: 1, title: "First", text: "one" },
      { index: 2, title: "Second", text: "two" },
    ]);
    const files = unzipSync(archive);
    expect(Object.keys(files)).toEqual(["001-First.txt", "002-Second.txt"]);
    expect(strFromU8(files["002-Second.txt"])).toBe("two");
  });
});
