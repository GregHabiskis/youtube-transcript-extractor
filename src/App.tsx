import { useState } from "react";
import {
  Archive,
  ArrowRight,
  CalendarDays,
  Check,
  ChevronDown,
  Clock3,
  Copy,
  Download,
  ExternalLink,
  Eye,
  FileText,
  Github,
  LoaderCircle,
  ListVideo,
  Minus,
  RefreshCw,
  Search,
  Sparkles,
  TriangleAlert,
  X,
  Youtube,
} from "lucide-react";

import { inspectYouTube } from "./lib/api";
import { runTranscriptPool } from "./lib/batch";
import { downloadBytes, downloadText, makeZip, transcriptFilename } from "./lib/export";
import { formatCount, formatTimestamp } from "./lib/format";
import type {
  BatchItem,
  InspectionResult,
  TranscriptResult,
  VideoMetadata,
  VideoStatus,
} from "./lib/types";
import { Badge } from "./components/ui/badge";
import { Button } from "./components/ui/button";
import { Card, CardContent, CardFooter, CardHeader } from "./components/ui/card";
import { Input } from "./components/ui/input";
import { Progress } from "./components/ui/progress";

const CONCURRENCY = 2;

function App() {
  const [url, setUrl] = useState("");
  const [latestVideos, setLatestVideos] = useState("20");
  const [language, setLanguage] = useState("en");
  const [customLanguage, setCustomLanguage] = useState("");
  const [inspection, setInspection] = useState<InspectionResult | null>(null);
  const [batchItems, setBatchItems] = useState<BatchItem[]>([]);
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  const [busyInspecting, setBusyInspecting] = useState(false);
  const [batchRunning, setBatchRunning] = useState(false);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState("");

  const likelyVideo = /(?:youtu\.be\/|[?&]v=|\/shorts\/|\/live\/|\/embed\/)/i.test(url);
  const selectedLanguage = language === "custom" ? customLanguage.trim() : language;
  const resolvedCount = batchItems.filter((item) =>
    ["complete", "no_captions", "failed"].includes(item.status),
  ).length;
  const successfulItems = batchItems.filter((item) => item.status === "complete" && item.result);
  const failedItems = batchItems.filter((item) => item.status === "failed");
  const activeResult = activeIndex === null ? null : batchItems[activeIndex]?.result;
  const progress = batchItems.length ? (resolvedCount / batchItems.length) * 100 : 0;

  async function handleInspect(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setInspection(null);
    setBatchItems([]);
    setActiveIndex(null);

    const count = likelyVideo ? 1 : Number.parseInt(latestVideos, 10);
    if (!url.trim()) {
      setError("Paste a YouTube channel or video URL first.");
      return;
    }
    if (!Number.isInteger(count) || count < 1) {
      setError("Latest videos must be a positive whole number.");
      return;
    }

    setBusyInspecting(true);
    try {
      const result = await inspectYouTube(url, count);
      setInspection(result);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Inspection failed.");
    } finally {
      setBusyInspecting(false);
    }
  }

  function updateBatchItem(
    index: number,
    status: VideoStatus,
    result?: TranscriptResult,
    itemError?: string,
  ) {
    setBatchItems((current) =>
      current.map((item, itemIndex) => {
        if (itemIndex !== index) return item;
        if (status === "processing") {
          return { ...item, status, result: undefined, error: undefined, attempts: item.attempts + 1 };
        }
        return {
          ...item,
          status,
          ...(result ? { result } : {}),
          error: itemError,
        };
      }),
    );
  }

  async function processIndices(indices: number[]) {
    if (!inspection || !selectedLanguage) {
      setError("Choose a transcript language before extracting.");
      return;
    }
    setError("");
    setBatchRunning(true);
    await runTranscriptPool({
      videos: inspection.videos,
      language: selectedLanguage,
      indices,
      concurrency: CONCURRENCY,
      onStatus: updateBatchItem,
    });
    setBatchRunning(false);
  }

  function startBatch() {
    if (!inspection) return;
    const initialItems = inspection.videos.map((video) => ({
      video,
      status: "waiting" as const,
      attempts: 0,
    }));
    setBatchItems(initialItems);
    setActiveIndex(null);
    void processIndices(inspection.videos.map((_, index) => index));
  }

  function retry(index: number) {
    if (batchRunning) return;
    setBatchItems((current) =>
      current.map((item, itemIndex) =>
        itemIndex === index ? { ...item, status: "waiting", error: undefined } : item,
      ),
    );
    void processIndices([index]);
  }

  function retryFailed() {
    if (batchRunning || failedItems.length === 0) return;
    const indices = failedItems.map((item) => batchItems.indexOf(item));
    setBatchItems((current) =>
      current.map((item, index) =>
        indices.includes(index) ? { ...item, status: "waiting", error: undefined } : item,
      ),
    );
    void processIndices(indices);
  }

  async function copyTranscript(result: TranscriptResult, key: string) {
    try {
      await navigator.clipboard.writeText(result.transcript);
    } catch {
      const textarea = document.createElement("textarea");
      textarea.value = result.transcript;
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      textarea.remove();
    }
    setCopied(key);
    window.setTimeout(() => setCopied((current) => (current === key ? "" : current)), 1600);
  }

  function downloadTranscript(item: BatchItem) {
    if (!item.result) return;
    const index = item.video.index ?? batchItems.indexOf(item) + 1;
    downloadText(transcriptFilename(index, item.result.video.title), item.result.transcript);
  }

  function downloadBatch() {
    const entries = successfulItems.map((item) => ({
      index: item.video.index ?? batchItems.indexOf(item) + 1,
      title: item.result?.video.title ?? item.video.title,
      text: item.result?.transcript ?? "",
    }));
    if (entries.length === 0) return;
    downloadBytes("ytvid-transcripts.zip", makeZip(entries));
  }

  return (
    <main className="min-h-screen overflow-hidden bg-[var(--paper)] text-[var(--ink)]">
      <div className="mx-auto flex min-h-screen max-w-7xl flex-col px-5 pb-20 pt-5 sm:px-8 lg:px-12">
        <header className="flex flex-wrap items-center justify-between gap-4 border-b border-[var(--line)] pb-5">
          <a href="/" className="flex min-w-0 items-center gap-3" aria-label="YTVID Transcript Extractor home">
            <span className="grid h-9 w-9 place-items-center rounded-xl bg-[var(--ink)] text-[var(--paper)]">
              <Youtube size={18} strokeWidth={2.5} />
            </span>
            <span className="truncate font-mono text-[11px] font-bold uppercase tracking-[0.16em] sm:tracking-[0.22em]">YTVID Transcript Extractor</span>
          </a>
          <div className="flex shrink-0 items-center gap-3">
            <span className="hidden font-mono text-[10px] uppercase tracking-[0.18em] text-[var(--muted)] sm:block">
              Local utility / yt-dlp
            </span>
            <Button asChild variant="outline" size="sm" className="shrink-0">
              <a
                href="https://github.com/GregHabiskis/youtube-transcript-extractor"
                target="_blank"
                rel="noopener noreferrer"
                aria-label="View project on GitHub"
                title="View project on GitHub"
              >
                <Github size={15} aria-hidden="true" />
                GitHub
              </a>
            </Button>
          </div>
        </header>

        <div className="flex-1">
          <section className="grid gap-10 pb-12 pt-12 lg:grid-cols-[1.05fr_0.95fr] lg:items-end lg:pt-20">
          <div>
            <Badge className="border-[var(--accent)]/30 bg-[var(--accent)]/8 text-[var(--accent-dark)]">
              <Sparkles size={12} className="mr-1.5" /> Clean transcripts, kept local
            </Badge>
            <h1 className="mt-6 max-w-3xl font-display text-5xl font-semibold leading-[0.96] tracking-[-0.06em] sm:text-7xl">
              Turn a channel feed into clean transcripts.
            </h1>
            <p className="mt-6 max-w-xl text-base leading-7 text-[var(--muted)] sm:text-lg">
              Inspect the latest uploads, keep the ones you expect, and extract timestamped captions without downloading video or audio.
            </p>
            <div className="mt-8 flex flex-wrap gap-2 font-mono text-[10px] uppercase tracking-[0.15em] text-[var(--muted)]">
              <span className="rounded-full border border-[var(--line)] px-3 py-2">Manual first</span>
              <span className="rounded-full border border-[var(--line)] px-3 py-2">Rolling captions cleaned</span>
              <span className="rounded-full border border-[var(--line)] px-3 py-2">Browser ZIP export</span>
            </div>
          </div>

          <Card className="border-[var(--ink)]/10 bg-white/70">
            <CardHeader className="border-b border-[var(--line)] pb-5">
              <p className="font-mono text-[10px] font-bold uppercase tracking-[0.2em] text-[var(--accent-dark)]">01 / Inspect source</p>
              <h2 className="font-display text-2xl font-semibold tracking-[-0.03em]">Start with a channel or video URL</h2>
            </CardHeader>
            <CardContent className="space-y-5 pt-6">
              <form onSubmit={handleInspect} className="space-y-5">
                <label className="block space-y-2">
                  <span className="text-sm font-semibold">YouTube URL</span>
                  <div className="relative">
                    <Youtube className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-[var(--muted-light)]" size={18} />
                    <Input
                      value={url}
                      onChange={(event) => setUrl(event.target.value)}
                      placeholder="youtube.com/@channel or watch?v=..."
                      className="pl-11"
                      autoComplete="url"
                    />
                  </div>
                </label>

                <div className="grid gap-5 sm:grid-cols-2">
                  <label className="block space-y-2">
                    <span className="text-sm font-semibold">Latest videos</span>
                    <Input
                      type="number"
                      min="1"
                      step="1"
                      value={latestVideos}
                      onChange={(event) => setLatestVideos(event.target.value)}
                      disabled={likelyVideo}
                      aria-describedby="count-help"
                    />
                    <span id="count-help" className="block text-xs leading-5 text-[var(--muted)]">
                      {likelyVideo ? "Ignored for an individual video." : "Any positive number; newest first."}
                    </span>
                  </label>
                  <label className="block space-y-2">
                    <span className="text-sm font-semibold">Transcript language</span>
                    <div className="relative">
                      <select
                        value={language}
                        onChange={(event) => setLanguage(event.target.value)}
                        className="h-12 w-full appearance-none rounded-xl border border-[var(--line-strong)] bg-white/70 px-4 pr-10 text-sm outline-none focus:border-[var(--accent)] focus:ring-4 focus:ring-[var(--accent)]/10"
                      >
                        <option value="en">English / en</option>
                        <option value="auto">Auto / best available</option>
                        <option value="custom">Custom language code...</option>
                      </select>
                      <ChevronDown className="pointer-events-none absolute right-4 top-1/2 -translate-y-1/2 text-[var(--muted)]" size={16} />
                    </div>
                  </label>
                </div>

                {language === "custom" && (
                  <Input
                    value={customLanguage}
                    onChange={(event) => setCustomLanguage(event.target.value)}
                    placeholder="e.g. en-GB, fr, pt-BR"
                    aria-label="Custom transcript language code"
                  />
                )}

                {error && (
                  <div className="flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm leading-5 text-red-800" role="alert">
                    <TriangleAlert size={17} className="mt-0.5 shrink-0" />
                    <span>{error}</span>
                  </div>
                )}

                <Button type="submit" variant="accent" size="lg" className="w-full" disabled={busyInspecting}>
                  {busyInspecting ? <LoaderCircle className="animate-spin" size={18} /> : <Search size={18} />}
                  {busyInspecting ? "Inspecting..." : "Inspect source"}
                  {!busyInspecting && <ArrowRight size={17} className="ml-auto" />}
                </Button>
              </form>
            </CardContent>
          </Card>
        </section>

        {inspection && (
          <section className="space-y-5 border-t border-[var(--line)] pt-10" aria-labelledby="inspection-heading">
            <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
              <div>
                <p className="font-mono text-[10px] font-bold uppercase tracking-[0.2em] text-[var(--accent-dark)]">02 / Confirm queue</p>
                <h2 id="inspection-heading" className="mt-2 font-display text-3xl font-semibold tracking-[-0.04em]">
                  {inspection.channel}
                </h2>
                <p className="mt-2 text-sm text-[var(--muted)]">
                  {inspection.kind === "channel" ? `${formatCount(inspection.found_count)} normal videos found` : "Individual video ready"}
                  {inspection.channel_url && (
                    <> · <a className="underline decoration-[var(--accent)] underline-offset-4" href={inspection.channel_url} target="_blank" rel="noreferrer">Open channel</a></>
                  )}
                </p>
              </div>
              <Button variant="accent" size="lg" onClick={startBatch} disabled={batchRunning || inspection.videos.length === 0}>
                <ListVideo size={18} />
                Extract {inspection.videos.length} transcript{inspection.videos.length === 1 ? "" : "s"}
                <ArrowRight size={17} />
              </Button>
            </div>

            <Card className="overflow-hidden">
              <div className="hidden grid-cols-[3rem_1fr_8rem_7rem] gap-4 border-b border-[var(--line)] bg-[var(--panel-muted)] px-5 py-3 font-mono text-[10px] uppercase tracking-[0.16em] text-[var(--muted)] sm:grid">
                <span>#</span><span>Video</span><span>Date</span><span>Length</span>
              </div>
              <ol className="divide-y divide-[var(--line)]">
                {inspection.videos.map((video, index) => <VideoPreview key={`${video.id}-${index}`} video={video} />)}
              </ol>
            </Card>
          </section>
        )}

        {batchItems.length > 0 && (
          <section className="mt-14 space-y-6 border-t border-[var(--line)] pt-10" aria-labelledby="batch-heading">
            <div className="flex flex-col justify-between gap-5 md:flex-row md:items-end">
              <div>
                <p className="font-mono text-[10px] font-bold uppercase tracking-[0.2em] text-[var(--accent-dark)]">03 / Extract</p>
                <div className="mt-2 flex flex-wrap items-baseline gap-x-4 gap-y-2">
                  <h2 id="batch-heading" className="font-display text-3xl font-semibold tracking-[-0.04em]">Transcript run</h2>
                  <span className="font-mono text-xs text-[var(--muted)]">{resolvedCount} / {batchItems.length} finished</span>
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                {failedItems.length > 0 && <Button variant="outline" size="sm" onClick={retryFailed} disabled={batchRunning}><RefreshCw size={14} /> Retry failed ({failedItems.length})</Button>}
                {successfulItems.length > 0 && <Button variant="default" size="sm" onClick={downloadBatch}><Archive size={14} /> Download ZIP</Button>}
              </div>
            </div>

            <div className="rounded-[1.5rem] border border-[var(--line)] bg-[var(--panel)] p-5 sm:p-6">
              <div className="mb-3 flex items-center justify-between gap-4 font-mono text-[10px] uppercase tracking-[0.16em] text-[var(--muted)]">
                <span>{batchRunning ? `Working with ${CONCURRENCY} concurrent requests` : resolvedCount === batchItems.length ? "Run finished" : "Ready"}</span>
                <span>{Math.round(progress)}%</span>
              </div>
              <Progress value={progress} />
            </div>

            <div className="grid gap-3">
              {batchItems.map((item, index) => (
                <ResultRow
                  key={`${item.video.id}-${index}`}
                  item={item}
                  copied={copied === `row-${index}`}
                  onView={() => setActiveIndex(index)}
                  onCopy={() => item.result && void copyTranscript(item.result, `row-${index}`)}
                  onDownload={() => downloadTranscript(item)}
                  onRetry={() => retry(index)}
                  retryDisabled={batchRunning}
                />
              ))}
            </div>

            {activeResult && activeIndex !== null && (
              <TranscriptViewer
                result={activeResult}
                copied={copied === `viewer-${activeIndex}`}
                onClose={() => setActiveIndex(null)}
                onCopy={() => void copyTranscript(activeResult, `viewer-${activeIndex}`)}
                onDownload={() => downloadTranscript(batchItems[activeIndex])}
              />
            )}
          </section>
        )}
        </div>
        <footer className="mt-16 border-t border-[var(--line)] pt-6 text-center text-sm text-[var(--muted)]">
          Made by Greg Habiskis
        </footer>
      </div>
    </main>
  );
}

function VideoPreview({ video }: { video: VideoMetadata }) {
  return (
    <li className="grid gap-4 px-5 py-4 sm:grid-cols-[3rem_1fr_8rem_7rem] sm:items-center">
      <span className="font-mono text-xs text-[var(--muted-light)]">{String(video.index ?? "").padStart(2, "0")}</span>
      <div className="flex min-w-0 gap-3">
        <div className="hidden h-12 w-20 shrink-0 overflow-hidden rounded-lg bg-[var(--panel-muted)] sm:block">
          {video.thumbnail && <img src={video.thumbnail} alt="" className="h-full w-full object-cover" loading="lazy" />}
        </div>
        <div className="min-w-0">
          <a href={video.url} target="_blank" rel="noreferrer" className="line-clamp-2 text-sm font-semibold leading-5 hover:text-[var(--accent-dark)]">
            {video.title}
          </a>
          <p className="mt-1 truncate text-xs text-[var(--muted)]">{video.channel}</p>
        </div>
      </div>
      <span className="flex items-center gap-1.5 text-xs text-[var(--muted)]"><CalendarDays size={13} /> {video.upload_date ?? "Not listed"}</span>
      <span className="flex items-center gap-1.5 text-xs text-[var(--muted)]"><Clock3 size={13} /> {video.duration ?? "Unknown"}</span>
    </li>
  );
}

function ResultRow({
  item,
  copied,
  onView,
  onCopy,
  onDownload,
  onRetry,
  retryDisabled,
}: {
  item: BatchItem;
  copied: boolean;
  onView: () => void;
  onCopy: () => void;
  onDownload: () => void;
  onRetry: () => void;
  retryDisabled: boolean;
}) {
  const status = statusDetails(item.status);
  return (
    <div className="grid gap-4 rounded-2xl border border-[var(--line)] bg-[var(--panel)] px-4 py-4 sm:grid-cols-[2rem_1fr_auto] sm:items-center sm:px-5">
      <div className={`grid h-8 w-8 place-items-center rounded-full ${status.iconClass}`} title={status.label}>
        <StatusIcon status={item.status} />
      </div>
      <div className="min-w-0">
        <p className="line-clamp-1 text-sm font-semibold">{item.video.title}</p>
        <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-[var(--muted)]">
          <span className={status.textClass}>{status.label}</span>
          {item.result?.source && <span>{item.result.source === "manual" ? "Creator captions" : "Automatic captions"}</span>}
          {item.result?.language && <span>{item.result.language}</span>}
          {item.error && <span className="text-red-700">{item.error}</span>}
          {item.result?.reason && <span>{item.result.reason}</span>}
        </div>
      </div>
      <div className="flex flex-wrap gap-2 sm:justify-end">
        {item.status === "complete" && item.result && (
          <>
            <Button variant="outline" size="sm" onClick={onView}><Eye size={14} /> View</Button>
            <Button variant="ghost" size="sm" onClick={onCopy}><Copy size={14} /> {copied ? "Copied" : "Copy"}</Button>
            <Button variant="ghost" size="sm" onClick={onDownload}><Download size={14} /> TXT</Button>
          </>
        )}
        {item.status === "failed" && <Button variant="destructive" size="sm" onClick={onRetry} disabled={retryDisabled}><RefreshCw size={14} /> Retry</Button>}
      </div>
    </div>
  );
}

function TranscriptViewer({
  result,
  copied,
  onClose,
  onCopy,
  onDownload,
}: {
  result: TranscriptResult;
  copied: boolean;
  onClose: () => void;
  onCopy: () => void;
  onDownload: () => void;
}) {
  return (
    <Card className="overflow-hidden border-[var(--ink)]/15">
      <CardHeader className="border-b border-[var(--line)] bg-[var(--ink)] text-[var(--paper)]">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-[var(--accent-light)]">Transcript viewer</p>
            <h3 className="mt-2 max-w-3xl font-display text-2xl font-semibold tracking-[-0.03em]">{result.video.title}</h3>
            <p className="mt-2 text-sm text-white/65">{result.video.channel} · {result.source === "manual" ? "Creator captions" : "Automatic captions"} · {result.language}</p>
          </div>
          <Button variant="ghost" size="icon" onClick={onClose} className="shrink-0 text-white/70 hover:bg-white/10 hover:text-white" aria-label="Close transcript viewer"><X size={18} /></Button>
        </div>
        <div className="flex flex-wrap gap-2 pt-3">
          <Button variant="secondary" size="sm" onClick={onCopy}><Copy size={14} /> {copied ? "Copied" : "Copy transcript"}</Button>
          <Button variant="secondary" size="sm" onClick={onDownload}><Download size={14} /> Download .txt</Button>
          <Button asChild variant="ghost" size="sm" className="text-white/75 hover:bg-white/10 hover:text-white">
            <a href={result.video.url} target="_blank" rel="noreferrer"><ExternalLink size={14} /> Open video</a>
          </Button>
        </div>
      </CardHeader>
      <CardContent className="bg-[#fbfaf6] p-0">
        <div className="border-b border-[var(--line)] px-6 py-5 text-sm leading-6 text-[var(--muted)] sm:px-10">
          <p><strong className="text-[var(--ink)]">URL:</strong> <a className="underline decoration-[var(--accent)] underline-offset-4" href={result.video.url} target="_blank" rel="noreferrer">{result.video.url}</a></p>
          {result.video.upload_date && <p><strong className="text-[var(--ink)]">Upload date:</strong> {result.video.upload_date}</p>}
        </div>
        <div className="divide-y divide-[var(--line)] px-6 py-2 sm:px-10">
          {result.blocks.map((block, index) => (
            <div key={`${block.start_ms}-${index}`} className="grid gap-2 py-5 sm:grid-cols-[13rem_1fr] sm:gap-6">
              <a
                href={`${result.video.url}&t=${Math.floor(block.start_ms / 1000)}s`}
                target="_blank"
                rel="noreferrer"
                className="h-fit font-mono text-xs font-semibold text-[var(--accent-dark)] underline decoration-[var(--accent)]/40 underline-offset-4 hover:decoration-[var(--accent)]"
              >
                [{formatTimestamp(block.start_ms)} → {formatTimestamp(block.end_ms)}]
              </a>
              <p className="select-text text-[15px] leading-7 text-[var(--ink)]">{block.text}</p>
            </div>
          ))}
        </div>
      </CardContent>
      <CardFooter className="justify-between border-t border-[var(--line)] bg-[var(--panel-muted)] text-xs text-[var(--muted)]">
        <span className="flex items-center gap-1.5"><FileText size={14} /> {result.blocks.length} timestamped blocks</span>
        <span className="font-mono uppercase tracking-[0.12em]">Plain text / UTF-8</span>
      </CardFooter>
    </Card>
  );
}

function statusDetails(status: VideoStatus) {
  switch (status) {
    case "processing":
      return { label: "Processing", iconClass: "bg-[var(--accent)]/12 text-[var(--accent-dark)]", textClass: "text-[var(--accent-dark)]" };
    case "complete":
      return { label: "Complete", iconClass: "bg-emerald-100 text-emerald-700", textClass: "text-emerald-700" };
    case "no_captions":
      return { label: "No captions", iconClass: "bg-amber-100 text-amber-700", textClass: "text-amber-700" };
    case "failed":
      return { label: "Failed", iconClass: "bg-red-100 text-red-700", textClass: "text-red-700" };
    default:
      return { label: "Waiting", iconClass: "bg-[var(--panel-muted)] text-[var(--muted)]", textClass: "text-[var(--muted)]" };
  }
}

function StatusIcon({ status }: { status: VideoStatus }) {
  if (status === "processing") return <LoaderCircle size={15} className="animate-spin" />;
  if (status === "complete") return <Check size={15} />;
  if (status === "no_captions") return <Minus size={15} />;
  if (status === "failed") return <X size={15} />;
  return <Clock3 size={14} />;
}

export default App;
