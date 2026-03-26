"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { ThemeSwitcher } from "@/components/theme-switcher";
import { useAuthStore } from "@/lib/stores/auth-store";

export default function ProfileOnboardingPage() {
  const router = useRouter();
  const { user, isAuthenticated } = useAuthStore();
  const [name, setName] = useState<string>(user?.name || "");
  const [email, setEmail] = useState<string>(user?.email || "");
  const [company, setCompany] = useState<string>("");
  const [role, setRole] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(false);

  useEffect(() => {
    if (!isAuthenticated) return;
    // If profile is already completed, bounce out
    const done = typeof window !== 'undefined' && window.localStorage.getItem('profile_completed') === 'true';
    if (done) router.replace('/');
  }, [isAuthenticated, router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    // Phase: no backend mutation yet; store locally for gating, backend profile endpoint can be wired later
    try {
      // Best-effort: persist to localStorage for now
      if (typeof window !== 'undefined') {
        window.localStorage.setItem('profile_completed', 'true');
        window.localStorage.setItem('profile_company', company || '');
        window.localStorage.setItem('profile_role', role || '');
        if (name && user) {
          // Update in-memory store so UI reflects changes
          useAuthStore.getState().updateUser({ name });
        }
      }
      router.replace('/');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
      <div className="absolute top-4 right-4 z-20"><ThemeSwitcher /></div>
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-gradient-to-r from-purple-500/15 to-cyan-500/15 rounded-full blur-3xl" />
        <div className="absolute bottom-1/4 right-1/4 w-80 h-80 bg-gradient-to-r from-pink-500/15 to-blue-500/15 rounded-full blur-3xl" />
      </div>
      <Card className="w-full max-w-lg glass-card border-white/20 relative z-10">
        <CardContent className="p-8 space-y-6">
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg chromatic-border glow-purple overflow-hidden">
              <img src="/logo.png" alt="Etherion" className="h-6 w-6 object-contain" />
            </div>
            <h1 className="text-xl font-semibold text-white">Complete your profile</h1>
          </div>
          <p className="text-white/70 text-sm">We need a few details to personalize your workspace.</p>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="name" className="text-white/80">Your name</Label>
              <Input id="name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Jane Doe" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="email" className="text-white/80">Email</Label>
              <Input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="company" className="text-white/80">Company</Label>
              <Input id="company" value={company} onChange={(e) => setCompany(e.target.value)} placeholder="Acme Inc." />
            </div>
            <div className="space-y-2">
              <Label htmlFor="role" className="text-white/80">Role</Label>
              <Input id="role" value={role} onChange={(e) => setRole(e.target.value)} placeholder="Founder, PM, Engineer..." />
            </div>
            <Button type="submit" disabled={loading} className="w-full">
              {loading ? 'Saving...' : 'Save & Continue'}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
