'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { createStyles } from 'antd-style';
import { Avatar } from 'antd';
import Image from 'next/image';

const useStyles = createStyles(({ token, css }) => ({
  avatar: css`
    background: ${token.colorFillQuaternary};
    color: ${token.colorText};
    font-weight: 600;
    border: 1px solid ${token.colorBorder};
  `,
}));

// In-memory logo URL cache to avoid refetching in-session
const LogoCache = new Map<string, string | null>();

export interface BrandAvatarProps {
  name: string;
  domain?: string;
  size?: number;
  className?: string;
  shape?: 'circle' | 'square';
  preferNameSearch?: boolean;
}

export function BrandAvatar({
  name,
  domain,
  size = 32,
  className,
  shape = 'circle',
  preferNameSearch = false,
}: BrandAvatarProps) {
  const { styles } = useStyles();
  const [url, setUrl] = useState<string | null | undefined>(undefined);

  const key = useMemo(() => {
    const base =
      domain && !preferNameSearch ? `d:${domain.toLowerCase()}` : `n:${name.toLowerCase()}`;
    return base;
  }, [name, domain, preferNameSearch]);

  useEffect(() => {
    let cancelled = false;
    const cached = LogoCache.get(key);
    if (cached !== undefined) {
      setUrl(cached);
      return;
    }

    const q =
      domain && !preferNameSearch
        ? `domain=${encodeURIComponent(domain)}`
        : `name=${encodeURIComponent(name)}`;

    fetch(`/api/brand/logo?${q}`, { cache: 'no-store' })
      .then(async (res) => {
        if (!res.ok) return null;
        const data = await res.json().catch(() => null);
        return data?.url || null;
      })
      .catch(() => null)
      .then((logoUrl) => {
        if (cancelled) return;
        LogoCache.set(key, logoUrl);
        setUrl(logoUrl);
      });

    return () => {
      cancelled = true;
    };
  }, [key, name, domain, preferNameSearch]);

  // Fallback to first letter
  const fallbackText = name?.[0]?.toUpperCase() || '?';

  // Loading or no URL - use AntD Avatar with fallback
  if (url === undefined || !url) {
    return (
      <Avatar
        size={size}
        shape={shape}
        className={`${styles.avatar} ${className || ''}`}
        alt={`${name} logo`}
      >
        {fallbackText}
      </Avatar>
    );
  }

  // Have URL - use custom image with AntD Avatar as container
  return (
    <Avatar
      size={size}
      shape={shape}
      className={className}
      src={
        <Image
          src={url}
          alt={`${name} logo`}
          width={size}
          height={size}
          unoptimized
          style={{ objectFit: 'cover' }}
        />
      }
    />
  );
}

export default BrandAvatar;
