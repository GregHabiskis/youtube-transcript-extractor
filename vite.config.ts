import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        configure(proxy) {
          type ProxyResponse = {
            headersSent?: boolean;
            writableEnded?: boolean;
            writeHead?: (status: number, headers: Record<string, string>) => void;
            end?: (body: string) => void;
          };
          const proxyServer = proxy as unknown as {
            on: (
              event: "error",
              listener: (_error: unknown, _request: unknown, response?: ProxyResponse) => void,
            ) => void;
          };
          proxyServer.on("error", (_error, _request, response) => {
            if (
              !response ||
              response.headersSent ||
              response.writableEnded ||
              !response.writeHead ||
              !response.end
            ) {
              return;
            }
            response.writeHead(503, { "Content-Type": "application/json" });
            response.end(
              JSON.stringify({
                status: "failed",
                code: "BACKEND_UNAVAILABLE",
                error: "The local API is not running. Start the app with `pnpm dev`.",
              }),
            );
          });
        },
      },
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
