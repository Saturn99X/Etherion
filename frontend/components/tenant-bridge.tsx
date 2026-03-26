"use client";

import React, { useEffect, useState } from "react";
import { UIEventProvider } from "@/hooks/use-ui-events";
import UIEventDispatcher from "@/components/ui/triggered-ui/ui-event-dispatcher";
import { useAuthStore } from "@/lib/stores/auth-store";
import { decodeJwt } from "@/lib/jwt";

export function TenantBridge({ children }: { children: React.ReactNode }) {
  const { token } = useAuthStore();
  const [tenantId, setTenantId] = useState<number | null>(null);

  useEffect(() => {
    try {
      const t = token || (typeof window !== "undefined" ? window.localStorage.getItem("auth_token") : null);
      if (!t) {
        setTenantId(null);
        return;
      }
      const payload = decodeJwt(t);
      const raw = (payload && ((payload as any).tenant_id ?? (payload as any).tenantId)) as number | string | undefined;
      const n = Number(raw);
      setTenantId(Number.isFinite(n) && n > 0 ? n : null);
    } catch {
      setTenantId(null);
    }
  }, [token]);

  return (
    <UIEventProvider tenantId={tenantId}>
      {children}
      {tenantId ? <UIEventDispatcher tenantId={tenantId} /> : null}
    </UIEventProvider>
  );
}
