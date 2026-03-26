'use client';

import { useEffect, useState } from 'react';
import {
    Card, Button, Input, Skeleton,
    Typography, Space, App, List,
    Empty, Badge, Tag, Row, Col
} from 'antd';
import { createStyles } from 'antd-style';
import { Flexbox } from 'react-layout-kit';
import {
    Download, RefreshCw, Image as ImageIcon,
    FileText, Search, Database, HardDrive,
    Clock
} from 'lucide-react';

import { useApolloClient } from '@etherion/ui/layout/apollo-provider';
import { LIST_REPOSITORY_ASSETS } from '@etherion/lib/graphql-operations';

const { Title, Text, Paragraph } = Typography;

const useStyles = createStyles(({ token, css }) => ({
    container: css`
    padding: ${token.paddingLG}px;
  `,
    header: css`
    margin-bottom: ${token.marginLG}px;
  `,
    searchBar: css`
    margin-bottom: ${token.marginLG}px;
    background: ${token.colorBgContainer};
    padding: ${token.paddingMD}px;
    border-radius: ${token.borderRadiusLG}px;
    border: 1px solid ${token.colorBorderSecondary};
  `,
    assetCard: css`
    height: 100%;
    transition: all 0.3s;
    background: ${token.colorBgContainer};
    border: 1px solid ${token.colorBorderSecondary};
    &:hover {
      border-color: ${token.colorPrimary};
      box-shadow: ${token.boxShadowTertiary};
    }
  `,
    assetIcon: css`
    padding: 8px;
    background: ${token.colorFillQuaternary};
    border-radius: ${token.borderRadius}px;
    color: ${token.colorPrimary};
    margin-right: 12px;
  `,
    assetMeta: css`
    font-size: 11px;
    color: ${token.colorTextDescription};
  `,
}));

interface RepoAsset {
    assetId: string;
    jobId?: string | null;
    filename: string;
    mimeType: string;
    sizeBytes: number;
    gcsUri: string;
    createdAt: string;
    downloadUrl?: string | null;
}

export const RepositoryBrowser = () => {
    const { styles, theme } = useStyles();
    const { message } = App.useApp();
    const client = useApolloClient();

    const [assets, setAssets] = useState<RepoAsset[]>([]);
    const [loading, setLoading] = useState(false);
    const [search, setSearch] = useState("");

    const loadAssets = async () => {
        try {
            setLoading(true);
            const { data } = await client.query({
                query: LIST_REPOSITORY_ASSETS,
                variables: { limit: 50, jobId: null, include_download: true },
                fetchPolicy: "network-only",
            });
            setAssets(data.listRepositoryAssets);
        } catch (e) {
            message.error("Failed to load repository assets");
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        loadAssets();
    }, []);

    const filtered = assets.filter(a => a.filename.toLowerCase().includes(search.toLowerCase()));

    return (
        <div className={styles.container}>
            <Flexbox className={styles.header} horizontal align="center" justify="space-between">
                <Space size={12}>
                    <Database size={24} color={theme.colorPrimary} />
                    <div>
                        <Title level={3} style={{ margin: 0 }}>Repository</Title>
                        <Text type="secondary">AI-generated assets and documents</Text>
                    </div>
                </Space>
                <Button icon={<RefreshCw size={14} />} onClick={loadAssets} loading={loading}>
                    Refresh
                </Button>
            </Flexbox>

            <div className={styles.searchBar}>
                <Input
                    prefix={<Search size={14} />}
                    placeholder="Search by filename..."
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    allowClear
                />
            </div>

            {loading ? (
                <Row gutter={[16, 16]}>
                    {[1, 2, 3, 4, 5, 6].map(i => (
                        <Col xs={24} sm={12} lg={8} key={i}>
                            <Card size="small"><Skeleton active /></Card>
                        </Col>
                    ))}
                </Row>
            ) : filtered.length === 0 ? (
                <Empty description="No assets found" />
            ) : (
                <Row gutter={[16, 16]}>
                    {filtered.map((asset) => (
                        <Col xs={24} sm={12} lg={8} key={asset.assetId}>
                            <Card
                                className={styles.assetCard}
                                size="small"
                                actions={[
                                    <Button
                                        key="download"
                                        type="link"
                                        size="small"
                                        icon={<Download size={14} />}
                                        href={asset.downloadUrl || '#'}
                                        target="_blank"
                                        disabled={!asset.downloadUrl}
                                    >
                                        Download
                                    </Button>
                                ]}
                            >
                                <Flexbox horizontal align="center" style={{ marginBottom: 16 }}>
                                    <div className={styles.assetIcon}>
                                        {asset.mimeType.startsWith("image/") ? (
                                            <ImageIcon size={20} />
                                        ) : (
                                            <FileText size={20} />
                                        )}
                                    </div>
                                    <div style={{ overflow: 'hidden' }}>
                                        <Text strong style={{ display: 'block' }} ellipsis title={asset.filename}>
                                            {asset.filename}
                                        </Text>
                                        <Text type="secondary" style={{ fontSize: 11 }}>
                                            {asset.mimeType}
                                        </Text>
                                    </div>
                                </Flexbox>

                                <Space direction="vertical" size={4} style={{ width: '100%' }}>
                                    <Flexbox horizontal justify="space-between" className={styles.assetMeta}>
                                        <Space size={4}><HardDrive size={12} /> {Math.round(asset.sizeBytes / 1024)} KB</Space>
                                        <Space size={4}><Clock size={12} /> {new Date(asset.createdAt).toLocaleDateString()}</Space>
                                    </Flexbox>
                                    <Tag style={{ fontSize: 10, marginTop: 8 }}>
                                        Job: {asset.jobId ? asset.jobId.slice(0, 8) : 'Manual'}
                                    </Tag>
                                </Space>
                            </Card>
                        </Col>
                    ))}
                </Row>
            )}
        </div>
    );
};

export default RepositoryBrowser;
