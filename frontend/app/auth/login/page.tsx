"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ThemeSwitcher } from "@/components/theme-switcher";
import { LoginButton } from "@/components/auth/login-button";
import { PasswordAuthService } from "@/lib/services/auth-service";
import { decodeJwt } from "@/lib/jwt";

export default function PasswordLoginPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>("");
  const [inviteToken, setInviteToken] = useState<string | undefined>(undefined);

  useEffect(() => {
    // Read invite from URL or localStorage
    const invite = searchParams.get("invite");
    if (invite) {
      setInviteToken(invite);
      try { window.localStorage.setItem("invite_token", invite); } catch (_) {}
    } else {
      try {
        const stored = window.localStorage.getItem("invite_token") || undefined;
        setInviteToken(stored || undefined);
      } catch (_) {}
    }
  }, [searchParams]);
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const res = await PasswordAuthService.login(email, password, inviteToken);
      // Cross-subdomain redirect only when tenant_subdomain claim exists
      const token = res?.access_token || (typeof window !== 'undefined' ? window.localStorage.getItem('auth_token') : null);
      const host = typeof window !== 'undefined' ? window.location.host : '';
      if (token && (host.startsWith('app.') || host.split('.').length <= 2)) {
        const payload = decodeJwt(token);
        const tsub = (payload && ((payload as any).tenant_subdomain || (payload as any).tenantSubdomain)) as string | undefined;
        const isDefaultSub = (tsub || '').toLowerCase() === 'default';
        if (tsub && !isDefaultSub && tsub.trim().length > 0) {
          const domain = (host.includes('etherionai.com') ? 'etherionai.com' : (host.split('.').slice(-2).join('.')));
          const tenantHost = `${tsub}.${domain}`;
          const profileDone = (typeof window !== 'undefined' && window.localStorage.getItem('profile_completed') === 'true');
          const nextPath = profileDone ? '/' : '/onboarding/profile';
          const dest = `https://${tenantHost}/auth/accept#token=${encodeURIComponent(token)}&next=${encodeURIComponent(nextPath)}`;
          window.location.assign(dest);
          return;
        }
      }
      // Fallback: local route
      router.push("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
      <div className="absolute top-4 right-4 z-20">
        <ThemeSwitcher />
      </div>
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-gradient-to-r from-purple-500/15 to-cyan-500/15 rounded-full blur-3xl" />
        <div className="absolute bottom-1/4 right-1/4 w-80 h-80 bg-gradient-to-r from-pink-500/15 to-blue-500/15 rounded-full blur-3xl" />
      </div>

      <Card className="w-full max-w-md glass-card border-white/20 relative z-10">
        <CardContent className="p-8">
          <div className="flex items-center gap-3 mb-4">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg chromatic-border glow-purple overflow-hidden">
              <img src="/logo.png" alt="Etherion" className="h-6 w-6 object-contain" />
            </div>
            <h1 className="text-xl font-semibold text-white">Sign in with Email</h1>
          </div>
          <div className="space-y-2 mb-4">
            <div className="grid grid-cols-1 gap-2">
              <LoginButton className="w-full" size="lg" provider="google">Continue with Google</LoginButton>
              <LoginButton className="w-full" size="lg" variant="outline" provider="github">Continue with GitHub</LoginButton>
            </div>
            <div className="relative py-2">
              <div className="absolute inset-0 flex items-center" aria-hidden="true">
                <div className="w-full border-t border-white/20" />
              </div>
              <div className="relative flex justify-center">
                <span className="bg-transparent px-2 text-xs text-white/60">or continue with email</span>
              </div>
            </div>
          </div>
          {inviteToken && (
            <p className="text-xs text-green-400 mb-4">Invite token detected. You will join the invited tenant.</p>
          )}
          {error && (
            <p className="text-sm text-red-400 mb-3">{error}</p>
          )}
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="email" className="text-white/80">Email</Label>
              <Input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
            </div>
            <div className="space-y-2">
              <Label htmlFor="password" className="text-white/80">Password</Label>
              <Input id="password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
            </div>
            <Button type="submit" disabled={loading} className="w-full">
              {loading ? "Signing in..." : "Sign In"}
            </Button>
            <Button type="button" variant="ghost" onClick={() => router.push("/auth/signup")} className="w-full text-white/70">
              Need an account? Sign up
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
