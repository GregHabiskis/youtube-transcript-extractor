import { strToU8, zipSync } from "fflate";

export function sanitizeFilename(title: string) {
  const cleaned = title
    .normalize("NFKC")
    .replace(/[<>:"/\\|?*\u0000-\u001f]/g, " ")
    .replace(/\s+/g, " ")
    .replace(/^[. ]+|[. ]+$/g, "")
    .trim()
    .slice(0, 120);
  const safe = cleaned || "transcript";
  if (/^(con|prn|aux|nul|com[1-9]|lpt[1-9])$/i.test(safe)) {
    return `transcript-${safe.toLowerCase()}`;
  }
  return safe;
}

export function transcriptFilename(index: number, title: string) {
  return `${String(index).padStart(3, "0")}-${sanitizeFilename(title)}.txt`;
}

export function makeZip(
  entries: Array<{ index: number; title: string; text: string }>,
) {
  const files: Record<string, Uint8Array> = {};
  for (const entry of entries) {
    files[transcriptFilename(entry.index, entry.title)] = strToU8(entry.text);
  }
  return zipSync(files, { level: 6 });
}

export function downloadText(filename: string, text: string) {
  const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
  downloadBlob(filename, blob);
}

export function downloadBytes(filename: string, bytes: Uint8Array) {
  const copy = new Uint8Array(bytes);
  const blob = new Blob([copy.buffer as ArrayBuffer], { type: "application/zip" });
  downloadBlob(filename, blob);
}

function downloadBlob(filename: string, blob: Blob) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
