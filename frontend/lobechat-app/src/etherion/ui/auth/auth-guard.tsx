"use client";

import { useEffect } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import Link from 'next/link';
import { Card, Button, Spin, Typography, Space, Divider } from 'antd';
import { createStyles } from 'antd-style';
import { useAuthStore } from '@etherion/stores/auth-store';
import { AuthService } from '@etherion/lib/services/auth-service';
import { LoginButton } from './login-button';
import { Loader2 } from 'lucide-react';
import { Icon } from '@lobehub/ui';

const { Title, Text } = Typography;

const useStyles = createStyles(({ css, token }) => ({
    container: css`
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 24px;
    background: ${token.colorBgLayout};
    position: relative;
    overflow: hidden;
  `,
    background: css`
    position: absolute;
    inset: 0;
    pointer-events: none;
    z-index: 0;
  `,
    blob1: css`
    position: absolute;
    top: 25%;
    left: 25%;
    width: 400px;
    height: 400px;
    background: radial-gradient(circle, ${token.colorPrimaryBgHover} 0%, transparent 70%);
    filter: blur(80px);
    opacity: 0.15;
    animation: float 20s infinite alternate;
    @keyframes float {
      from { transform: translate(0, 0); }
      to { transform: translate(50px, 50px); }
    }
  `,
    blob2: css`
    position: absolute;
    bottom: 25%;
    right: 25%;
    width: 350px;
    height: 350px;
    background: radial-gradient(circle, ${token.colorInfoBgHover} 0%, transparent 70%);
    filter: blur(80px);
    opacity: 0.15;
    animation: float2 25s infinite alternate-reverse;
    @keyframes float2 {
      from { transform: translate(0, 0); }
      to { transform: translate(-40px, -60px); }
    }
  `,
    card: css`
    width: 100%;
    max-width: 400px;
    z-index: 10;
    backdrop-filter: blur(10px);
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.1);
  `,
    header: css`
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 16px;
    margin-bottom: 32px;
  `,
    logoWrapper: css`
    width: 48px;
    height: 48px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 12px;
    background: ${token.colorBgContainer};
    border: 1px solid ${token.colorBorder};
    box-shadow: 0 0 20px ${token.colorPrimaryShadow};
    overflow: hidden;
  `,
    logo: css`
    width: 40px;
    height: 40px;
    object-fit: contain;
  `,
    footer: css`
    margin-top: 24px;
    text-align: center;
    font-size: 12px;
    opacity: 0.5;
  `
}));

interface AuthGuardProps {
    children: React.ReactNode;
    fallback?: React.ReactNode;
}

export function AuthGuard({ children, fallback }: AuthGuardProps) {
    const router = useRouter();
    const pathname = usePathname();
    const { styles } = useStyles();
    const { isAuthenticated, isLoading } = useAuthStore();

    // Dev-only auth bypass
    const BYPASS = typeof window !== 'undefined' && (window as any).ENV?.NEXT_PUBLIC_BYPASS_AUTH === 'true';

    useEffect(() => {
        // Initialize auth state from stored token
        AuthService.initializeAuth();
    }, []);

    // Bypass logic (port from original)
    useEffect(() => {
        if (!BYPASS) return;
        if (typeof window === 'undefined') return;
        const st = useAuthStore.getState();

        const decodeJwtLocal = (tok: string) => {
            try {
                const [, payload] = tok.split('.') as [string, string, string];
                const json = typeof atob !== 'undefined' ? atob(payload) : Buffer.from(payload, 'base64').toString('utf-8');
                return JSON.parse(json);
            } catch {
                return null;
            }
        };

        const ensureToken = async () => {
            const existing = window.localStorage.getItem('auth_token');
            if (existing) {
                const p = decodeJwtLocal(existing);
                if (p && p.sub) {
                    if (!st.isAuthenticated) {
                        st.login(existing, {
                            user_id: p.sub,
                            email: p.email || '<EMAIL>',
                            name: 'jon',
                            provider: 'dev',
                        });
                    }
                    window.localStorage.setItem('profile_completed', 'true');
                    return;
                }
            }

            if (!st.isAuthenticated) {
                st.login('dev-bypass', {
                    user_id: 'dev:<EMAIL>',
                    email: '<EMAIL>',
                    name: 'jon',
                    provider: 'dev',
                });
                try { window.localStorage.setItem('auth_token', 'dev-bypass'); } catch { }
            }

            try {
                const apiBase = (window as any).ENV?.NEXT_PUBLIC_API_URL || process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080';
                const resp = await fetch(`${apiBase}/__dev/bypass-token`, { method: 'GET' });
                if (!resp.ok) throw new Error('bypass token fetch failed');
                const data = await resp.json();
                const token = data?.token as string | undefined;
                if (token) {
                    window.localStorage.setItem('auth_token', token);
                    const p = decodeJwtLocal(token);
                    if (p && p.sub) {
                        st.login(token, {
                            user_id: p.sub,
                            email: p.email || '<EMAIL>',
                            name: 'jon',
                            provider: 'dev',
                        });
                    }
                    window.localStorage.setItem('profile_completed', 'true');
                }
            } catch {
                window.localStorage.setItem('profile_completed', 'true');
            }
        };

        ensureToken();
    }, [BYPASS]);

    useEffect(() => {
        if (typeof window === 'undefined') return;
        if (!isAuthenticated) return;
        const profileDone = window.localStorage.getItem('profile_completed') === 'true';
        if (!profileDone && pathname !== '/onboarding/profile') {
            router.push('/onboarding/profile');
        }
    }, [isAuthenticated, pathname, router]);

    if (BYPASS) {
        return <>{children}</>;
    }

    if (isLoading) {
        return (
            <div className={styles.container}>
                <Space direction="vertical" align="center" size="large">
                    <Spin indicator={<Icon icon={Loader2} spin size={32} />} />
                    <Text type="secondary">Loading...</Text>
                </Space>
            </div>
        );
    }

    if (!isAuthenticated) {
        // Skip fallback UI for auth routes to avoid double login UI
        const isAuthRoute = pathname?.startsWith('/auth/');
        if (isAuthRoute) {
            return <>{children}</>;
        }

        if (fallback) {
            return <>{fallback}</>;
        }

        return (
            <div className={styles.container}>
                <div className={styles.background}>
                    <div className={styles.blob1} />
                    <div className={styles.blob2} />
                </div>

                <Card className={styles.card}>
                    <div className={styles.header}>
                        <div className={styles.logoWrapper}>
                            <img src="/logo.png" alt="Etherion" className={styles.logo} />
                        </div>
                        <div style={{ textAlign: 'center' }}>
                            <Title level={3} style={{ margin: 0 }}>Welcome to Etherion</Title>
                            <Text type="secondary"> Please sign in to access your platform.</Text>
                        </div>
                    </div>

                    <Space direction="vertical" style={{ width: '100%' }} size="middle">
                        <LoginButton provider="google" block size="large" type="primary">
                            Sign in with Google
                        </LoginButton>
                        <LoginButton provider="github" block size="large">
                            Sign in with GitHub
                        </LoginButton>

                        <Divider plain>
                            <Text type="secondary" style={{ fontSize: 12 }}>or continue with email</Text>
                        </Divider>

                        <Space style={{ width: '100%' }}>
                            <Link href="/auth/login" style={{ flex: 1 }}>
                                <Button block>Email Login</Button>
                            </Link>
                            <Link href="/auth/signup" style={{ flex: 1 }}>
                                <Button block>Email Sign Up</Button>
                            </Link>
                        </Space>

                        <div className={styles.footer}>
                            By signing in, you agree to our terms of service and privacy policy.
                        </div>
                    </Space>
                </Card>
            </div>
        );
    }

    return <>{children}</>;
}
