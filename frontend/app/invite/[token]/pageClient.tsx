"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { LoginButton } from "@/components/auth/login-button";
import { CheckCircle } from "lucide-react";

interface Props {
  token: string;
}

export default function InvitePageClient({ token }: Props) {
  const router = useRouter();
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    try {
      if (token) {
        window.localStorage.setItem("invite_token", token);
        setSaved(true);
      }
    } catch (_) {}
  }, [token]);

  return (
    <>
      <p className="text-white/80 text-center">
        {saved
          ? "Invitation saved. Continue with your provider to join this tenant."
          : "Preparing your invitation..."}
      </p>
      {saved && (
        <div className="flex flex-col items-center gap-3 w-full">
          <LoginButton className="w-full" size="lg" provider="google">
            Continue with Google
          </LoginButton>
          <LoginButton className="w-full" size="lg" variant="outline" provider="github">
            Continue with GitHub
          </LoginButton>
          <div className="w-full flex items-center gap-2 my-2">
            <div className="flex-1 h-px bg-white/10" />
            <span className="text-white/50 text-xs">or</span>
            <div className="flex-1 h-px bg-white/10" />
          </div>
          <div className="flex gap-2 w-full">
            <Button onClick={() => router.push("/auth/login")} variant="outline" className="w-1/2">
              Use Email Login
            </Button>
            <Button onClick={() => router.push("/auth/signup")} variant="outline" className="w-1/2">
              Email Signup
            </Button>
          </div>
          <Button variant="ghost" onClick={() => router.push("/")} className="text-white/70">
            Cancel
          </Button>
          <div className="flex items-center gap-2 text-green-400 text-sm mt-2">
            <CheckCircle className="h-4 w-4" />
            Invite token stored securely in your browser for this sign-in.
          </div>
        </div>
      )}
    </>
  );
}
