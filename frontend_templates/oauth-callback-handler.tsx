"""
Frontend OAuth Callback Handler Template

File: frontend / app / auth / callback / page.tsx

This shows the required logic for detecting new vs existing users.
Full implementation requires Next.js setup.
"""

'use client';

import { useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';

export default function OAuthCallbackPage() {
    const router = useRouter();
    const searchParams = useSearchParams();

    useEffect(() => {
        const handleCallback = async () => {
            const code = searchParams.get('code');
            const provider = searchParams.get('provider') || 'google';

            if (!code) {
                router.push('/auth/error?message=Missing authorization code');
                return;
            }

            // Exchange code for token via GraphQL
            const response = await fetch('/graphql', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    query: `
            mutation GoogleLogin($code: String!) {
              googleLogin(code: $code) {
                access_token
                user {
                  user_id
                  email
                  name
                }
              }
            }
          `,
                    variables: { code }
                })
            });

            const { data } = await response.json();
            const token = data.googleLogin.access_token;

            // Store token
            localStorage.setItem('access_token', token);

            // Parse JWT to check if user is new
            const tokenData = parseJwt(token);

            // Check if user has been onboarded
            if (!tokenData.onboarded || !tokenData.tenant_subdomain) {
                // New user - redirect to tenant naming wizard
                router.push('/onboarding/name-tenant');
            } else {
                // Existing user - redirect to their subdomain
                const subdomain = tokenData.tenant_subdomain;
                window.location.href = `https://${subdomain}.etherionai.com/dashboard`;
            }
        };

        handleCallback();
    }, []);

    return (
        <div className="flex items-center justify-center min-h-screen">
            <div className="text-center">
                <h2>Completing sign in...</h2>
                <p>Please wait while we set up your account.</p>
            </div>
        </div>
    );
}

function parseJwt(token: string) {
    const base64Url = token.split('.')[1];
    const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
    const jsonPayload = decodeURIComponent(
        atob(base64)
            .split('')
            .map(c => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2))
            .join('')
    );
    return JSON.parse(jsonPayload);
}
