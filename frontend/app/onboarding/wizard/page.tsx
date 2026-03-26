"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useApolloClient } from "@/components/apollo-provider";
import { CREATE_TENANT_MUTATION } from "@/lib/graphql-operations";
import { decodeJwt } from "@/lib/jwt";

export default function PostAuthOnboardingWizard() {
  const router = useRouter();
  const client = useApolloClient();

  const [step, setStep] = useState<1 | 2>(1);
  const [name, setName] = useState("");
  const [subdomain, setSubdomain] = useState("");
  const [adminEmail, setAdminEmail] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Resolve domain
  const domain = useMemo(() => {
    if (typeof window === "undefined") return "";
    const host = window.location.host;
    return host.includes("etherionai.com")
      ? "etherionai.com"
      : host.split(".").slice(-2).join(".");
  }, []);

  useEffect(() => {
    // Ensure user is authenticated and derive adminEmail from JWT
    try {
      const t = typeof window !== "undefined" ? window.localStorage.getItem("auth_token") : null;
      if (!t) {
        router.push("/auth/login");
        return;
      }
      const payload: any = decodeJwt(t);
      const email = payload?.email || payload?.user?.email || "";
      if (!email) {
        // Fallback to login if email missing
        router.push("/auth/login");
        return;
      }
      setAdminEmail(email);
    } catch {
      router.push("/auth/login");
    }
  }, [router]);

  const handleCreateTenant = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!name.trim() || !subdomain.trim()) {
      setError("Organization name and subdomain are required");
      return;
    }
    try {
      setLoading(true);
      const { data } = await client.mutate({
        mutation: CREATE_TENANT_MUTATION,
        variables: {
          tenant_input: {
            name: name.trim(),
            adminEmail: adminEmail.trim(),
            subdomain: subdomain.trim().toLowerCase(),
          },
        },
      });
      const t = data?.createTenant;
      if (t?.subdomain && t?.inviteToken) {
        setStep(2);
        // Short delay for step transition animation, then redirect
        setTimeout(() => {
          const dest = `https://${t.subdomain}.${domain}/invite/${t.inviteToken}`;
          window.location.assign(dest);
        }, 400);
        return;
      }
      setError("Failed to create tenant");
    } catch (e: any) {
      const msg = e?.message || "Failed to create tenant";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-gradient-to-r from-purple-500/15 to-cyan-500/15 rounded-full blur-3xl" />
        <div className="absolute bottom-1/4 right-1/4 w-80 h-80 bg-gradient-to-r from-pink-500/15 to-blue-500/15 rounded-full blur-3xl" />
      </div>

      <Card className="w-full max-w-xl glass-card border-white/20 relative z-10">
        <CardContent className="p-8 space-y-6">
          <div className="space-y-1">
            <div className="text-xs text-white/60">Step {step} of 2</div>
            <h1 className="text-2xl font-bold text-white">
              {step === 1 ? "Set up your organization" : "Creating your environment"}
            </h1>
            <p className="text-white/70 text-sm">
              {step === 1
                ? "Choose a name and subdomain. We'll reserve it and set everything up."
                : "Hold tight. Redirecting you to your tenant environment..."}
            </p>
          </div>

          {step === 1 && (
            <form onSubmit={handleCreateTenant} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="name" className="text-white/80">Organization name</Label>
                <Input id="name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Acme Inc." />
              </div>
              <div className="space-y-2">
                <Label htmlFor="subdomain" className="text-white/80">Desired subdomain</Label>
                <Input id="subdomain" value={subdomain} onChange={(e) => setSubdomain(e.target.value)} placeholder="acme" />
                <div className="text-xs text-white/50">Your app will live at https://{subdomain || "your-subdomain"}.{domain}</div>
              </div>
              <div className="space-y-2">
                <Label className="text-white/80">Admin email</Label>
                <Input value={adminEmail} disabled />
              </div>
              {error && <div className="text-destructive text-sm">{error}</div>}
              <div className="flex gap-2">
                <Button type="submit" disabled={loading} className="flex-1">
                  {loading ? "Creating..." : "Create tenant"}
                </Button>
                <Button type="button" variant="outline" className="flex-1" onClick={() => router.push("/")}>Cancel</Button>
              </div>
            </form>
          )}

          {step === 2 && (
            <div className="text-white/80 text-sm">
              We generated a secure invite and are redirecting you to your subdomain.
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
