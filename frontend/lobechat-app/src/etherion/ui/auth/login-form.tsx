'use client';

import { useState } from 'react';
import { createStyles } from 'antd-style';
import { Alert, Button, Form, Input } from 'antd';
import { Lock, Mail } from 'lucide-react';
import { Flexbox } from 'react-layout-kit';
import { login } from '@etherion/bridge/auth';

const useStyles = createStyles(({ token, css }) => ({
  container: css`
    width: 100%;
    max-width: 360px;
  `,
  title: css`
    font-size: ${token.fontSizeXL}px;
    font-weight: 600;
    color: ${token.colorText};
    margin-bottom: ${token.marginMD}px;
    text-align: center;
  `,
  submit: css`
    width: 100%;
  `,
}));

interface LoginFormValues { email: string; password: string }
interface LoginFormProps { onSuccess?: () => void; onSignupClick?: () => void }

export const LoginForm = ({ onSuccess, onSignupClick }: LoginFormProps) => {
  const { styles } = useStyles();
  const [form] = Form.useForm<LoginFormValues>();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleFinish = async (values: LoginFormValues) => {
    setLoading(true);
    setError(null);
    try {
      await login({ email: values.email, password: values.password });
      onSuccess?.();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Login failed. Check your credentials.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Flexbox className={styles.container} gap={16}>
      <h2 className={styles.title}>Sign in to Etherion</h2>
      {error && <Alert type="error" message={error} showIcon />}
      <Form form={form} layout="vertical" onFinish={handleFinish}>
        <Form.Item name="email" label="Email" rules={[{ required: true, type: 'email', message: 'Valid email required' }]}>
          <Input prefix={<Mail size={14} />} placeholder="you@example.com" autoComplete="email" />
        </Form.Item>
        <Form.Item name="password" label="Password" rules={[{ required: true, message: 'Password required' }]}>
          <Input.Password prefix={<Lock size={14} />} placeholder="Password" autoComplete="current-password" />
        </Form.Item>
        <Form.Item>
          <Button type="primary" htmlType="submit" loading={loading} className={styles.submit}>
            Sign in
          </Button>
        </Form.Item>
      </Form>
      {onSignupClick && (
        <Flexbox align="center">
          <Button type="link" onClick={onSignupClick}>
            Don&apos;t have an account? Sign up
          </Button>
        </Flexbox>
      )}
    </Flexbox>
  );
};

export default LoginForm;
