"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Card, Result, Typography, Spin } from "antd";
import { LoadingOutlined } from "@ant-design/icons";
import { createStyles } from "antd-style";
import { AuthService } from "@etherion/lib/services/auth-service";

const { Text } = Typography;

const useStyles = createStyles(({ css, token }) => ({
    container: css`
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 24px;
    background: ${token.colorBgLayout};
  `,
    card: css`
    width: 100%;
    max-width: 440px;
    backdrop-filter: blur(10px);
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.1);
  `
}));

export default function AuthAcceptPage() {
    const router = useRouter();
    const { styles } = useStyles();
    const [status, setStatus] = useState<"loading" | "success" | "error">("loading");
    const [message, setMessage] = useState<string>("Authenticating...");

    useEffect(() => {
        const run = async () => {
            try {
                const hash = (typeof window !== "undefined" ? window.location.hash : "").replace(/^#/, "");
                const params = new URLSearchParams(hash);
                const token = params.get("token");
                const next = params.get("next") || "/";

                if (!token) {
                    setStatus("error");
                    setMessage("Missing token in URL fragment");
                    return;
                }

                try {
                    window.localStorage.setItem("auth_token", token);
                } catch { }

                await AuthService.initializeAuth();
                setStatus("success");
                setMessage("Authenticated. Redirecting...");

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
        <div className={styles.container}>
            <Card className={styles.card}>
                {status === "loading" && (
                    <Result
                        icon={<LoadingOutlined style={{ fontSize: 48 }} spin />}
                        title="Authenticating..."
                        subTitle="Please wait while we process your login."
                    />
                )}
                {status === "success" && (
                    <Result
                        status="success"
                        title="Authenticated"
                        subTitle="Redirecting you to your workspace..."
                    />
                )}
                {status === "error" && (
                    <Result
                        status="error"
                        title="Authentication Failed"
                        subTitle={message}
                        extra={[
                            <button key="retry" onClick={() => router.push('/auth/login')} className="ant-btn ant-btn-primary">
                                Back to Login
                            </button>
                        ]}
                    />
                )}
            </Card>
        </div>
    );
}
