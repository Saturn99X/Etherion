"use client"

import React, { useEffect, useMemo, useState } from 'react'
import Image from 'next/image'
import { cn } from '@/lib/utils'

// In-memory logo URL cache to avoid refetching in-session
const LogoCache = new Map<string, string | null>()

export interface BrandAvatarProps {
  name: string
  domain?: string
  size?: number
  className?: string
  rounded?: boolean
  // If true, force searching by name (useful when domain unknown)
  preferNameSearch?: boolean
}

export function BrandAvatar({ name, domain, size = 32, className, rounded = true, preferNameSearch = false }: BrandAvatarProps) {
  const [url, setUrl] = useState<string | null | undefined>(undefined)

  const key = useMemo(() => {
    const base = (domain && !preferNameSearch) ? `d:${domain.toLowerCase()}` : `n:${name.toLowerCase()}`
    return base
  }, [name, domain, preferNameSearch])

  useEffect(() => {
    let cancelled = false
    const cached = LogoCache.get(key)
    if (cached !== undefined) {
      setUrl(cached)
      return
    }

    const q = (domain && !preferNameSearch) ? `domain=${encodeURIComponent(domain)}` : `name=${encodeURIComponent(name)}`
    fetch(`/api/brand/logo?${q}`, { cache: 'no-store' })
      .then(async (res) => {
        if (!res.ok) return null
        const data = await res.json().catch(() => null)
        return data?.url || null
      })
      .catch(() => null)
      .then((logoUrl) => {
        if (cancelled) return
        LogoCache.set(key, logoUrl)
        setUrl(logoUrl)
      })

    return () => { cancelled = true }
  }, [key, name, domain, preferNameSearch])

  const fallback = (
    <div
      className={cn(
        'flex items-center justify-center select-none bg-white/10 text-white/80',
        rounded ? 'rounded-full' : 'rounded-md',
        className,
      )}
      style={{ width: size, height: size, fontSize: Math.max(10, Math.floor(size * 0.45)) }}
      aria-label={`${name} logo`}
    >
      {name?.[0]?.toUpperCase() || '?'}
    </div>
  )

  if (url === undefined) {
    // Loading state uses fallback initial
    return fallback
  }

  if (!url) return fallback

  return (
    <Image
      src={url}
      alt={`${name} logo`}
      width={size}
      height={size}
      className={cn(rounded ? 'rounded-full' : 'rounded-md', className)}
      unoptimized
    />
  )
}
