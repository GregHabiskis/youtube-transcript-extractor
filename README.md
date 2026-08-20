# YTVID Transcript Extractor

YTVID Transcript Extractor is a local-friendly and Vercel-deployable YouTube transcript extractor. It discovers recent normal videos from a channel, retrieves captions through the official `yt-dlp` Python API, removes deterministic rolling-caption repetition, and returns readable timestamped plain text.

The application never downloads video or audio. Subtitle payloads are processed in memory inside the individual request that asked for them.

## What It Does

- Accepts YouTube channel roots, handles, `/videos` URLs, individual video URLs, and `youtu.be` URLs.
- Treats a channel root as the normal uploads/videos feed.
- Discovers an arbitrary positive number of recent videos without requiring a manually collected URL list.
- Prefers creator subtitles and falls back to automatic captions.
- Supports English, automatic best-available selection, and arbitrary YouTube/BCP-47 language identifiers.
- Prefers JSON3 subtitle tracks and falls back to WebVTT/SRT parsing.
- Removes exact duplicate and conservative token-overlap rolling-caption artifacts without using an LLM.
- Preserves cue timing and produces bounded readable paragraphs.
- Lets the browser preview, copy, download, retry, and ZIP successful transcripts.

## Architecture

The production path is stateless and compatible with Vercel Functions:

```text
React/Vite frontend
        │ relative /api/* requests
        ▼
FastAPI application
        │
        └── yt-dlp Python API ── YouTube captions only
```

The browser orchestrates batches with two concurrent `POST /api/transcript` requests. There is no server-side job queue, database, persistent runtime directory, background worker, or server-side ZIP file.

Vercel is explicitly configured with its `FastAPI` framework preset so all requests are routed through one Python application. The `api/index.py` entrypoint imports the real FastAPI application from `backend/app.py`; after `pnpm build`, FastAPI serves the Vite `dist/` directory through its frontend integration, while plain Uvicorn serves the same application locally.

## Tech Stack

### Shared Stack

- Frontend: React 19 with TypeScript.
- Bundler and development server: Vite 7.
- Styling: Tailwind CSS 4.
- UI utilities: Radix Slot, Lucide React, `clsx`, `tailwind-merge`, and `fflate`.
- Backend: Python 3.14 with FastAPI and Uvicorn.
- YouTube extraction: the official `yt-dlp` Python API.
- Package managers: `pnpm@11.15.0` for JavaScript and `uv` for Python.
- Storage: none. Caption data is processed in memory per request.
- Database, authentication, and persistent application storage: none.
- Media processing: no video or audio downloads; captions only.

### Localhost

- `pnpm dev` starts the Vite frontend at `http://127.0.0.1:5173` and the Uvicorn backend at `http://127.0.0.1:8000`.
- Vite proxies relative `/api/*` requests to FastAPI.
- The frontend source is in `src/` and the backend source is in `backend/`.
- Browser-side ZIP exports use `fflate`.
- Python development tools include pytest, Ruff, and HTTPX.

### Vercel

- Hosting: Vercel Python Serverless Functions.
- Framework preset: `FastAPI`.
- Entrypoint: `api/index.py`, which imports `backend.app:app`.
- Build command: `pnpm build`, which runs `tsc -b && vite build` and writes the frontend to `dist/`.
- FastAPI serves the compiled React frontend and `/api/*` routes from the same deployment.
- Function maximum duration: 180 seconds.
- `yt-dlp` uses Node/EJS challenge support when a supported JavaScript runtime is available.
- `YTDLP_PROXY_URL` is optional and is used only for a single retry after detected YouTube blocking.
- The Vercel runtime is stateless: there is no database, queue, persistent filesystem, or background worker.

## Requirements

- Python 3.14.x
- Node.js 20 or newer
- Internet access
- A current `yt-dlp` installation from the project dependency

`ffmpeg` is not required because the application does not process media files. Current yt-dlp documentation recommends `yt-dlp-ejs` and a supported JavaScript runtime for full YouTube support; YouTube extraction may be more reliable when those optional requirements are available in the execution environment.

## Installation

### Python with uv

```bash
uv sync --extra dev
```

### Python with a virtual environment

```bash
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Install the frontend dependencies:

```bash
pnpm install
```

## Local Development

Start both the FastAPI backend and Vite frontend with one command:

```bash
pnpm dev
```

For detailed local yt-dlp/caption pipeline diagnostics, run `YTVID_LOG_LEVEL=DEBUG pnpm dev`.

Open `http://127.0.0.1:5173`. Vite proxies relative `/api/*` requests to `http://127.0.0.1:8000`.

For a production-like local check where FastAPI serves the compiled React application:

```bash
pnpm build
uv run uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`.

If the Vercel CLI is needed for local runtime emulation, run `pnpm dlx vercel@latest dev`.

## Optional Vercel Proxy

Vercel can use a trusted HTTP or HTTPS proxy only when YouTube blocks the direct server request. Add `YTDLP_PROXY_URL` in the Vercel project environment variables, then redeploy:

```text
YTDLP_PROXY_URL=https://proxy.example.com:8443
```

The application always tries direct yt-dlp extraction first and retries once through this proxy only for detected YouTube access restrictions. If the variable is absent, no proxy is used. Keep proxy credentials in Vercel's encrypted environment settings; they are never sent to the React frontend, API responses, or application logs. Do not commit `.env` files or proxy credentials.

## Usage

1. Paste `https://www.youtube.com/@ExampleChannel` or an individual video URL.
2. Enter any positive number such as `20` or `125` for a channel.
3. Select `English / en`, `Auto / best available`, or a custom language code.
4. Click **Inspect source**.
5. Confirm the newest normal videos shown by the application.
6. Click **Extract transcripts**.
7. View, copy, retry, download individual `.txt` files, or download the completed batch ZIP.

The browser shows only truthful request states: `Waiting`, `Processing`, `Complete`, `No captions`, and `Failed`. Progress counts requests that have actually returned; no backend extraction percentage is fabricated. The public API accepts any positive count up to a safety limit of 500 and rejects larger requests rather than silently truncating them.

## API

### `GET /api/health`

Returns `{ "status": "ok" }` without contacting YouTube.

### `POST /api/inspect`

Example request:

```json
{
  "url": "https://www.youtube.com/@ExampleChannel",
  "latest_videos": 20
}
```

Returns channel metadata and the bounded newest-first video list. For an individual video, `latest_videos` is ignored.

### `POST /api/transcript`

Example request:

```json
{
  "url": "https://www.youtube.com/watch?v=BaW_jenozKc",
  "language": "en"
}
```

Successful responses include the video metadata, caption source, selected language, selected format, structured timestamped blocks, and a UTF-8 plain-text rendering. Failed responses include a safe diagnostic `code` such as `SUBTITLE_DOWNLOAD_FAILED`, `YOUTUBE_BLOCKED`, or `PROXY_RETRY_FAILED` without exposing a traceback or proxy credentials. Videos without usable captions return `status: "no_captions"` with a distinct code without aborting the browser batch.

## Deploying to Vercel

1. Push this repository to GitHub.
2. Sign into Vercel and choose **New Project**.
3. Import the GitHub repository.
4. Keep the repository root as the project root and confirm the detected Python/Vite build setup.
5. Deploy and open the generated `https://<project>.vercel.app` URL.
6. Verify `https://<project>.vercel.app/api/health`.
7. Test one public individual video before testing a small channel batch.

`vercel.json` selects the `FastAPI` preset and configures the resolved `api/index.py` function with a 180-second maximum duration. `pyproject.toml` points Vercel at `api.index:app` and runs `pnpm build`; FastAPI owns `/` and `/api/*`, so the browser and backend use the same complete paths. No legacy `builds` or `routes` configuration is used.

Vercel's Git integration creates Preview Deployments for branch and pull-request pushes. Merging the configured production branch, normally `main`, creates a Production Deployment. Future pushes to that branch deploy automatically.

For a personal-only deployment, Vercel Deployment Protection can be enabled in project settings. This project does not add a custom authentication system.

## Security and Privacy

- The API accepts only approved YouTube hosts and individual YouTube video URLs.
- Client input cannot supply arbitrary yt-dlp options.
- No shell commands are used by the application.
- No user-provided path is opened or exposed.
- Transcript/title content is rendered as text, not executable HTML.
- Subtitle responses have a size limit and yt-dlp retries/timeouts are bounded.
- No analytics, telemetry, cloud storage, database, or external AI service is used.

## Limitations

Transcript extraction depends on captions exposed by YouTube and yt-dlp. Private, deleted, age-restricted, members-only, geo-restricted, or login-required videos may fail without authentication. The application does not embed personal cookies or credentials.

Vercel requests originate from cloud/datacenter IP addresses. YouTube may throttle or challenge those requests even when the same URL succeeds locally. Configure an approved trusted proxy with `YTDLP_PROXY_URL` when direct Vercel access is blocked. Current yt-dlp YouTube support may also require its recommended JavaScript challenge components/runtime.

Each Vercel request processes one video and is bounded by the platform function duration. Failed videos can be retried independently; completed videos are not restarted.

## Testing and Checks

Run backend tests:

```bash
uv run pytest
```

Run frontend tests:

```bash
pnpm test
```

Build the production frontend:

```bash
pnpm build
```

Run lint checks when the development extra is installed:

```bash
uv run ruff check backend tests
```

Validate the deployment bundle with `pnpm dlx vercel@latest build` when the Vercel CLI is not installed locally. An authenticated production deployment is not required for local development or the normal test suite.
