import type { NextRequest } from 'next/server'

export const runtime = 'edge'

export async function POST(req: Request) {
  try {
    const upstream = process.env.ORCHESTRATOR_SSE_URL
    if (!upstream) {
      return new Response('Missing ORCHESTRATOR_SSE_URL', { status: 500 })
    }

    const incoming = await req.json().catch(() => ({})) as any
    const job_id = incoming?.job_id
    if (!job_id) return new Response('Missing job_id', { status: 400 })

    const auth = (req.headers.get('authorization') || '').toString()

    const res = await fetch(upstream, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(auth ? { Authorization: auth } : {}),
      },
      body: JSON.stringify({ job_id }),
    })

    if (!res.ok || !res.body) {
      const text = await res.text().catch(() => 'Upstream error')
      return new Response(text, { status: res.status || 502 })
    }

    const readable = new ReadableStream({
      start(controller) {
        const reader = res.body!.getReader()
        const pump = (): any => reader.read().then(({ done, value }) => {
          if (done) {
            controller.close()
            return
          }
          if (value) controller.enqueue(value)
          return pump()
        })
        return pump()
      },
      cancel() {
        try { res.body?.cancel() } catch {}
      }
    })

    return new Response(readable, {
      headers: {
        'Content-Type': 'text/event-stream; charset=utf-8',
        'Cache-Control': 'no-cache, no-transform',
        'Connection': 'keep-alive',
        'X-Accel-Buffering': 'no',
      },
    })
  } catch (e: any) {
    return new Response(`Proxy error: ${e?.message || 'unknown'}`, { status: 500 })
  }
}
