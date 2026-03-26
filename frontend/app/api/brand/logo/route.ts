import { NextRequest, NextResponse } from 'next/server'

// Server-side proxy for Brandfetch to avoid exposing tokens to the client.
// Query params: ?domain=example.com or ?name=BrandName
export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url)
  const domain = searchParams.get('domain') || ''
  const name = searchParams.get('name') || ''

  const token = process.env.BRANDFETCH_TOKEN
  if (!token) {
    return NextResponse.json({ error: 'Brandfetch token not configured' }, { status: 501 })
  }

  try {
    let url: string
    if (domain) {
      // Brand endpoint by domain
      url = `https://api.brandfetch.io/v2/brands/${encodeURIComponent(domain)}`
    } else if (name) {
      // Search endpoint by name
      url = `https://api.brandfetch.io/v2/search/${encodeURIComponent(name)}`
    } else {
      return NextResponse.json({ error: 'Missing domain or name' }, { status: 400 })
    }

    const res = await fetch(url, {
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      // 5s timeout via AbortController
      signal: AbortSignal.timeout(5000),
      cache: 'no-store',
    })

    if (!res.ok) {
      return NextResponse.json({ error: `Brandfetch error ${res.status}` }, { status: 502 })
    }

    const data = await res.json().catch(() => null)
    if (!data) return NextResponse.json({ error: 'Invalid Brandfetch response' }, { status: 502 })

    // Try to pick a logo/icon URL from response shapes
    // Case 1: direct brand object with logos
    const pickFromBrand = (brand: any): string | null => {
      const logos = Array.isArray(brand?.logos) ? brand.logos : []
      for (const prefType of ['icon', 'logo']) {
        const chosen = logos.find((l: any) => l?.type === prefType)
        const formats = Array.isArray(chosen?.formats) ? chosen.formats : []
        // prefer svg then png
        const svg = formats.find((f: any) => f?.format === 'svg')
        if (svg?.src) return svg.src
        const png = formats.find((f: any) => f?.format === 'png')
        if (png?.src) return png.src
      }
      return null
    }

    let urlOut: string | null = null
    if (domain) {
      urlOut = pickFromBrand(data)
    } else if (name) {
      // Search returns an array; try first
      const first = Array.isArray(data) ? data[0] : null
      urlOut = pickFromBrand(first)
    }

    if (!urlOut) return NextResponse.json({ url: null }, { status: 200 })
    return NextResponse.json({ url: urlOut }, { status: 200 })
  } catch (e) {
    return NextResponse.json({ error: 'Brandfetch request failed' }, { status: 502 })
  }
}
