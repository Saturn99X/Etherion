'use client';

import { useState } from 'react';
import { createStyles } from 'antd-style';
import { Alert, Button, Form, Input } from 'antd';
import { Lock, Mail, User } from 'lucide-react';
import { Flexbox } from 'react-layout-kit';
import { signup } from '@etherion/bridge/auth';

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

interface SignupFormValues { name: string; email: string; password: string; confirm: string; subdomain?: string }
interface SignupFormProps { onSuccess?: () => void; onLoginClick?: () => void; inviteToken?: string }

export const SignupForm = ({ onSuccess, onLoginClick, inviteToken }: SignupFormProps) => {
  const { styles } = useStyles();
  const [form] = Form.useForm<SignupFormValues>();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleFinish = async (values: SignupFormValues) => {
    setLoading(true);
    setError(null);
    try {
      await signup({
        name: values.name,
        email: values.email,
        password: values.password,
        subdomain: values.subdomain,
        invite_token: inviteToken,
      });
      onSuccess?.();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Sign up failed. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Flexbox className={styles.container} gap={16}>
      <h2 className={styles.title}>Create your account</h2>
      {error && <Alert type="error" message={error} showIcon />}
      <Form form={form} layout="vertical" onFinish={handleFinish}>
        <Form.Item name="name" label="Name" rules={[{ required: true, message: 'Name required' }]}>
          <Input prefix={<User size={14} />} placeholder="Your name" autoComplete="name" />
        </Form.Item>
        <Form.Item name="email" label="Email" rules={[{ required: true, type: 'email', message: 'Valid email required' }]}>
          <Input prefix={<Mail size={14} />} placeholder="you@example.com" autoComplete="email" />
        </Form.Item>
        <Form.Item name="password" label="Password" rules={[{ required: true, min: 8, message: 'At least 8 characters' }]}>
          <Input.Password prefix={<Lock size={14} />} placeholder="Password" autoComplete="new-password" />
        </Form.Item>
        <Form.Item
          name="confirm"
          label="Confirm password"
          dependencies={['password']}
          rules={[
            { required: true, message: 'Please confirm password' },
            ({ getFieldValue }) => ({
              validator(_, value) {
                if (!value || getFieldValue('password') === value) return Promise.resolve();
                return Promise.reject(new Error('Passwords do not match'));
              },
            }),
          ]}
        >
          <Input.Password prefix={<Lock size={14} />} placeholder="Confirm password" autoComplete="new-password" />
        </Form.Item>
        <Form.Item>
          <Button type="primary" htmlType="submit" loading={loading} className={styles.submit}>
            Create account
          </Button>
        </Form.Item>
      </Form>
      {onLoginClick && (
        <Flexbox align="center">
          <Button type="link" onClick={onLoginClick}>
            Already have an account? Sign in
          </Button>
        </Flexbox>
      )}
    </Flexbox>
  );
};

export default SignupForm;
