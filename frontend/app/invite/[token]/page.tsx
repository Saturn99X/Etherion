import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { LoginButton } from "@/components/auth/login-button";
import { CheckCircle, Link as LinkIcon } from "lucide-react";
import InvitePageClient from "./pageClient";

export default async function InvitePage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-gradient-to-r from-purple-500/15 to-cyan-500/15 rounded-full blur-3xl" />
        <div className="absolute bottom-1/4 right-1/4 w-80 h-80 bg-gradient-to-r from-pink-500/15 to-blue-500/15 rounded-full blur-3xl" />
      </div>

      <Card className="w-full max-w-md glass-card border-white/20 relative z-10">
        <CardContent className="p-8 flex flex-col items-center gap-6">
          <div className="flex items-center gap-2 text-white">
            <LinkIcon className="h-5 w-5" />
            <h1 className="text-xl font-semibold">Tenant Invitation</h1>
          </div>
          <InvitePageClient token={token} />
        </CardContent>
      </Card>
    </div>
  );
}

// client component extracted to handle localStorage and navigation
// file colocated for simplicity
// ./pageClient.tsx
