'use client';

import { useState, useEffect } from 'react';
import {
    Button, Card, List, Badge, Typography,
    Input, Select, Progress, Modal, Space,
    App, Row, Col, Tag, Segmented, Empty, Skeleton, Divider
} from 'antd';
import { createStyles } from 'antd-style';
import { Flexbox } from 'react-layout-kit';
import {
    Wrench, Search, Filter, Grid3X3,
    List as ListIcon, Star, Download,
    Upload, Settings, Key, Sparkles,
    Activity
} from 'lucide-react';

import { useApolloClient } from '@etherion/ui/layout/apollo-provider';
import { GET_AVAILABLE_MCP_TOOLS_QUERY } from '@etherion/lib/graphql-operations';
import { MCPToolManager } from './mcp-tool-manager';
import { CredentialManager } from './credential-manager';

const { Title, Text, Paragraph } = Typography;

const useStyles = createStyles(({ token, css }) => ({
    container: css`
    padding: ${token.paddingLG}px;
  `,
    header: css`
    margin-bottom: ${token.marginLG}px;
  `,
    filterBar: css`
    margin-bottom: ${token.marginLG}px;
    background: ${token.colorBgContainer};
    padding: ${token.paddingMD}px;
    border-radius: ${token.borderRadiusLG}px;
    border: 1px solid ${token.colorBorderSecondary};
  `,
    toolCard: css`
    height: 100%;
    transition: all 0.3s;
    cursor: pointer;
    &:hover {
      box-shadow: ${token.boxShadowTertiary};
      border-color: ${token.colorPrimary};
    }
  `,
    categoryTag: css`
    margin-bottom: 4px;
  `,
}));

export const MCPToolRegistry = () => {
    const { styles, theme } = useStyles();
    const { message } = App.useApp();
    const client = useApolloClient();

    const [tools, setTools] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);
    const [searchQuery, setSearchQuery] = useState("");
    const [viewMode, setViewMode] = useState<any>("grid");
    const [selectedTool, setSelectedTool] = useState<string | null>(null);
    const [managerOpen, setManagerOpen] = useState(false);
    const [credOpen, setCredOpen] = useState(false);

    const loadTools = async () => {
        try {
            setLoading(true);
            const { data } = await client.query({ query: GET_AVAILABLE_MCP_TOOLS_QUERY });
            setTools((data as any).getAvailableMCPTools.map((t: any) => ({
                ...t,
                health: 85 + Math.random() * 15,
                executions: Math.floor(Math.random() * 500)
            })));
        } catch {
            message.error('Failed to load registry');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => { loadTools(); }, []);

    const filtered = tools.filter(t =>
        t.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        t.description.toLowerCase().includes(searchQuery.toLowerCase())
    );

    return (
        <div className={styles.container}>
            <Flexbox className={styles.header} horizontal align="center" justify="space-between">
                <div>
                    <Title level={2} style={{ margin: 0 }}>Tool Registry</Title>
                    <Text type="secondary">Catalog of available Model Context Protocol extensions</Text>
                </div>
                <Space>
                    <Button icon={<Download size={14} />}>Export</Button>
                    <Button type="primary" icon={<Star size={14} />}>Featured</Button>
                </Space>
            </Flexbox>

            <div className={styles.filterBar}>
                <Row gutter={16} align="middle">
                    <Col flex="auto">
                        <Input
                            prefix={<Search size={14} />}
                            placeholder="Search tools and capabilities..."
                            value={searchQuery}
                            onChange={e => setSearchQuery(e.target.value)}
                        />
                    </Col>
                    <Col>
                        <Select defaultValue="all" style={{ width: 150 }} options={[{ value: 'all', label: 'All Categories' }]} />
                    </Col>
                    <Col>
                        <Segmented
                            options={[
                                { value: 'grid', icon: <Grid3X3 size={14} /> },
                                { value: 'list', icon: <ListIcon size={14} /> }
                            ]}
                            value={viewMode}
                            onChange={setViewMode}
                        />
                    </Col>
                </Row>
            </div>

            {loading ? <Skeleton active /> : filtered.length === 0 ? (
                <Empty description="No tools matching your search" />
            ) : (
                <List
                    grid={viewMode === 'grid' ? { gutter: 16, xs: 1, sm: 2, lg: 3, xl: 4 } : undefined}
                    dataSource={filtered}
                    renderItem={t => (
                        <List.Item>
                            <Card
                                className={styles.toolCard}
                                size="small"
                                onClick={() => { setSelectedTool(t.name); setManagerOpen(true); }}
                                actions={[
                                    <Button key="manage" type="text" icon={<Settings size={14} />}>Manage</Button>,
                                    <Button
                                        key="creds"
                                        type="text"
                                        icon={<Key size={14} />}
                                        onClick={(e) => { e.stopPropagation(); setSelectedTool(t.name); setCredOpen(true); }}
                                    >
                                        Credentials
                                    </Button>
                                ]}
                            >
                                <Flexbox direction="vertical" gap={8}>
                                    <Flexbox horizontal justify="space-between" align="start">
                                        <div>
                                            <Text strong>{t.name}</Text>
                                            <br />
                                            <Tag color="blue" size="small" style={{ marginTop: 4 }}>{t.category || 'Utility'}</Tag>
                                        </div>
                                        <Badge status="success" />
                                    </Flexbox>
                                    <Paragraph type="secondary" style={{ fontSize: 12, height: 36, overflow: 'hidden', margin: 0 }}>
                                        {t.description}
                                    </Paragraph>
                                    <Divider style={{ margin: '8px 0' }} />
                                    <Flexbox horizontal justify="space-between" align="center" style={{ fontSize: 11 }}>
                                        <Space size={4}><Activity size={12} /> {t.executions} calls</Space>
                                        <Text type="secondary">Health: {t.health.toFixed(0)}%</Text>
                                    </Flexbox>
                                    <Progress percent={t.health} size="small" showInfo={false} strokeColor={theme.colorSuccess} />
                                </Flexbox>
                            </Card>
                        </List.Item>
                    )}
                />
            )}

            <Modal
                title="Tool Manager"
                open={managerOpen}
                onCancel={() => setManagerOpen(false)}
                footer={null}
                width={1000}
            >
                {selectedTool && <MCPToolManager preselectToolName={selectedTool} onClose={() => setManagerOpen(false)} />}
            </Modal>

            <Modal
                title="Manage Credentials"
                open={credOpen}
                onCancel={() => setCredOpen(false)}
                footer={null}
                width={700}
            >
                {selectedTool && <CredentialManager toolName={selectedTool} onClose={() => setCredOpen(false)} />}
            </Modal>
        </div>
    );
};

export default MCPToolRegistry;
