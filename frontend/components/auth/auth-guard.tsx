"use client";

import { useEffect } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import Link from 'next/link';
import { useAuthStore } from '@/lib/stores/auth-store';
import { AuthService } from '@/lib/services/auth-service';
import { Card, CardContent } from '@/components/ui/card';
import { LoginButton } from './login-button';
import { Button } from '@/components/ui/button';
import { ThemeSwitcher } from '@/components/theme-switcher';
import { Loader2 } from 'lucide-react';

interface AuthGuardProps {
  children: React.ReactNode;
  fallback?: React.ReactNode;
}

export function AuthGuard({ children, fallback }: AuthGuardProps) {
  const router = useRouter();
  const pathname = usePathname();
  const { isAuthenticated, isLoading } = useAuthStore();
  // Dev-only auth bypass: controlled by runtime window.ENV to avoid leaking build-time env into production.
  const BYPASS = typeof window !== 'undefined' && (window as any).ENV?.NEXT_PUBLIC_BYPASS_AUTH === 'true';

  useEffect(() => {
    // Initialize auth state from stored token
    AuthService.initializeAuth();
  }, []);

  // In bypass mode, obtain a real JWT from the API so both HTTP and WebSocket links authenticate.
  useEffect(() => {
    if (!BYPASS) return;
    if (typeof window === 'undefined') return;
    const st = useAuthStore.getState();

    // Helper to decode a JWT without verification (payload only)
    const decodeJwt = (tok: string) => {
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
        const p = decodeJwt(existing);
        if (p && p.sub) {
          // Already have a real token
          if (!st.isAuthenticated) {
            st.login(existing, {
              user_id: p.sub,
              email: p.email || 'contact@etherionai.com',
              name: 'jon',
              provider: 'dev',
              profile_picture_url: undefined,
            });
          }
          window.localStorage.setItem('profile_completed', 'true');
          return;
        }
      }

      // Fallback to immediate local login to avoid blank UI while fetching
      if (!st.isAuthenticated) {
        st.login('dev-bypass', {
          user_id: 'dev:contact@etherionai.com',
          email: 'contact@etherionai.com',
          name: 'jon',
          provider: 'dev',
          profile_picture_url: undefined,
        });
        // Seed a temporary token so UI can render while fetching real token
        try { window.localStorage.setItem('auth_token', 'dev-bypass'); } catch {}
      }

      try {
        const apiBase = (window as any).ENV?.NEXT_PUBLIC_API_URL || process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080';
        const resp = await fetch(`${apiBase}/__dev/bypass-token`, { method: 'GET' });
        if (!resp.ok) throw new Error('bypass token fetch failed');
        const data = await resp.json();
        const token = data?.token as string | undefined;
        if (token) {
          window.localStorage.setItem('auth_token', token);
          const p = decodeJwt(token);
          if (p && p.sub) {
            st.login(token, {
              user_id: p.sub,
              email: p.email || 'contact@etherionai.com',
              name: 'jon',
              provider: 'dev',
              profile_picture_url: undefined,
            });
          }
          window.localStorage.setItem('profile_completed', 'true');
        }
      } catch {
        // Keep dev-bypass fallback; HTTP will be injected by API middleware; WS may remain unauthenticated
        window.localStorage.setItem('profile_completed', 'true');
      }
      // Safety: if token still missing after 5s, ensure a seed token exists to avoid spinner
      setTimeout(() => {
        try {
          const t = window.localStorage.getItem('auth_token');
          if (!t) window.localStorage.setItem('auth_token', 'dev-bypass');
        } catch {}
      }, 5000);
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

  // In bypass mode, never block rendering; background effects will acquire a token.
  if (BYPASS) {
    return <>{children}</>;
  }

  // Show loading state while checking authentication
  if (isLoading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="h-8 w-8 animate-spin text-cyan-400" />
          <p className="text-white/70">Loading...</p>
        </div>
      </div>
    );
  }

  // Show authentication required if not authenticated
  if (!isAuthenticated) {
    if (fallback) {
      return <>{fallback}</>;
    }

    return (
      <div className="min-h-screen bg-background flex items-center justify-center p-4">
        {/* Theme toggle */}
        <div className="absolute top-4 right-4 z-20">
          <ThemeSwitcher />
        </div>
        <div className="absolute inset-0 overflow-hidden pointer-events-none">
          <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-gradient-to-r from-purple-500/15 to-cyan-500/15 rounded-full blur-3xl float-animation" />
          <div
            className="absolute bottom-1/4 right-1/4 w-80 h-80 bg-gradient-to-r from-pink-500/15 to-blue-500/15 rounded-full blur-3xl float-animation"
            style={{ animationDelay: "2s" }}
          />
        </div>

        <Card className="w-full max-w-md glass-card border-white/20 relative z-10">
          <CardContent className="p-8">
            <div className="flex flex-col items-center gap-6">
              <div className="flex flex-col items-center gap-3">
                <div className="flex h-12 w-12 items-center justify-center rounded-lg chromatic-border glow-purple overflow-hidden">
                  <img src="/logo.png" alt="Etherion" className="h-10 w-10 object-contain" />
                </div>
                <div className="text-center">
                  <h1 className="text-2xl font-bold text-white mb-2">Welcome to Etherion</h1>
                  <p className="text-white/70">
                    Please sign in to access your autonomous AI workforce platform.
                  </p>
                </div>
              </div>

              {/* OAuth providers */}
              <div className="flex flex-col gap-3 w-full">
                <LoginButton className="w-full glass-button hover:glow-cyan transition-all duration-300" provider="google">
                  Sign in with Google
                </LoginButton>
                <LoginButton className="w-full" variant="outline" provider="github">
                  Sign in with GitHub
                </LoginButton>
              </div>

              {/* Divider */}
              <div className="w-full flex items-center gap-2">
                <div className="flex-1 h-px bg-white/10" />
                <span className="text-white/50 text-xs">or</span>
                <div className="flex-1 h-px bg-white/10" />
              </div>

              {/* Email auth links */}
              <div className="flex gap-2 w-full">
                <Link href="/auth/login" className="w-1/2">
                  <Button variant="outline" className="w-full">Email Login</Button>
                </Link>
                <Link href="/auth/signup" className="w-1/2">
                  <Button variant="outline" className="w-full">Email Sign Up</Button>
                </Link>
              </div>

              <div className="text-center text-sm text-white/50">
                <p>By signing in, you agree to our terms of service and privacy policy.</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  return <>{children}</>;
}
