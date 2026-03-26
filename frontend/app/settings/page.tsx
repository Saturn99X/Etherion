"use client";

import { useEffect, useMemo, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { AuthGuard } from "@/components/auth/auth-guard";
import { useMutation, useQuery } from "@apollo/client";
import { GET_USER_SETTINGS_QUERY, UPDATE_USER_SETTINGS_MUTATION } from "@/lib/graphql-operations";
import { Button } from "@/components/ui/button";

export default function SettingsPage() {
  const { data, loading, error, refetch } = useQuery(GET_USER_SETTINGS_QUERY);
  const [updateSettings, { loading: saving }] = useMutation(UPDATE_USER_SETTINGS_MUTATION);
  const [text, setText] = useState<string>("{}");
  const [parseError, setParseError] = useState<string | null>(null);
  const pretty = useMemo(() => {
    try {
      const v = data?.getUserSettings ?? {};
      return JSON.stringify(v, null, 2);
    } catch {
      return "{}";
    }
  }, [data]);

  useEffect(() => {
    if (!loading && !error) setText(pretty);
  }, [loading, error, pretty]);

  return (
    <AuthGuard>
      <AppShell>
        <div className="space-y-6">
          <h1 className="text-3xl font-bold tracking-tight">Settings</h1>
          {loading ? (
            <p className="text-muted-foreground">Loading…</p>
          ) : error ? (
            <p className="text-red-500 text-sm">Failed to load settings</p>
          ) : (
            <div className="space-y-3">
              <label className="block text-sm font-medium">User Settings (JSON)</label>
              <textarea
                className="w-full h-72 rounded border border-white/10 bg-black/30 p-2 font-mono text-sm"
                value={text}
                onChange={(e) => {
                  setText(e.target.value);
                  setParseError(null);
                }}
              />
              {parseError && <p className="text-xs text-amber-400">{parseError}</p>}
              <div className="flex gap-2">
                <Button
                  disabled={saving}
                  onClick={async () => {
                    try {
                      const obj = JSON.parse(text || "{}");
                      await updateSettings({ variables: { settings: obj } });
                      await refetch();
                    } catch (e: any) {
                      setParseError("Invalid JSON: " + (e?.message || String(e)));
                    }
                  }}
                >
                  {saving ? "Saving…" : "Save"}
                </Button>
                <Button variant="secondary" onClick={() => setText(pretty)}>Reset</Button>
              </div>
            </div>
          )}
        </div>
      </AppShell>
    </AuthGuard>
  );
}
