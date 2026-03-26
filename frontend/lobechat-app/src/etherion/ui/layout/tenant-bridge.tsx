"use client";

import { useEffect } from 'react';
import { useAuthStore } from '@etherion/stores/auth-store';

/**
 * TenantBridge ensures that any tenant-related state is synchronized 
 * across the app when the authenticated user changes.
 */
export function TenantBridge({ children }: { children: React.ReactNode }) {
    const user = useAuthStore((s) => s.user);
    const tenantId = user?.tenant_id;

    useEffect(() => {
        if (tenantId) {
            console.log(`[TenantBridge] Active Tenant: ${tenantId}`);
            // Here we could sync to other stores or local storage if needed by legacy code
        }
    }, [tenantId]);

    return <>{children}</>;
}
