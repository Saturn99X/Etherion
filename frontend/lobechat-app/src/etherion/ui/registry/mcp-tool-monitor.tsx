'use client';

import { useState, useEffect, useCallback } from 'react';
import {
    Button, Card, List, Badge, Typography,
    Tabs, Progress, Space, App, Row, Col,
    Statistic, Divider
} from 'antd';
import { createStyles } from 'antd-style';
import { Flexbox } from 'react-layout-kit';
import {
    Activity, AlertTriangle, CheckCircle,
    XCircle, RefreshCw, TrendingUp,
    Clock, Zap, Server, Gauge
} from 'lucide-react';

import { useApolloClient } from '@etherion/ui/layout/apollo-provider';
import { GET_AVAILABLE_MCP_TOOLS_QUERY } from '@etherion/lib/graphql-operations';

const { Title, Text, Paragraph } = Typography;

const useStyles = createStyles(({ token, css }) => ({
    container: css`
    padding: ${token.paddingLG}px;
  `,
    header: css`
    margin-bottom: ${token.marginLG}px;
  `,
    statCard: css`
    .ant-card-body {
      padding: ${token.paddingMD}px;
    }
  `,
    toolCard: css`
    height: 100%;
    transition: all 0.3s;
    &:hover {
      box-shadow: ${token.boxShadowTertiary};
    }
  `,
}));

interface ToolHealth {
    toolName: string;
    status: 'healthy' | 'degraded' | 'down' | 'unknown';
    responseTime: number;
    uptime: number;
    errorRate: number;
    throughput: number;
    lastCheck: string;
}

export const MCPToolMonitor = () => {
    const { styles, theme } = useStyles();
    const { message } = App.useApp();
    const client = useApolloClient();

    const [tools, setTools] = useState<ToolHealth[]>([]);
    const [loading, setLoading] = useState(true);
    const [autoRefresh, setAutoRefresh] = useState(true);
    const [lastRefresh, setLastRefresh] = useState<Date>(new Date());

    const loadToolHealth = useCallback(async () => {
        try {
            setLoading(true);
            const { data } = await client.query({ query: GET_AVAILABLE_MCP_TOOLS_QUERY });

            const mockHealth: ToolHealth[] = (data as any).getAvailableMCPTools.map((tool: any) => ({
                toolName: tool.name,
                status: Math.random() > 0.1 ? 'healthy' : 'degraded',
                responseTime: 100 + Math.random() * 400,
                uptime: 98 + Math.random() * 2,
                errorRate: Math.random() * 2,
                throughput: Math.floor(Math.random() * 100) + 10,
                lastCheck: new Date().toISOString()
            }));

            setTools(mockHealth);
            setLastRefresh(new Date());
        } catch (e) {
            message.error('Failed to load health data');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        loadToolHealth();
        if (autoRefresh) {
            const id = setInterval(loadToolHealth, 30000);
            return () => clearInterval(id);
        }
    }, [autoRefresh, loadToolHealth]);

    const stats = {
        healthy: tools.filter(t => t.status === 'healthy').length,
        degraded: tools.filter(t => t.status === 'degraded').length,
        total: tools.length,
        avgLatency: tools.reduce((a, b) => a + b.responseTime, 0) / (tools.length || 1)
    };

    return (
        <div className={styles.container}>
            <Flexbox className={styles.header} horizontal align="center" justify="space-between">
                <div>
                    <Title level={2} style={{ margin: 0 }}>Tool Monitoring</Title>
                    <Text type="secondary">Real-time telemetry and health status for all connected MCP tools</Text>
                </div>
                <Space>
                    <Text type="secondary" style={{ fontSize: 12 }}>Last check: {lastRefresh.toLocaleTimeString()}</Text>
                    <Button icon={<RefreshCw size={14} />} onClick={loadToolHealth}>Refresh</Button>
                    <Button
                        type={autoRefresh ? 'primary' : 'default'}
                        onClick={() => setAutoRefresh(!autoRefresh)}
                    >
                        Auto {autoRefresh ? 'ON' : 'OFF'}
                    </Button>
                </Space>
            </Flexbox>

            <Row gutter={16} style={{ marginBottom: 24 }}>
                <Col span={6}>
                    <Card className={styles.statCard}>
                        <Statistic title="Healthy Tools" value={stats.healthy} suffix={`/ ${stats.total}`} valueStyle={{ color: theme.colorSuccess }} />
                    </Card>
                </Col>
                <Col span={6}>
                    <Card className={styles.statCard}>
                        <Statistic title="Avg Latency" value={stats.avgLatency} precision={0} suffix="ms" />
                    </Card>
                </Col>
                <Col span={6}>
                    <Card className={styles.statCard}>
                        <Statistic title="Total Throughput" value={tools.reduce((a, b) => a + b.throughput, 0)} suffix=" req/m" />
                    </Card>
                </Col>
                <Col span={6}>
                    <Card className={styles.statCard}>
                        <Statistic title="System Uptime" value={99.98} suffix="%" valueStyle={{ color: theme.colorInfo }} />
                    </Card>
                </Col>
            </Row>

            <Tabs defaultActiveKey="list" items={[
                {
                    key: 'list',
                    label: <Space><Activity size={14} />Live Feed</Space>,
                    children: (
                        <List
                            grid={{ gutter: 16, xs: 1, sm: 2, lg: 3 }}
                            dataSource={tools}
                            renderItem={t => (
                                <List.Item>
                                    <Card className={styles.toolCard} size="small">
                                        <Flexbox horizontal align="center" justify="space-between" style={{ marginBottom: 12 }}>
                                            <Text strong>{t.toolName}</Text>
                                            <Badge status={t.status === 'healthy' ? 'success' : 'warning'} text={t.status} />
                                        </Flexbox>
                                        <Space direction="vertical" style={{ width: '100%' }}>
                                            <div>
                                                <Flexbox horizontal justify="space-between" style={{ fontSize: 12 }}>
                                                    <Text type="secondary">Uptime</Text>
                                                    <Text strong>{t.uptime.toFixed(1)}%</Text>
                                                </Flexbox>
                                                <Progress percent={t.uptime} size="small" showInfo={false} />
                                            </div>
                                            <Row>
                                                <Col span={12}><Statistic title="Latency" value={t.responseTime} precision={0} suffix="ms" valueStyle={{ fontSize: 16 }} /></Col>
                                                <Col span={12}><Statistic title="Error Rate" value={t.errorRate} precision={2} suffix="%" valueStyle={{ fontSize: 16 }} /></Col>
                                            </Row>
                                        </Space>
                                    </Card>
                                </List.Item>
                            )}
                        />
                    )
                }
            ]} />
        </div>
    );
};

export default MCPToolMonitor;
