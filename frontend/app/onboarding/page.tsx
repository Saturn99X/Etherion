"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { LoginButton } from "@/components/auth/login-button";

export default function OnboardingPage() {
  const router = useRouter();
  const [invite, setInvite] = useState<string>("");
  const [saved, setSaved] = useState<boolean>(false);

  useEffect(() => {
    try {
      const existing = window.localStorage.getItem("invite_token");
      if (existing) {
        setInvite(existing);
        setSaved(true);
      }
    } catch {}
  }, []);

  const saveInvite = () => {
    try {
      if (invite.trim()) {
        window.localStorage.setItem("invite_token", invite.trim());
        setSaved(true);
      }
    } catch {}
  };

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-gradient-to-r from-purple-500/15 to-cyan-500/15 rounded-full blur-3xl" />
        <div className="absolute bottom-1/4 right-1/4 w-80 h-80 bg-gradient-to-r from-pink-500/15 to-blue-500/15 rounded-full blur-3xl" />
      </div>

      <Card className="w-full max-w-lg glass-card border-white/20 relative z-10">
        <CardContent className="p-8 space-y-6">
          <div className="space-y-2">
            <h1 className="text-2xl font-bold text-white">Tenant Onboarding</h1>
            <p className="text-white/70 text-sm">
              New users must join via a secure invitation. Paste your invite token below, or open your invite link.
            </p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="invite" className="text-white/80">Invite token</Label>
            <div className="flex gap-2">
              <Input id="invite" value={invite} onChange={(e) => setInvite(e.target.value)} placeholder="paste invite token" />
              <Button onClick={saveInvite} variant="secondary">Save</Button>
            </div>
            {saved && <p className="text-green-400 text-xs">Saved. Continue with your provider.</p>}
          </div>

          <div className="flex flex-col gap-3">
            <LoginButton className="w-full" size="lg" provider="google">Continue with Google</LoginButton>
            <LoginButton className="w-full" size="lg" variant="outline" provider="github">Continue with GitHub</LoginButton>
          </div>

          <div className="text-xs text-white/60">
            Tip: If you don’t have an invite, contact your tenant admin. Single-tenant mode uses the default tenant only.
          </div>

          <div className="flex justify-end">
            <Button variant="ghost" onClick={() => router.push("/")}>Cancel</Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
