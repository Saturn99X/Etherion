"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Card, Button, Input, Form, Typography, Space, Divider, message } from "antd";
import { createStyles } from "antd-style";
import { LoginButton } from "@/etherion/ui/auth/login-button";
import { PasswordAuthService } from "@etherion/lib/services/auth-service";
import { decodeJwt } from "@etherion/lib/jwt";

const { Title, Text, Link: AntLink } = Typography;

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
    max-width: 400px;
    backdrop-filter: blur(10px);
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.1);
  `,
  logoHeader: css`
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 24px;
  `,
  logoWrapper: css`
    width: 32px;
    height: 32px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 8px;
    background: ${token.colorBgContainer};
    border: 1px solid ${token.colorBorder};
    overflow: hidden;
  `,
  logo: css`
    width: 24px;
    height: 24px;
    object-fit: contain;
  `
}));

export default function PasswordSignupPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { styles } = useStyles();
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [inviteToken, setInviteToken] = useState<string | undefined>(undefined);

  useEffect(() => {
    // Read invite from URL or localStorage
    const invite = searchParams.get("invite");
    if (invite) {
      setInviteToken(invite);
      try { window.localStorage.setItem("invite_token", invite); } catch (_) { }
    } else {
      try {
        const stored = window.localStorage.getItem("invite_token") || undefined;
        setInviteToken(stored || undefined);
      } catch (_) { }
    }
  }, [searchParams]);

  const handleSubmit = async (values: any) => {
    setLoading(true);

    // Create timeout for 20 seconds
    let timeoutId: NodeJS.Timeout | null = null;
    let timedOut = false;

    try {
      const timeoutPromise = new Promise((_, reject) => {
        timeoutId = setTimeout(() => {
          timedOut = true;
          reject(new Error('TIMEOUT'));
        }, 20000); // 20-second timeout
      });

      const signupPromise = PasswordAuthService.signup(values.email, values.password, values.name, inviteToken);

      const res = await Promise.race([signupPromise, timeoutPromise]) as any;

      if (timeoutId) clearTimeout(timeoutId);

      const token = res?.access_token || (typeof window !== 'undefined' ? window.localStorage.getItem('auth_token') : null);
      const host = typeof window !== 'undefined' ? window.location.host : '';

      if (token && (host.startsWith('app.') || host.split('.').length <= 2)) {
        const payload = decodeJwt(token);
        const tsub = (payload && ((payload as any).tenant_subdomain || (payload as any).tenantSubdomain)) as string | undefined;
        const isDefaultSub = (tsub || '').toLowerCase() === 'default';

        if (tsub && !isDefaultSub && tsub.trim().length > 0) {
          const domain = (host.includes('etherionai.com') ? 'etherionai.com' : (host.split('.').slice(-2).join('.')));
          const tenantHost = `${tsub}.${domain}`;
          const profileDone = (typeof window !== 'undefined' && window.localStorage.getItem('profile_completed') === 'true');
          const nextPath = profileDone ? '/' : '/onboarding/profile';
          const dest = `https://${tenantHost}/auth/accept#token=${encodeURIComponent(token)}&next=${encodeURIComponent(nextPath)}`;
          window.location.assign(dest);
          return;
        }
      }

      router.push("/");
    } catch (err) {
      if (timeoutId) clearTimeout(timeoutId);

      if (timedOut || (err instanceof Error && err.message === 'TIMEOUT')) {
        message.error("Request timed out. Please check your connection and try again.");
      } else {
        message.error(err instanceof Error ? err.message : "Signup failed");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className={styles.container}>
      <Card className={styles.card}>
        <div className={styles.logoHeader}>
          <div className={styles.logoWrapper}>
            <img src="/logo.png" alt="Etherion" className={styles.logo} />
          </div>
          <Title level={4} style={{ margin: 0 }}>Create an account</Title>
        </div>

        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          <div className="grid grid-cols-1 gap-2">
            <LoginButton block size="large" provider="google">Continue with Google</LoginButton>
            <LoginButton block size="large" provider="github">Continue with GitHub</LoginButton>
          </div>

          <Divider plain>
            <Text type="secondary" style={{ fontSize: 12 }}>or continue with email</Text>
          </Divider>

          {inviteToken && (
            <Text type="success" style={{ fontSize: 12, display: 'block', marginBottom: 12 }}>
              Invite token detected. Your account will join the invited tenant.
            </Text>
          )}

          <Form
            form={form}
            layout="vertical"
            onFinish={handleSubmit}
            requiredMark={false}
          >
            <Form.Item
              label="Name"
              name="name"
            >
              <Input size="large" placeholder="Your name" />
            </Form.Item>

            <Form.Item
              label="Email"
              name="email"
              rules={[{ required: true, message: 'Please input your email!' }, { type: 'email', message: 'Please enter a valid email!' }]}
            >
              <Input size="large" placeholder="<EMAIL>" />
            </Form.Item>

            <Form.Item
              label="Password"
              name="password"
              rules={[{ required: true, message: 'Please input your password!' }]}
            >
              <Input.Password size="large" placeholder="••••••••" />
            </Form.Item>

            <Form.Item>
              <Button type="primary" htmlType="submit" size="large" block loading={loading}>
                Sign Up
              </Button>
            </Form.Item>
          </Form>

          <div style={{ textAlign: 'center' }}>
            <Text type="secondary">Already have an account? </Text>
            <AntLink onClick={() => router.push("/auth/login")}>Sign in</AntLink>
          </div>
        </Space>
      </Card>
    </div>
  );
}
