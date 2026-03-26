"use client";

import { useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Card, Button, Typography, Space, Spin, Result } from 'antd';
import { LoadingOutlined, CheckCircleFilled, CloseCircleFilled } from '@ant-design/icons';
import { createStyles } from 'antd-style';
import { AuthService } from '@etherion/lib/services/auth-service';
import { decodeJwt } from '@etherion/lib/jwt';

const { Text } = Typography;

const useStyles = createStyles(({ css, token }) => ({
    container: css`
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 24px;
    background: ${token.colorBgLayout};
  `,
    card: css`
    width: 100%;
    max-width: 440px;
    backdrop-filter: blur(10px);
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.1);
  `
}));

export default function AuthCallbackPage() {
    const router = useRouter();
    const searchParams = useSearchParams();
    const { styles } = useStyles();
    const [status, setStatus] = useState<'loading' | 'success' | 'error'>('loading');
    const [errorMessage, setErrorMessage] = useState<string>('');

    useEffect(() => {
        const handleCallback = async () => {
            const code = searchParams.get('code');
            const state = searchParams.get('state');
            const error = searchParams.get('error');
            const error_description = searchParams.get('error_description');

            if (error) {
                setStatus('error');
                if (error === 'access_denied') {
                    setErrorMessage('You denied access. Please try again and grant the necessary permissions.');
                } else if (error_description) {
                    setErrorMessage(`${error}: ${error_description}`);
                } else {
                    setErrorMessage(error);
                }
                return;
            }

            if (!code) {
                setStatus('error');
                setErrorMessage('No authorization code received. Please try logging in again.');
                return;
            }

            let timeoutId: NodeJS.Timeout | null = null;
            let timedOut = false;

            try {
                const timeoutPromise = new Promise((_, reject) => {
                    timeoutId = setTimeout(() => {
                        timedOut = true;
                        reject(new Error('TIMEOUT'));
                    }, 15000);
                });

                let provider: 'google' | 'github' = 'google';
                let inviteToken: string | undefined = undefined;
                try {
                    if (state) {
                        const raw = typeof atob !== 'undefined' ? atob(state) : Buffer.from(state, 'base64').toString('utf-8');
                        const parsed = JSON.parse(raw || '{}');
                        if (parsed && (parsed.p === 'google' || parsed.p === 'github')) provider = parsed.p;
                        if (parsed && typeof parsed.inv === 'string' && parsed.inv.length > 0) inviteToken = parsed.inv;
                    }
                } catch (_) {
                    try {
                        const saved = typeof window !== 'undefined' ? window.localStorage.getItem('oauth_provider') : null;
                        if (saved === 'github') provider = 'github';
                    } catch (_) { }
                }

                if (!inviteToken) {
                    try { inviteToken = typeof window !== 'undefined' ? window.localStorage.getItem('invite_token') || undefined : undefined; } catch (_) { }
                }

                const loginPromise = (async () => {
                    if (provider === 'github') {
                        return await AuthService.githubLogin(code, inviteToken);
                    } else {
                        return await AuthService.googleLogin(code, inviteToken);
                    }
                })();

                const loginRes: any = await Promise.race([loginPromise, timeoutPromise]);

                if (timeoutId) clearTimeout(timeoutId);

                setStatus('success');
                try {
                    if (typeof window !== 'undefined') {
                        window.localStorage.removeItem('invite_token');
                        window.localStorage.removeItem('oauth_provider');
                        window.localStorage.removeItem('oauth_initiated_at');
                        window.localStorage.removeItem('oauth_initiated_provider');
                    }
                } catch (_) { }

                const token = loginRes?.access_token || (typeof window !== 'undefined' ? window.localStorage.getItem('auth_token') : null);
                let destination = '/';
                if (token) {
                    const payload = decodeJwt(token);
                    const tsub = (payload && (payload.tenant_subdomain || (payload as any).tenantSubdomain)) as string | undefined;
                    const profileDone = (typeof window !== 'undefined' && window.localStorage.getItem('profile_completed') === 'true');
                    const host = typeof window !== 'undefined' ? window.location.host : '';
                    const domain = (host.includes('etherionai.com') ? 'etherionai.com' : (host.split('.').slice(-2).join('.')));
                    const isDefaultSub = (tsub || '').toLowerCase() === 'default';

                    if (tsub && !isDefaultSub && tsub.trim().length > 0 && (host.startsWith('app.') || host === domain)) {
                        const tenantHost = `${tsub}.${domain}`;
                        const path = '/'; // Keep it simple for shell
                        const dest = `https://${tenantHost}/auth/accept#token=${encodeURIComponent(token)}&next=${encodeURIComponent(path)}`;
                        window.location.assign(dest);
                        return;
                    }
                    destination = '/'; // Default destination in shell
                }
                setTimeout(() => { router.push(destination); }, 1200);
            } catch (error) {
                if (timeoutId) clearTimeout(timeoutId);
                setStatus('error');
                if (timedOut || (error instanceof Error && error.message === 'TIMEOUT')) {
                    setErrorMessage('Authentication timed out. Please try logging in again.');
                } else {
                    setErrorMessage(error instanceof Error ? error.message : 'Authentication failed');
                }
            }
        };

        handleCallback();
    }, [searchParams, router]);

    return (
        <div className={styles.container}>
            <Card className={styles.card}>
                {status === 'loading' && (
                    <Result
                        icon={<LoadingOutlined style={{ fontSize: 48 }} spin />}
                        title="Authenticating..."
                        subTitle="Please wait while we verify your credentials."
                    />
                )}

                {status === 'success' && (
                    <Result
                        status="success"
                        title="Authentication Successful!"
                        subTitle="Redirecting you to the application..."
                    />
                )}

                {status === 'error' && (
                    <Result
                        status="error"
                        title="Authentication Failed"
                        subTitle={errorMessage}
                        extra={[
                            <Button type="primary" key="retry" onClick={() => router.push('/auth/login')}>
                                Try Again
                            </Button>,
                            <Button key="home" onClick={() => router.push('/')}>
                                Return to Home
                            </Button>,
                        ]}
                    />
                )}
            </Card>
        </div>
    );
}
