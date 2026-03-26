'use client';

import React, { useEffect, useMemo, useState } from 'react';
import Image from 'next/image';
import { createStyles } from 'antd-style';

const useStyles = createStyles(({ token, css }) => ({
    fallback: css`
    display: flex;
    align-items: center;
    justify-content: center;
    background: ${token.colorFillQuaternary};
    color: ${token.colorTextSecondary};
    font-weight: 600;
  `,
}));

const LogoCache = new Map<string, string | null>();

export interface BrandAvatarProps {
    name: string;
    domain?: string;
    size?: number;
    className?: string;
    rounded?: boolean;
    preferNameSearch?: boolean;
}

export const BrandAvatar = ({
    name,
    domain,
    size = 32,
    className,
    rounded = true,
    preferNameSearch = false
}: BrandAvatarProps) => {
    const { styles, cx } = useStyles();
    const [url, setUrl] = useState<string | null | undefined>(undefined);

    const key = useMemo(() => {
        return (domain && !preferNameSearch) ? `d:${domain.toLowerCase()}` : `n:${name.toLowerCase()}`;
    }, [name, domain, preferNameSearch]);

    useEffect(() => {
        let cancelled = false;
        const cached = LogoCache.get(key);
        if (cached !== undefined) {
            setUrl(cached);
            return;
        }

        const q = (domain && !preferNameSearch) ? `domain=${encodeURIComponent(domain)}` : `name=${encodeURIComponent(name)}`;
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

        return () => { cancelled = true; };
    }, [key, name, domain, preferNameSearch]);

    const fallback = (
        <div
            className={cx(styles.fallback, className)}
            style={{
                width: size,
                height: size,
                borderRadius: rounded ? '50%' : '8px',
                fontSize: Math.max(10, Math.floor(size * 0.45))
            }}
            aria-label={`${name} logo`}
        >
            {name?.[0]?.toUpperCase() || '?'}
        </div>
    );

    if (url === undefined || !url) return fallback;

    return (
        <Image
            src={url}
            alt={`${name} logo`}
            width={size}
            height={size}
            className={className}
            style={{ borderRadius: rounded ? '50%' : '8px' }}
            unoptimized
        />
    );
};

export default BrandAvatar;
