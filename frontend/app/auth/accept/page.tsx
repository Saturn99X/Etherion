"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Card, CardContent } from "@/components/ui/card";
import { Loader2, CheckCircle, XCircle } from "lucide-react";
import { AuthService } from "@/lib/services/auth-service";

export default function AuthAcceptPage() {
  const router = useRouter();
  const [status, setStatus] = useState<"loading" | "success" | "error">("loading");
  const [message, setMessage] = useState<string>("Authenticating...");

  useEffect(() => {
    const run = async () => {
      try {
        // Parse URL fragment: #token=...&next=/path
        const hash = (typeof window !== "undefined" ? window.location.hash : "").replace(/^#/, "");
        const params = new URLSearchParams(hash);
        const token = params.get("token");
        const next = params.get("next") || "/";
        if (!token) {
          setStatus("error");
          setMessage("Missing token in URL fragment");
          return;
        }
        // Store token and initialize auth
        try {
          window.localStorage.setItem("auth_token", token);
        } catch {}
        await AuthService.initializeAuth();
        setStatus("success");
        setMessage("Authenticated. Redirecting...");
        // Guard against open redirects: allow only same-origin path
        const safeNext = next.startsWith("/") ? next : "/";
        setTimeout(() => router.replace(safeNext), 500);
      } catch (e) {
        setStatus("error");
        setMessage(e instanceof Error ? e.message : "Authentication failed");
      }
    };
    run();
  }, [router]);

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
      <Card className="w-full max-w-md glass-card border-white/20 relative z-10">
        <CardContent className="p-8">
          {status === "loading" && (
            <div className="flex flex-col items-center gap-4">
              <Loader2 className="h-8 w-8 animate-spin text-cyan-400" />
              <h1 className="text-xl font-semibold text-white">{message}</h1>
            </div>
          )}
          {status === "success" && (
            <div className="flex flex-col items-center gap-4">
              <CheckCircle className="h-8 w-8 text-green-400" />
              <h1 className="text-xl font-semibold text-white">{message}</h1>
            </div>
          )}
          {status === "error" && (
            <div className="flex flex-col items-center gap-4">
              <XCircle className="h-8 w-8 text-red-400" />
              <h1 className="text-xl font-semibold text-white">{message}</h1>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
