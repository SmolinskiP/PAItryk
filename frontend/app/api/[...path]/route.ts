// Catch-all proxy do backendu FastAPI.
// Streaming-aware: ręcznie pompujemy chunki z upstream przez ReadableStream,
// żeby Next.js nie buforował SSE w produkcji.

import { NextRequest } from "next/server";

const BACKEND = process.env.BACKEND_INTERNAL_URL ?? "http://127.0.0.1:8010";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

async function proxy(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  const url = new URL(req.url);
  const target = `${BACKEND}/api/${path.join("/")}${url.search}`;

  const headers = new Headers(req.headers);
  headers.delete("host");
  headers.delete("connection");
  headers.delete("content-length");
  headers.delete("accept-encoding");

  const hasBody = !["GET", "HEAD"].includes(req.method);

  const init: RequestInit & { duplex?: "half" } = {
    method: req.method,
    headers,
    body: hasBody ? req.body : undefined,
    duplex: "half",
    cache: "no-store"
  };

  const upstream = await fetch(target, init);
  const reader = upstream.body?.getReader();

  // Manualne pompowanie chunków — wymusza natychmiastowe flushowanie do klienta
  // i omija buforowanie Next.js production server.
  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      if (!reader) {
        controller.close();
        return;
      }
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          if (value) controller.enqueue(value);
        }
        controller.close();
      } catch (err) {
        controller.error(err);
      }
    },
    async cancel() {
      // Klient odłączył — anulujemy reader (NIE upstream.body, który jest locked).
      try {
        await reader?.cancel();
      } catch {
        // ignoruj
      }
    }
  });

  const responseHeaders = new Headers();
  const passthrough = ["content-type", "cache-control", "set-cookie"];
  for (const name of passthrough) {
    const value = upstream.headers.get(name);
    if (value) responseHeaders.set(name, value);
  }
  if (!responseHeaders.has("cache-control")) {
    responseHeaders.set("cache-control", "no-cache, no-transform");
  }
  responseHeaders.set("x-accel-buffering", "no");

  if ([204, 205, 304].includes(upstream.status)) {
    return new Response(null, {
      status: upstream.status,
      headers: responseHeaders
    });
  }

  return new Response(stream, {
    status: upstream.status,
    headers: responseHeaders
  });
}

export { proxy as GET, proxy as POST, proxy as PUT, proxy as PATCH, proxy as DELETE };
