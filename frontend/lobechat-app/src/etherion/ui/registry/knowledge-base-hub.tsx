'use client';

import { useEffect, useRef, useState } from 'react';
import {
    Button, Card, List, Badge, Typography,
    Space, Tag, Empty, Skeleton, App,
    Divider, Progress
} from 'antd';
import { createStyles } from 'antd-style';
import { Flexbox } from 'react-layout-kit';
import {
    FileText, File, ImageIcon, Video,
    Music, Archive, CheckCircle, Upload,
    RefreshCw, Cloud, ExternalLink
} from 'lucide-react';

import { BrandAvatar } from '../layout/brand-avatar';
import { useApolloClient } from '@etherion/ui/layout/apollo-provider';
import { useAuthStore } from '@etherion/stores/auth-store';
import { decodeJwt } from '@etherion/lib/jwt';
import { LIST_REPOSITORY_ASSETS, GET_INTEGRATIONS_QUERY } from '@etherion/lib/graphql-operations';

const { Title, Text, Paragraph } = Typography;

const useStyles = createStyles(({ token, css }) => ({
    container: css`
    padding: ${token.paddingLG}px;
  `,
    header: css`
    margin-bottom: ${token.marginLG}px;
  `,
    sectionCard: css`
    margin-bottom: ${token.marginLG}px;
  `,
    sourceCard: css`
    padding: ${token.paddingSM}px;
    background: ${token.colorFillQuaternary};
    border-radius: ${token.borderRadius}px;
    border: 1px solid ${token.colorBorderSecondary};
  `,
    assetCard: css`
    height: 100%;
    transition: all 0.3s;
    &:hover {
      box-shadow: ${token.boxShadowTertiary};
    }
  `,
    iconWrapper: css`
    width: 40px;
    height: 40px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: ${token.colorFillQuaternary};
    border-radius: 8px;
    color: ${token.colorTextSecondary};
  `,
}));

interface RepoAsset {
    assetId: string;
    jobId?: string;
    filename: string;
    mimeType: string;
    sizeBytes: number;
    createdAt: string;
    downloadUrl?: string;
}

const getFileIcon = (mime: string) => {
    if (mime.startsWith('image/')) return <ImageIcon size={20} />;
    if (mime.startsWith('video/')) return <Video size={20} />;
    if (mime.startsWith('audio/')) return <Music size={20} />;
    if (mime === 'application/zip') return <Archive size={20} />;
    return <FileText size={20} />;
};

const PROVIDERS = ['slack', 'google', 'jira', 'hubspot', 'notion', 'shopify'] as const;
type Provider = typeof PROVIDERS[number];
const PROVIDER_META: Record<Provider, { name: string; domain: string }> = {
    slack: { name: 'Slack', domain: 'slack.com' },
    google: { name: 'Google', domain: 'google.com' },
    jira: { name: 'Jira', domain: 'atlassian.com' },
    hubspot: { name: 'HubSpot', domain: 'hubspot.com' },
    notion: { name: 'Notion', domain: 'notion.so' },
    shopify: { name: 'Shopify', domain: 'shopify.com' },
};

export const KnowledgeBaseHub = () => {
    const { styles, theme } = useStyles();
    const { message } = App.useApp();
    const client = useApolloClient();
    const { token } = useAuthStore();

    const [assets, setAssets] = useState<RepoAsset[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    type Integration = { serviceName: string; status: string };
    const [integrationMap, setIntegrationMap] = useState<Record<string, Integration | undefined>>({});
    const [intLoading, setIntLoading] = useState(false);
    const [isPolling, setIsPolling] = useState(false);
    const pollIntervalRef = useRef<any>(null);
    const pollTimeoutRef = useRef<any>(null);

    const getTenantId = (): number | null => {
        try {
            const t = token || localStorage.getItem('auth_token');
            if (!t) return null;
            const payload = decodeJwt(t);
            const tid = (payload as any)?.tenant_id || (payload as any)?.tenantId;
            return tid ? Number(tid) : null;
        } catch { return null; }
    };

    const getApiBase = (): string => {
        try {
            const v = (window as any).ENV?.NEXT_PUBLIC_API_URL || '';
            return v ? v.replace(/\/$/, '') : window.location.origin;
        } catch { return ''; }
    };

    const refreshIntegrations = async () => {
        try {
            setIntLoading(true);
            const tenantId = getTenantId();
            if (!tenantId) throw new Error('Missing tenant identity');

            const { data } = await client.query({
                query: GET_INTEGRATIONS_QUERY,
                variables: { tenant_id: tenantId },
                fetchPolicy: 'network-only',
            });

            const map: Record<string, Integration> = {};
            (data.getIntegrations || []).forEach((it: any) => {
                const key = it.serviceName.toLowerCase();
                if (PROVIDERS.includes(key as any)) map[key] = it;
            });
            setIntegrationMap(map);
        } catch (e) {
            console.error('Failed to load integrations', e);
        } finally {
            setIntLoading(false);
        }
    };

    const startOAuth = async (provider: Provider) => {
        try {
            const api = getApiBase();
            let url = `${api}/oauth/silo/${provider}/start?redirect_to=${encodeURIComponent(window.location.href)}`;
            if (provider === 'shopify') {
                const shop = window.prompt('Enter your Shopify shop domain');
                if (!shop) return;
                url += `&shop=${encodeURIComponent(shop)}`;
            }

            const res = await fetch(url, {
                headers: token ? { Authorization: `Bearer ${token}` } : {},
            });
            const data = await res.json();
            if (data?.authorize_url) {
                window.open(data.authorize_url, '_blank', 'noopener');
                if (!isPolling) {
                    setIsPolling(true);
                    refreshIntegrations();
                    pollIntervalRef.current = setInterval(refreshIntegrations, 3000);
                    pollTimeoutRef.current = setTimeout(() => {
                        clearInterval(pollIntervalRef.current);
                        setIsPolling(false);
                    }, 60000);
                }
            }
        } catch (e) {
            message.error('OAuth initiation failed');
        }
    };

    const fetchAssets = async () => {
        try {
            setLoading(true);
            const { data } = await client.query({
                query: LIST_REPOSITORY_ASSETS,
                variables: { limit: 24, include_download: false },
                fetchPolicy: 'network-only',
            });
            setAssets(data?.listRepositoryAssets || []);
        } catch (e) {
            setError('Failed to load knowledge assets');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchAssets();
        refreshIntegrations();
        return () => {
            if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
            if (pollTimeoutRef.current) clearTimeout(pollTimeoutRef.current);
        };
    }, []);

    return (
        <div className={styles.container}>
            <Flexbox className={styles.header} horizontal align="center" justify="space-between">
                <div>
                    <Title level={2} style={{ margin: 0 }}>Knowledge Base</Title>
                    <Text type="secondary">Manage repository assets and external data sources</Text>
                </div>
                <Button
                    type="primary"
                    icon={<Upload size={16} />}
                    onClick={() => message.info('Upload triggered')}
                >
                    Upload Asset
                </Button>
            </Flexbox>

            {/* Connection Sources */}
            <Card
                className={styles.sectionCard}
                title="Knowledge Sources"
                size="small"
                extra={<Button type="text" size="small" icon={<RefreshCw size={14} />} onClick={refreshIntegrations} loading={intLoading} />}
            >
                <List
                    grid={{ gutter: 16, xs: 1, sm: 2, lg: 3 }}
                    dataSource={PROVIDERS}
                    renderItem={(p) => {
                        const status = integrationMap[p]?.status?.toLowerCase() || 'disconnected';
                        const isConnected = status === 'connected';
                        const meta = PROVIDER_META[p];
                        return (
                            <List.Item>
                                <Flexbox horizontal align="center" justify="space-between" className={styles.sourceCard}>
                                    <Flexbox horizontal align="center" gap={12}>
                                        <BrandAvatar name={meta.name} domain={meta.domain} size={24} />
                                        <Text strong>{meta.name}</Text>
                                    </Flexbox>
                                    <Space>
                                        <Badge status={isConnected ? 'success' : 'default'} text={status} style={{ fontSize: 11 }} />
                                        <Button
                                            size="small"
                                            type={isConnected ? 'text' : 'primary'}
                                            onClick={() => startOAuth(p)}
                                        >
                                            {isConnected ? 'Reconnect' : 'Connect'}
                                        </Button>
                                    </Space>
                                </Flexbox>
                            </List.Item>
                        );
                    }}
                />
            </Card>

            <Divider orientation="left">Repository Assets</Divider>

            {loading ? (
                <List
                    grid={{ gutter: 24, xs: 1, sm: 2, lg: 3, xl: 4 }}
                    dataSource={[1, 2, 3, 4]}
                    renderItem={() => <List.Item><Card><Skeleton active /></Card></List.Item>}
                />
            ) : assets.length === 0 ? (
                <Empty description="No files in the knowledge base yet" />
            ) : (
                <List
                    grid={{ gutter: 24, xs: 1, sm: 2, lg: 3, xl: 4 }}
                    dataSource={assets}
                    renderItem={(asset) => (
                        <List.Item>
                            <Card
                                className={styles.assetCard}
                                size="small"
                                hoverable
                                actions={[
                                    <Button key="view" type="link" size="small">Metadata</Button>,
                                    <Button key="dl" type="link" size="small" icon={<ExternalLink size={12} />}>Open</Button>
                                ]}
                            >
                                <Flexbox gap={12}>
                                    <Flexbox horizontal align="center" justify="space-between">
                                        <div className={styles.iconWrapper}>
                                            {getFileIcon(asset.mimeType)}
                                        </div>
                                        <CheckCircle size={16} color={theme.colorSuccess} />
                                    </Flexbox>
                                    <div>
                                        <Text strong ellipsis style={{ display: 'block' }} title={asset.filename}>
                                            {asset.filename}
                                        </Text>
                                        <Flexbox direction="vertical" style={{ marginTop: 4 }}>
                                            <Text type="secondary" style={{ fontSize: 11 }}>
                                                {(asset.sizeBytes / 1024 / 1024).toFixed(2)} MB • {new Date(asset.createdAt).toLocaleDateString()}
                                            </Text>
                                            {asset.jobId && <Tag color="processing" style={{ marginTop: 4, width: 'fit-content', fontSize: 10 }}>Job: {asset.jobId.slice(0, 8)}</Tag>}
                                        </Flexbox>
                                    </div>
                                </Flexbox>
                            </Card>
                        </List.Item>
                    )}
                />
            )}
        </div>
    );
};

export default KnowledgeBaseHub;
