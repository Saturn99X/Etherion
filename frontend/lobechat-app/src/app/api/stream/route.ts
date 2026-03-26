/**
 * /api/stream — SSE proxy to Etherion orchestrator.
 *
 * Accepts POST { job_id } and streams the orchestrator's SSE response
 * back to the client.  Used by sendGoalAndStream() in bridge/chat.ts.
 *
 * NEXT_PUBLIC_CHAT_SSE_URL / ORCHESTRATOR_SSE_URL must point to the
 * FastAPI /stream endpoint (e.g. http://localhost:8080/stream).
 */

export const runtime = 'edge';

export async function POST(req: Request) {
  try {
    // Server-side: prefer ORCHESTRATOR_SSE_URL; client default falls back to this route
    const upstream =
      process.env.ORCHESTRATOR_SSE_URL ??
      process.env.NEXT_PUBLIC_CHAT_SSE_URL;

    if (!upstream) {
      return new Response('Missing ORCHESTRATOR_SSE_URL or NEXT_PUBLIC_CHAT_SSE_URL', { status: 500 });
    }

    const body = await req.json().catch(() => ({})) as Record<string, unknown>;
    const job_id = body?.job_id;
    if (!job_id) return new Response('Missing job_id', { status: 400 });

    const auth = req.headers.get('authorization') ?? '';

    const res = await fetch(upstream, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(auth ? { Authorization: auth } : {}),
      },
      body: JSON.stringify({ job_id }),
    });

    if (!res.ok || !res.body) {
      const text = await res.text().catch(() => 'Upstream error');
      return new Response(text, { status: res.status || 502 });
    }

    // Stream the SSE response body back verbatim
    const readable = new ReadableStream({
      start(controller) {
        const reader = res.body!.getReader();
        const pump = (): Promise<void> =>
          reader.read().then(({ done, value }) => {
            if (done) { controller.close(); return; }
            if (value) controller.enqueue(value);
            return pump();
          });
        return pump();
      },
      cancel() {
        try { res.body?.cancel(); } catch { /* ignore */ }
      },
    });

    return new Response(readable, {
      headers: {
        'Content-Type': 'text/event-stream; charset=utf-8',
        'Cache-Control': 'no-cache, no-transform',
        'Connection': 'keep-alive',
        'X-Accel-Buffering': 'no',
      },
    });
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : 'unknown';
    return new Response(`Proxy error: ${msg}`, { status: 500 });
  }
}
