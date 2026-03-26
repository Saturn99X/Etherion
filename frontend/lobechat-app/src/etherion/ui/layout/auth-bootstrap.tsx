"use client";

import React, { useEffect, useState } from "react";
import { useAuthStore } from "@etherion/stores/auth-store";
import { decodeJwt } from "@etherion/lib/jwt";

function getEnv(key: string): string | undefined {
    if (typeof window !== "undefined") {
        return (window as any).ENV?.[key] ?? process.env[key];
    }
    return process.env[key];
}

export function AuthBootstrap({ children }: { children: React.ReactNode }) {
    const [ready, setReady] = useState(false);
    const login = useAuthStore((s) => s.login);

    useEffect(() => {
        let cancelled = false;
        async function ensureToken() {
            try {
                const existing = typeof window !== "undefined" ? window.localStorage.getItem("auth_token") : null;
                const BYPASS = getEnv("NEXT_PUBLIC_BYPASS_AUTH") === "true";

                if (existing) {
                    // Hydrate store and proceed
                    try {
                        const payload = existing ? decodeJwt(existing) : null;
                        const stubUser = {
                            user_id: (payload && (payload as any).sub) || "dev",
                            email: (payload && (payload as any).email) || "",
                            name: (payload && ((payload as any).name || (payload as any).email)) || "Dev User",
                            provider: "dev",
                        };
                        login(existing, stubUser as any);
                    } catch { }
                    if (!cancelled) setReady(true);
                    return;
                }

                if (!BYPASS) {
                    // In non-bypass mode, render immediately and let normal auth flow handle it
                    if (!cancelled) setReady(true);
                    return;
                }

                // Compute dev token endpoint from GraphQL HTTP endpoint
                const httpEndpoint = getEnv("NEXT_PUBLIC_GRAPHQL_ENDPOINT");
                const fallback = "http://localhost:8080/graphql";
                const resolvedHttp = httpEndpoint || fallback;
                let tokenUrl = "";
                try {
                    const u = new URL(resolvedHttp);
                    tokenUrl = `${u.origin}/__dev/bypass-token`;
                } catch {
                    tokenUrl = "/__dev/bypass-token";
                }

                // Fetch bypass token
                const resp = await fetch(tokenUrl, { method: "GET", credentials: "include" });
                if (!resp.ok) throw new Error(`bypass-token HTTP ${resp.status}`);
                const data = await resp.json().catch(() => ({}));
                const token: string | null = data?.token || null;
                if (!token) throw new Error("No token in bypass response");

                // Persist and hydrate
                window.localStorage.setItem("auth_token", token);
                try {
                    const payload = decodeJwt(token);
                    const stubUser = {
                        user_id: (payload && (payload as any).sub) || "dev",
                        email: (payload && (payload as any).email) || "",
                        name: (payload && ((payload as any).name || (payload as any).email)) || "Dev User",
                        provider: "dev",
                    };
                    login(token, stubUser as any);
                } catch { }

                if (!cancelled) setReady(true);
            } catch (e) {
                console.error("AuthBootstrap: failed to ensure token", e);
                // Allow app to render to avoid deadlock; components will show auth error states
                if (!cancelled) setReady(true);
            }
        }
        ensureToken();
        return () => { cancelled = true; };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []); // CRITICAL FIX: Empty deps array - login is a Zustand action, shouldn't retrigger

    if (!ready) {
        return null;
    }
    return <>{children}</>;
}
