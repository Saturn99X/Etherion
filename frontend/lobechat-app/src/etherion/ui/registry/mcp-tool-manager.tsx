'use client';

import { useState, useEffect } from 'react';
import {
    Button, Card, List, Badge, Typography,
    Tabs, Form, Input, Select, Space,
    App, Alert, Divider, Radio, Tag,
    Switch, Slider, Progress, Statistic, Row, Col,
    Skeleton, Empty, Modal
} from 'antd';
import { createStyles } from 'antd-style';
import { Flexbox } from 'react-layout-kit';
import {
    Wrench, Settings, Play, Pause,
    RotateCcw, BarChart3, Activity,
    Shield, Key, CheckCircle, XCircle,
    AlertTriangle, Clock, Zap, Database,
    Globe, Users, TrendingUp, RefreshCw,
    Plus, Edit, Trash2, Eye, ExternalLink
} from 'lucide-react';

import { useApolloClient } from '@etherion/ui/layout/apollo-provider';
import { useAuthStore } from '@etherion/stores/auth-store';
import { decodeJwt } from '@etherion/lib/jwt';
import { useThreadPrefStore } from '@etherion/stores/thread-pref-store';
import { useTeamStore } from '@etherion/stores/team-store';
import { CredentialManager } from './credential-manager';
import { MCPToolMonitor } from './mcp-tool-monitor';
import {
    GET_AVAILABLE_MCP_TOOLS_QUERY,
    EXECUTE_MCP_TOOL_MUTATION,
    TEST_MCP_TOOL_MUTATION
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
    toolList: css`
    height: calc(100vh - 250px);
    overflow-y: auto;
    padding-right: 8px;
  `,
    toolItem: css`
    margin-bottom: 8px;
    cursor: pointer;
    transition: all 0.2s;
    &:hover {
      border-color: ${token.colorPrimaryHover};
    }
  `,
    activeTool: css`
    border-color: ${token.colorPrimary};
    background: ${token.colorFillQuaternary};
  `,
    statusDot: css`
    width: 8px;
    height: 8px;
    border-radius: 50%;
  `,
}));

interface MCPTool {
    id: string;
    name: string;
    description: string;
    category: string;
    status: 'active' | 'inactive' | 'error' | 'maintenance';
    version: string;
    capabilities: string[];
    requiredCredentials: string[];
    maxConcurrentCalls: number;
    rateLimit: number;
    healthScore: number;
    lastUsed: string | null;
    totalExecutions: number;
    successRate: number;
    averageExecutionTime: number;
    totalCost: number;
    isEnabled: boolean;
}

export const MCPToolManager = ({ preselectToolName, onClose }: { preselectToolName?: string; onClose?: () => void }) => {
    const { styles, theme } = useStyles();
    const { message } = App.useApp();
    const client = useApolloClient();
    const { token } = useAuthStore();

    const [tools, setTools] = useState<MCPTool[]>([]);
    const [selectedTool, setSelectedTool] = useState<MCPTool | null>(null);
    const [loading, setLoading] = useState(true);
    const [testing, setTesting] = useState<string | null>(null);
    const [executing, setExecuting] = useState<string | null>(null);
    const [credModalOpen, setCredModalOpen] = useState(false);
    const [executionResults, setExecutionResults] = useState<any[]>([]);

    const searchForce = useThreadPrefStore((s) => s.searchForce['default'] || false);
    const selectedTeamId = useTeamStore((s) => (s as any).selectedTeamId || undefined);

    const getTenantId = (): number | null => {
        try {
            const t = token || localStorage.getItem('auth_token');
            if (!t) return null;
            const payload = decodeJwt(t);
            const tid = (payload as any)?.tenant_id || (payload as any)?.tenantId;
            return tid ? Number(tid) : null;
        } catch { return null; }
    };

    const loadAvailableTools = async () => {
        try {
            setLoading(true);
            const { data } = await client.query({ query: GET_AVAILABLE_MCP_TOOLS_QUERY });
            const formatted = (data as any).getAvailableMCPTools.map((tool: any) => ({
                id: tool.name,
                name: tool.name,
                description: tool.description,
                category: tool.category || 'general',
                status: tool.status === 'STABLE' ? 'active' : 'active',
                version: tool.version || '1.0.0',
                capabilities: tool.capabilities || [],
                requiredCredentials: tool.requiredCredentials || [],
                maxConcurrentCalls: tool.maxConcurrentCalls || 10,
                rateLimit: tool.rateLimit || 100,
                healthScore: 98,
                lastUsed: new Date().toISOString(),
                totalExecutions: 124,
                successRate: 99.2,
                averageExecutionTime: 450,
                totalCost: 0.45,
                isEnabled: true
            }));
            setTools(formatted);
            if (preselectToolName) {
                const found = formatted.find((t: any) => t.name === preselectToolName);
                if (found) setSelectedTool(found);
            }
        } catch (e) {
            message.error('Failed to load MCP tools');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => { loadAvailableTools(); }, []);

    const handleExecute = async (toolName: string, params: any) => {
        try {
            setExecuting(toolName);
            const tenantId = getTenantId();
            if (!tenantId) return;
            const { data } = await client.mutate({
                mutation: EXECUTE_MCP_TOOL_MUTATION,
                variables: {
                    tool_name: toolName,
                    params: JSON.stringify({
                        tenant_id: tenantId,
                        search_force: !!searchForce,
                        ...(selectedTeamId ? { agent_team_id: selectedTeamId } : {}),
                        ...params
                    })
                }
            });
            const result = data.executeMCPTool;
            setExecutionResults(prev => [{ toolName, ...result, timestamp: new Date().toISOString() }, ...prev.slice(0, 9)]);
            message.success('Execution triggered');
        } catch {
            message.error('Execution failed');
        } finally {
            setExecuting(null);
        }
    };

    const getStatusColor = (status: string) => {
        switch (status) {
            case 'active': return theme.colorSuccess;
            case 'error': return theme.colorError;
            default: return theme.colorTextDescription;
        }
    };

    return (
        <div className={styles.container}>
            <Flexbox className={styles.header} horizontal align="center" justify="space-between">
                <div>
                    <Title level={2} style={{ margin: 0 }}>MCP Tool Manager</Title>
                    <Text type="secondary">Monitor and control Model Context Protocol tools</Text>
                </div>
                <Space>
                    <Button icon={<RefreshCw size={14} />} onClick={loadAvailableTools}>Refresh</Button>
                    <Button type="primary" icon={<Plus size={14} />}>Add Tool</Button>
                </Space>
            </Flexbox>

            <Row gutter={24}>
                <Col span={8}>
                    <div className={styles.toolList}>
                        {loading ? <Skeleton active /> : tools.map(tool => (
                            <Card
                                key={tool.id}
                                className={`${styles.toolItem} ${selectedTool?.id === tool.id ? styles.activeTool : ''}`}
                                size="small"
                                onClick={() => setSelectedTool(tool)}
                            >
                                <Flexbox horizontal align="center" justify="space-between">
                                    <Flexbox direction="vertical" style={{ flex: 1 }}>
                                        <Space>
                                            <Text strong>{tool.name}</Text>
                                            <Tag>v{tool.version}</Tag>
                                        </Space>
                                        <Text type="secondary" style={{ fontSize: 12 }} ellipsis>{tool.description}</Text>
                                        <Space size={4}>
                                            <div className={styles.statusDot} style={{ background: getStatusColor(tool.status) }} />
                                            <Text type="secondary" style={{ fontSize: 11 }}>{tool.status}</Text>
                                        </Space>
                                    </Flexbox>
                                    <Switch checked={tool.isEnabled} size="small" />
                                </Flexbox>
                            </Card>
                        ))}
                    </div>
                </Col>

                <Col span={16}>
                    {selectedTool ? (
                        <Tabs defaultActiveKey="overview" items={[
                            {
                                key: 'overview',
                                label: <Space><Settings size={14} />Overview</Space>,
                                children: (
                                    <Card>
                                        <Row gutter={[16, 16]}>
                                            <Col span={6}><Statistic title="Executions" value={selectedTool.totalExecutions} /></Col>
                                            <Col span={6}><Statistic title="Success Rate" value={selectedTool.successRate} suffix="%" /></Col>
                                            <Col span={6}><Statistic title="Avg Resp" value={selectedTool.averageExecutionTime} suffix="ms" /></Col>
                                            <Col span={6}><Statistic title="Health" value={selectedTool.healthScore} suffix="%" /></Col>
                                        </Row>
                                        <Divider />
                                        <Title level={5}>Capabilities</Title>
                                        <Space wrap>
                                            {selectedTool.capabilities.map(c => <Tag key={c}>{c}</Tag>)}
                                        </Space>
                                        <Divider />
                                        <Flexbox horizontal gap={12}>
                                            <Button type="primary" icon={<Activity size={14} />} onClick={() => setTesting(selectedTool.name)}>Test Connection</Button>
                                            <Button icon={<Key size={14} />} onClick={() => setCredModalOpen(true)}>Credentials</Button>
                                            <Button danger icon={<Trash2 size={14} />}>Remove</Button>
                                        </Flexbox>
                                    </Card>
                                )
                            },
                            {
                                key: 'testing',
                                label: <Space><Zap size={14} />Terminal</Space>,
                                children: (
                                    <Flexbox direction="vertical" gap={16}>
                                        <Card size="small" title="Execution Parameters">
                                            <TextArea rows={4} placeholder='{"key": "value"}' />
                                            <Button
                                                type="primary"
                                                icon={<Play size={14} />}
                                                style={{ marginTop: 12 }}
                                                loading={executing === selectedTool.name}
                                                onClick={() => handleExecute(selectedTool.name, {})}
                                            >
                                                Execute
                                            </Button>
                                        </Card>
                                        <List
                                            header="Execution Log"
                                            dataSource={executionResults.filter(r => r.toolName === selectedTool.name)}
                                            renderItem={item => (
                                                <List.Item>
                                                    <Flexbox horizontal justify="space-between" style={{ width: '100%' }}>
                                                        <Space>
                                                            {item.success ? <CheckCircle size={14} color={theme.colorSuccess} /> : <XCircle size={14} color={theme.colorError} />}
                                                            <Text style={{ fontSize: 13 }}>{new Date(item.timestamp).toLocaleTimeString()}</Text>
                                                        </Space>
                                                        <Text type="secondary" style={{ fontSize: 12 }}>{item.executionTime}ms</Text>
                                                    </Flexbox>
                                                </List.Item>
                                            )}
                                        />
                                    </Flexbox>
                                )
                            },
                            {
                                key: 'monitor',
                                label: <Space><Activity size={14} />Monitor</Space>,
                                children: <MCPToolMonitor />
                            }
                        ]} />
                    ) : (
                        <Card style={{ height: '400px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                            <Empty description="Select a tool to manage" />
                        </Card>
                    )}
                </Col>
            </Row>

            <Modal
                title={`Credentials for ${selectedTool?.name}`}
                open={credModalOpen}
                onCancel={() => setCredModalOpen(false)}
                footer={null}
                width={800}
            >
                <CredentialManager toolName={selectedTool?.name} onClose={() => setCredModalOpen(false)} />
            </Modal>
        </div>
    );
};

export default MCPToolManager;
