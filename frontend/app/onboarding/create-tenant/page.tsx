"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useApolloClient } from "@/components/apollo-provider";
import { CREATE_TENANT_MUTATION } from "@/lib/graphql-operations";

export default function CreateTenantPage() {
  const router = useRouter();
  const client = useApolloClient();

  const [name, setName] = useState("");
  const [subdomain, setSubdomain] = useState("");
  const [adminEmail, setAdminEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!name.trim() || !adminEmail.trim() || !password || !subdomain.trim()) {
      setError("All fields are required");
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
            password,
            subdomain: subdomain.trim().toLowerCase(),
          },
        },
      });
      const t = data?.createTenant;
      if (t?.subdomain && t?.inviteToken) {
        const host = typeof window !== 'undefined' ? window.location.host : '';
        const domain = host.includes('etherionai.com')
          ? 'etherionai.com'
          : host.split('.').slice(-2).join('.');
        const dest = `https://${t.subdomain}.${domain}/invite/${t.inviteToken}`;
        window.location.assign(dest);
        return;
      }
      setError("Failed to create tenant");
    } catch (e: any) {
      const msg = e?.message || 'Failed to create tenant';
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

      <Card className="w-full max-w-lg glass-card border-white/20 relative z-10">
        <CardContent className="p-8 space-y-6">
          <div className="space-y-2">
            <h1 className="text-2xl font-bold text-white">Create Organization</h1>
            <p className="text-white/70 text-sm">
              Choose your tenant name and subdomain. We'll generate a secure invite for the admin email and redirect you to it.
            </p>
          </div>
          <form onSubmit={onSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="name" className="text-white/80">Organization name</Label>
              <Input id="name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Acme Inc." />
            </div>
            <div className="space-y-2">
              <Label htmlFor="subdomain" className="text-white/80">Desired subdomain</Label>
              <Input id="subdomain" value={subdomain} onChange={(e) => setSubdomain(e.target.value)} placeholder="acme" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="email" className="text-white/80">Admin email</Label>
              <Input id="email" type="email" value={adminEmail} onChange={(e) => setAdminEmail(e.target.value)} placeholder="owner@acme.com" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="password" className="text-white/80">Admin password</Label>
              <Input id="password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Minimum 8 characters" />
            </div>
            {error && <div className="text-destructive text-sm">{error}</div>}
            <div className="flex gap-2">
              <Button type="submit" disabled={loading} className="flex-1">
                {loading ? 'Creating...' : 'Create & Continue'}
              </Button>
              <Button type="button" variant="outline" className="flex-1" onClick={() => router.push('/onboarding')}>
                Cancel
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
