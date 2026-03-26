"use client";

import { useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Loader2, CheckCircle, XCircle } from 'lucide-react';
import { AuthService } from '@/lib/services/auth-service';
import { decodeJwt } from '@/lib/jwt';

export default function AuthCallbackPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
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
        // Enhanced error messages for common OAuth errors
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

      // Implement timeout protection
      let timeoutId: NodeJS.Timeout | null = null;
      let timedOut = false;

      try {
        // Set 15-second timeout
        const timeoutPromise = new Promise((_, reject) => {
          timeoutId = setTimeout(() => {
            timedOut = true;
            reject(new Error('TIMEOUT'));
          }, 15000);
        });

        // Decode provider + optional invite from OAuth state if present
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
          // fallback: localStorage provider and invite token
          try {
            const saved = typeof window !== 'undefined' ? window.localStorage.getItem('oauth_provider') : null;
            if (saved === 'github') provider = 'github';
          } catch (_) { }
        }
        // Fallback invite token from localStorage if still empty
        if (!inviteToken) {
          try { inviteToken = typeof window !== 'undefined' ? window.localStorage.getItem('invite_token') || undefined : undefined; } catch (_) { }
        }

        // Race between actual login and timeout
        const loginPromise = (async () => {
          if (provider === 'github') {
            return await AuthService.githubLogin(code, inviteToken);
          } else {
            return await AuthService.googleLogin(code, inviteToken);
          }
        })();

        const loginRes: any = await Promise.race([loginPromise, timeoutPromise]);

        // Clear timeout if we got here
        if (timeoutId) clearTimeout(timeoutId);

        setStatus('success');
        try {
          // Clear invite token and OAuth tracking after successful login
          if (typeof window !== 'undefined') {
            window.localStorage.removeItem('invite_token');
            window.localStorage.removeItem('oauth_provider');
            window.localStorage.removeItem('oauth_initiated_at');
            window.localStorage.removeItem('oauth_initiated_provider');
          }
        } catch (_) { }

        // Redirect based on tenant identity from JWT
        const token = loginRes?.access_token || (typeof window !== 'undefined' ? window.localStorage.getItem('auth_token') : null);
        let destination = '/';
        if (token) {
          const payload = decodeJwt(token);
          const tsub = (payload && (payload.tenant_subdomain || (payload as any).tenantSubdomain)) as string | undefined;
          const profileDone = (typeof window !== 'undefined' && window.localStorage.getItem('profile_completed') === 'true');
          const host = typeof window !== 'undefined' ? window.location.host : '';
          const domain = (host.includes('etherionai.com') ? 'etherionai.com' : (host.split('.').slice(-2).join('.')));
          const isDefaultSub = (tsub || '').toLowerCase() === 'default';
          // Only cross-subdomain if we have an explicit non-default tenant subdomain claim
          if (tsub && !isDefaultSub && tsub.trim().length > 0 && (host.startsWith('app.') || host === domain)) {
            const tenantHost = `${tsub}.${domain}`;
            const path = profileDone ? '/' : '/';
            const dest = `https://${tenantHost}/auth/accept#token=${encodeURIComponent(token)}&next=${encodeURIComponent(path)}`;
            window.location.assign(dest);
            return;
          }
          // Otherwise, stay on current host and go to post-auth onboarding wizard
          destination = '/onboarding/wizard';
        }
        setTimeout(() => { router.push(destination); }, 1200);
      } catch (error) {
        // Clear timeout
        if (timeoutId) clearTimeout(timeoutId);

        setStatus('error');

        if (timedOut || (error instanceof Error && error.message === 'TIMEOUT')) {
          setErrorMessage('Authentication timed out. Please try logging in again.');
        } else {
          const errorMsg = error instanceof Error ? error.message : 'Authentication failed';

          // Parse specific backend errors for user-friendly messages
          if (errorMsg.includes('not configured')) {
            setErrorMessage('OAuth is not properly configured. Please contact support.');
          } else if (errorMsg.includes('invalid') || errorMsg.includes('expired')) {
            setErrorMessage('Authorization code expired. Please try logging in again.');
          } else if (errorMsg.includes('redirect_uri')) {
            setErrorMessage('OAuth configuration mismatch. Please contact support.');
          } else {
            setErrorMessage(errorMsg);
          }
        }
      }
    };

    handleCallback();
  }, [searchParams, router]);

  const renderContent = () => {
    switch (status) {
      case 'loading':
        return (
          <div className="flex flex-col items-center gap-4">
            <Loader2 className="h-8 w-8 animate-spin text-cyan-400" />
            <h1 className="text-xl font-semibold text-white">Authenticating...</h1>
            <p className="text-white/70">Please wait while we verify your credentials.</p>
          </div>
        );

      case 'success':
        return (
          <div className="flex flex-col items-center gap-4">
            <CheckCircle className="h-8 w-8 text-green-400" />
            <h1 className="text-xl font-semibold text-white">Authentication Successful!</h1>
            <p className="text-white/70">Redirecting you to the application...</p>
          </div>
        );

      case 'error':
        return (
          <div className="flex flex-col items-center gap-4">
            <XCircle className="h-8 w-8 text-red-400" />
            <h1 className="text-xl font-semibold text-white">Authentication Failed</h1>
            <p className="text-white/70 text-center max-w-md">{errorMessage}</p>
            <div className="flex gap-2">
              <Button
                onClick={() => router.push('/auth/login')}
                className="glass-button hover:glow-cyan transition-all duration-300"
              >
                Try Again
              </Button>
              <Button
                variant="outline"
                onClick={() => router.push('/')}
                className="glass-button"
              >
                Return to Home
              </Button>
            </div>
          </div>
        );
    }
  };

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-gradient-to-r from-purple-500/15 to-cyan-500/15 rounded-full blur-3xl float-animation" />
        <div
          className="absolute bottom-1/4 right-1/4 w-80 h-80 bg-gradient-to-r from-pink-500/15 to-blue-500/15 rounded-full blur-3xl float-animation"
          style={{ animationDelay: "2s" }}
        />
      </div>

      <Card className="w-full max-w-md glass-card border-white/20 relative z-10">
        <CardContent className="p-8">
          {renderContent()}
        </CardContent>
      </Card>
    </div>
  );
}
