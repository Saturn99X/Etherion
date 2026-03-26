'use client';

import { useState, useEffect } from 'react';
import {
    Button, Card, List, Badge, Typography,
    Modal, Form, Input, Space, App, Tag, Tooltip
} from 'antd';
import { createStyles } from 'antd-style';
import { Flexbox } from 'react-layout-kit';
import {
    Settings, Plus, CheckCircle, XCircle,
    AlertCircle, ShieldCheck, Zap, Info
} from 'lucide-react';

import { BrandAvatar } from '../layout/brand-avatar';
import { useApolloClient } from '@etherion/ui/layout/apollo-provider';
import { useAuthStore } from '@etherion/stores/auth-store';
import { decodeJwt } from '@etherion/lib/jwt';
import {
    GET_INTEGRATIONS_QUERY,
    CONNECT_INTEGRATION_MUTATION,
    TEST_INTEGRATION_MUTATION
} from '@etherion/lib/graphql-operations';

const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;

const useStyles = createStyles(({ token, css }) => ({
    container: css`
    padding: ${token.paddingLG}px;
  `,
    header: css`
    margin-bottom: ${token.marginLG}px;
  `,
    card: css`
    height: 100%;
    transition: all 0.3s;
    &:hover {
      box-shadow: ${token.boxShadowTertiary};
    }
  `,
    statusBadge: css`
    display: flex;
    align-items: center;
    gap: 4px;
    font-size: 12px;
    padding: 2px 8px;
    border-radius: 12px;
  `,
    capabilityTag: css`
    font-size: 11px;
    border-radius: 4px;
    padding: 0 4px;
  `,
}));

interface Integration {
    serviceName: string;
    status: string;
    lastConnected?: string;
    errorMessage?: string;
    capabilities: string[];
}

const SERVICE_META: Record<string, { name: string; domain: string }> = {
    openai: { name: 'OpenAI', domain: 'openai.com' },
    anthropic: { name: 'Anthropic', domain: 'anthropic.com' },
    supabase: { name: 'Supabase', domain: 'supabase.com' },
    stripe: { name: 'Stripe', domain: 'stripe.com' },
    github: { name: 'GitHub', domain: 'github.com' },
    slack: { name: 'Slack', domain: 'slack.com' },
    jira: { name: 'Jira', domain: 'atlassian.com' },
    hubspot: { name: 'HubSpot', domain: 'hubspot.com' },
    notion: { name: 'Notion', domain: 'notion.so' },
    resend: { name: 'Resend', domain: 'resend.com' },
    shopify: { name: 'Shopify', domain: 'shopify.com' },
    twitter: { name: 'Twitter (X)', domain: 'x.com' },
    redfin: { name: 'Redfin', domain: 'redfin.com' },
    zillow: { name: 'Zillow', domain: 'zillow.com' },
};

export const IntegrationHub = () => {
    const { styles, theme } = useStyles();
    const { message } = App.useApp();
    const client = useApolloClient();
    const { token } = useAuthStore();

    const [integrations, setIntegrations] = useState<Integration[]>([]);
    const [loading, setLoading] = useState(true);
    const [modalVisible, setModalVisible] = useState(false);
    const [selectedIntegration, setSelectedIntegration] = useState<Integration | null>(null);
    const [testingIntegration, setTestingIntegration] = useState<string | null>(null);
    const [form] = Form.useForm();

    const getTenantId = (): number | null => {
        try {
            const t = token || localStorage.getItem('auth_token');
            if (!t) return null;
            const payload = decodeJwt(t);
            const tid = (payload as any)?.tenant_id || (payload as any)?.tenantId;
            return tid ? Number(tid) : null;
        } catch { return null; }
    };

    const fetchIntegrations = async () => {
        try {
            setLoading(true);
            const tenantId = getTenantId();
            if (!tenantId) throw new Error('Missing tenant identity');

            const { data } = await client.query({
                query: GET_INTEGRATIONS_QUERY,
                variables: { tenant_id: tenantId }
            });
            setIntegrations(data.getIntegrations);
        } catch (err) {
            console.error('Failed to fetch integrations:', err);
            message.error('Failed to load integrations');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchIntegrations();
    }, []);

    const handleConnect = (integration: Integration) => {
        setSelectedIntegration(integration);
        form.resetFields();
        setModalVisible(true);
    };

    const handleSave = async (values: any) => {
        if (!selectedIntegration) return;
        try {
            const { data } = await client.mutate({
                mutation: CONNECT_INTEGRATION_MUTATION,
                variables: {
                    service_name: selectedIntegration.serviceName,
                    credentials: JSON.stringify({
                        api_key: values.apiKey,
                        other_credentials: values.otherCredentials
                    })
                }
            });

            const updated = data.connectIntegration;
            setIntegrations(prev => prev.map(i => i.serviceName === updated.serviceName ? { ...i, ...updated } : i));
            setModalVisible(false);
            message.success(`${selectedIntegration.serviceName} connected`);
        } catch (err) {
            message.error('Failed to connect integration');
        }
    };

    const handleTest = async (integration: Integration) => {
        try {
            setTestingIntegration(integration.serviceName);
            const { data } = await client.mutate({
                mutation: TEST_INTEGRATION_MUTATION,
                variables: { service_name: integration.serviceName }
            });

            if (data.testIntegration.success) {
                setIntegrations(prev => prev.map(i => i.serviceName === integration.serviceName ? { ...i, status: 'connected' } : i));
                message.success('Integration test successful');
            } else {
                message.error(`Test failed: ${data.testIntegration.errorMessage}`);
            }
        } catch (err) {
            message.error('Test execution failed');
        } finally {
            setTestingIntegration(null);
        }
    };

    const getStatusInfo = (status: string) => {
        switch (status.toLowerCase()) {
            case 'connected': return { icon: <CheckCircle size={14} />, color: 'success', label: 'Connected' };
            case 'error': return { icon: <XCircle size={14} />, color: 'error', label: 'Error' };
            case 'connecting': return { icon: <AlertCircle size={14} />, color: 'warning', label: 'Connecting' };
            default: return { icon: <AlertCircle size={14} />, color: 'default', label: 'Not Connected' };
        }
    };

    return (
        <div className={styles.container}>
            <Flexbox className={styles.header} horizontal align="center" justify="space-between">
                <div>
                    <Title level={2} style={{ margin: 0 }}>Integrations Hub</Title>
                    <Text type="secondary">Securely connect third-party platforms and AI providers</Text>
                </div>
                <Button icon={<ShieldCheck size={16} />} type="dashed">Security Log</Button>
            </Flexbox>

            <List
                loading={loading}
                grid={{ gutter: 24, xs: 1, sm: 2, md: 2, lg: 3, xl: 3, xxl: 4 }}
                dataSource={integrations}
                renderItem={(i) => {
                    const svcKey = i.serviceName.toLowerCase();
                    const meta = SERVICE_META[svcKey] || { name: i.serviceName, domain: undefined };
                    const status = getStatusInfo(i.status);

                    return (
                        <List.Item>
                            <Card
                                className={styles.card}
                                actions={[
                                    <Button
                                        key="action"
                                        type="link"
                                        icon={i.status === 'connected' ? <Settings size={14} /> : <Plus size={14} />}
                                        onClick={() => handleConnect(i)}
                                    >
                                        {i.status === 'connected' ? 'Manage' : 'Connect'}
                                    </Button>,
                                    i.status === 'connected' && (
                                        <Button
                                            key="test"
                                            type="link"
                                            onClick={() => handleTest(i)}
                                            loading={testingIntegration === i.serviceName}
                                        >
                                            Test
                                        </Button>
                                    )
                                ].filter(Boolean) as any}
                            >
                                <Flexbox gap={16}>
                                    <Flexbox horizontal align="center" gap={12}>
                                        <BrandAvatar name={meta.name} domain={meta.domain} size={40} rounded={false} />
                                        <Flexbox direction="vertical">
                                            <Text strong>{meta.name}</Text>
                                            <Space size={4}>
                                                <Tag color={status.color as any} icon={status.icon} style={{ margin: 0, fontSize: 10 }}>
                                                    {status.label}
                                                </Tag>
                                                {i.errorMessage && (
                                                    <Tooltip title={i.errorMessage}>
                                                        <Info size={12} style={{ cursor: 'help' }} />
                                                    </Tooltip>
                                                )}
                                            </Space>
                                        </Flexbox>
                                    </Flexbox>

                                    <div style={{ minHeight: 40 }}>
                                        {i.capabilities?.slice(0, 3).map((cap, idx) => (
                                            <Tag key={idx} className={styles.capabilityTag}>{cap}</Tag>
                                        ))}
                                        {i.capabilities?.length > 3 && (
                                            <Text type="secondary" style={{ fontSize: 11 }}>+{i.capabilities.length - 3}</Text>
                                        )}
                                    </div>
                                </Flexbox>
                            </Card>
                        </List.Item>
                    );
                }}
            />

            <Modal
                title={selectedIntegration ? `Configure ${SERVICE_META[selectedIntegration.serviceName.toLowerCase()]?.name || selectedIntegration.serviceName}` : 'Configure'}
                open={modalVisible}
                onOk={() => form.submit()}
                onCancel={() => setModalVisible(false)}
                destroyOnClose
            >
                <Form form={form} layout="vertical" onFinish={handleSave}>
                    <Form.Item
                        name="apiKey"
                        label="API Key / Token"
                        rules={[{ required: true, message: 'Identity key is required' }]}
                    >
                        <Input.Password placeholder="Enter your authentication key..." />
                    </Form.Item>
                    <Form.Item name="otherCredentials" label="Additional Configuration (JSON or Plaintext)">
                        <TextArea rows={4} placeholder="e.g. endpoint urls, specific organization IDs..." />
                    </Form.Item>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                        <ShieldCheck size={12} /> Your credentials are encrypted at rest and never shared.
                    </Text>
                </Form>
            </Modal>
        </div>
    );
};

export default IntegrationHub;
