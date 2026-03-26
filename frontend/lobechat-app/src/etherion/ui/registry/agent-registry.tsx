'use client';

import { useState, useEffect } from 'react';
import {
    Button, Card, List, Tag, Typography,
    Modal, Form, Input, Select, Space,
    Empty, Skeleton, Badge, App, Tabs
} from 'antd';
import { createStyles } from 'antd-style';
import dynamic from 'next/dynamic';
import { Flexbox } from 'react-layout-kit';
import { Plus, Edit, Trash2, Bot, Cpu, Zap, Activity } from 'lucide-react';

const AgentTeams = dynamic(() => import('./agent-teams'));
const ToneOfVoiceLibrary = dynamic(() => import('./tone-of-voice-library'));
import { ThreadView } from '../chat/thread-view';

import { useApolloClient } from '@etherion/ui/layout/apollo-provider';
import { useAuthStore } from '@etherion/stores/auth-store';
import { decodeJwt } from '@etherion/lib/jwt';
import {
    GET_AGENTS_QUERY, CREATE_AGENT_MUTATION,
    UPDATE_AGENT_MUTATION, DELETE_AGENT_MUTATION
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
      transform: translateY(-2px);
    }
  `,
    capabilityTag: css`
    margin-bottom: 4px;
  `,
    metrics: css`
    margin-top: ${token.marginSM}px;
    padding-top: ${token.paddingXS}px;
    border-top: 1px solid ${token.colorBorderSecondary};
    font-size: 12px;
  `,
}));

interface Agent {
    id: string;
    name: string;
    description: string;
    createdAt: string;
    lastUsed?: string;
    status: string;
    agentType: string;
    capabilities: string[];
    performanceMetrics?: {
        successRate?: number;
        averageExecutionTime?: number;
        totalExecutions?: number;
    };
}

export const AgentRegistry = () => {
    const { styles, theme } = useStyles();
    const { message, modal } = App.useApp();
    const client = useApolloClient();
    const { token } = useAuthStore();

    const [agents, setAgents] = useState<Agent[]>([]);
    const [loading, setLoading] = useState(true);
    const [editModalVisible, setEditModalVisible] = useState(false);
    const [editingAgent, setEditingAgent] = useState<Agent | null>(null);
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

    const fetchAgents = async () => {
        try {
            setLoading(true);
            const tenantId = getTenantId();
            if (!tenantId) throw new Error('Missing tenant identity');

            const { data } = await client.query({
                query: GET_AGENTS_QUERY,
                variables: { tenant_id: tenantId }
            });
            setAgents(data.getAgents);
        } catch (err) {
            console.error('Failed to fetch agents:', err);
            message.error('Failed to load agents');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchAgents();
    }, []);

    const handleEdit = (agent: Agent) => {
        setEditingAgent(agent);
        form.setFieldsValue({
            name: agent.name,
            description: agent.description,
            agentType: agent.agentType,
            capabilities: agent.capabilities.join(', '),
            systemPrompt: (agent as any).systemPrompt || '',
        });
        setEditModalVisible(true);
    };

    const handleDelete = (agent: Agent) => {
        modal.confirm({
            title: 'Delete Agent',
            content: `Are you sure you want to delete ${agent.name}?`,
            okText: 'Delete',
            okType: 'danger',
            onOk: async () => {
                try {
                    await client.mutate({
                        mutation: DELETE_AGENT_MUTATION,
                        variables: { agent_id: agent.id }
                    });
                    setAgents(prev => prev.filter(a => a.id !== agent.id));
                    message.success('Agent deleted');
                } catch (err) {
                    message.error('Failed to delete agent');
                }
            }
        });
    };

    const handleSave = async () => {
        try {
            const values = await form.validateFields();
            const payload = {
                ...values,
                capabilities: values.capabilities.split(',').map((s: string) => s.trim()).filter(Boolean),
            };

            if (editingAgent) {
                const { data } = await client.mutate({
                    mutation: UPDATE_AGENT_MUTATION,
                    variables: { agent_id: editingAgent.id, agent_input: payload }
                });
                const updated = data.updateAgent;
                setAgents(prev => prev.map(a => a.id === updated.id ? { ...a, ...updated, ...payload } : a));
                message.success('Agent updated');
            } else {
                const { data } = await client.mutate({
                    mutation: CREATE_AGENT_MUTATION,
                    variables: { agent_input: payload }
                });
                setAgents(prev => [...prev, data.createAgent]);
                message.success('Agent created');
            }
            setEditModalVisible(false);
            setEditingAgent(null);
        } catch (err) {
            message.error('Failed to save agent');
        }
    };

    return (
        <div className={styles.container}>
            <Tabs
                defaultActiveKey="agents"
                items={[
                    {
                        key: 'agents',
                        label: 'All Agents',
                        children: (
                            <>
                                <Flexbox className={styles.header} horizontal align="center" justify="space-between">
                                    <div>
                                        <Title level={2} style={{ margin: 0 }}>Agents Foundry</Title>
                                        <Text type="secondary">Iterate, manually modify, and validate new agent team blueprints with IO</Text>
                                    </div>
                                    <Button
                                        type="primary"
                                        icon={<Plus size={16} />}
                                        onClick={() => {
                                            // TODO: Trigger IO Blueprint Creation Flow
                                            // This should open a chat session with the Platform Orchestrator (IO)
                                            // for blueprint generation.
                                            message.info("Opening IO Chat for Blueprint Creation...");
                                            // For now, fall back to manual creation until IO Chat component is wired
                                            setEditingAgent(null);
                                            form.resetFields();
                                            setEditModalVisible(true);
                                        }}
                                    >
                                        Forge New Agent
                                    </Button>
                                </Flexbox>

                                {loading ? (
                                    <List
                                        grid={{ gutter: 24, xs: 1, sm: 1, md: 2, lg: 3, xl: 3, xxl: 3 }}
                                        dataSource={[1, 2, 3]}
                                        renderItem={() => (
                                            <List.Item>
                                                <Card><Skeleton active avatar /></Card>
                                            </List.Item>
                                        )}
                                    />
                                ) : agents.length === 0 ? (
                                    <Empty
                                        image={<Bot size={64} style={{ opacity: 0.2 }} />}
                                        description="No agents created yet"
                                    >
                                        <Button type="primary" onClick={() => setEditModalVisible(true)}>Forge First Agent</Button>
                                    </Empty>
                                ) : (
                                    <List
                                        grid={{ gutter: 24, xs: 1, sm: 1, md: 2, lg: 3, xl: 3, xxl: 3 }}
                                        dataSource={agents}
                                        renderItem={(agent) => (
                                            <List.Item>
                                                <Card
                                                    className={styles.card}
                                                    actions={[
                                                        <Button key="edit" type="text" icon={<Edit size={14} />} onClick={() => handleEdit(agent)}>Edit</Button>,
                                                        <Button key="delete" type="text" danger icon={<Trash2 size={14} />} onClick={() => handleDelete(agent)}>Delete</Button>
                                                    ]}
                                                >
                                                    <Card.Meta
                                                        avatar={<div style={{ padding: 8, background: theme.colorFillQuaternary, borderRadius: 8 }}><Bot size={24} color={theme.colorPrimary} /></div>}
                                                        title={
                                                            <Flexbox horizontal align="center" gap={8}>
                                                                <span>{agent.name}</span>
                                                                <Badge status={agent.status === 'active' ? 'success' : 'default'} />
                                                            </Flexbox>
                                                        }
                                                        description={<Text type="secondary" style={{ fontSize: 12 }}>{agent.agentType}</Text>}
                                                    />

                                                    <Paragraph ellipsis={{ rows: 2 }} style={{ marginTop: 16 }}>
                                                        {agent.description}
                                                    </Paragraph>

                                                    <div style={{ marginTop: 12 }}>
                                                        {agent.capabilities.slice(0, 3).map((cap, idx) => (
                                                            <Tag key={idx} className={styles.capabilityTag}>{cap}</Tag>
                                                        ))}
                                                        {agent.capabilities.length > 3 && (
                                                            <Tag>+{agent.capabilities.length - 3}</Tag>
                                                        )}
                                                    </div>

                                                    {agent.performanceMetrics && (
                                                        <Flexbox className={styles.metrics} gap={4}>
                                                            <Flexbox horizontal justify="space-between">
                                                                <Text type="secondary"><Zap size={10} /> Success Rate</Text>
                                                                <Text strong>{((agent.performanceMetrics.successRate || 0) * 100).toFixed(1)}%</Text>
                                                            </Flexbox>
                                                            <Flexbox horizontal justify="space-between">
                                                                <Text type="secondary"><Activity size={10} /> Avg Time</Text>
                                                                <Text strong>{agent.performanceMetrics.averageExecutionTime?.toFixed(1)}s</Text>
                                                            </Flexbox>
                                                        </Flexbox>
                                                    )}
                                                </Card>
                                            </List.Item>
                                        )}
                                    />
                                )}
                            </>
                        )
                    },
                    {
                        key: 'teams',
                        label: 'Agent Teams',
                        children: <div style={{ padding: '24px 0' }}><AgentTeams /></div>
                    },
                    {
                        key: 'tone',
                        label: 'Tone of Voice',
                        children: <div style={{ padding: '24px 0' }}><ToneOfVoiceLibrary /></div>
                    }
                ]}
            />

            <Modal
                title={editingAgent ? 'Edit Agent' : 'Forge Agent (IO Blueprinting)'}
                open={editModalVisible}
                onOk={handleSave}
                onCancel={() => setEditModalVisible(false)}
                width={800}
                destroyOnClose
                footer={null} // Let the Chat UI handle actions
            >
                {editingAgent ? (
                    <Form form={form} layout="vertical" initialValues={{ agentType: 'general' }}>
                        <Form.Item name="name" label="Name" rules={[{ required: true, message: 'Please input agent name' }]}>
                            <Input placeholder="e.g. Code Reviewer" />
                        </Form.Item>
                        <Form.Item name="description" label="Description" rules={[{ required: true }]}>
                            <TextArea rows={3} placeholder="What does this agent do?" />
                        </Form.Item>
                        <Form.Item name="agentType" label="Type">
                            <Select options={[
                                { value: 'general', label: 'General Purpose' },
                                { value: 'coding', label: 'Software Engineer' },
                                { value: 'research', label: 'Researcher' },
                                { value: 'creative', label: 'Creative Assistant' },
                            ]} />
                        </Form.Item>
                        <Form.Item name="capabilities" label="Capabilities (comma-separated)">
                            <Input placeholder="e.g. coding, testing, debugging" />
                        </Form.Item>
                        <Form.Item name="systemPrompt" label="System Prompt (Internal Logic)">
                            <TextArea rows={5} placeholder="Instructions for the AI..." />
                        </Form.Item>
                        <Flexbox justify="flex-end" gap={8} style={{ marginTop: 24 }}>
                            <Button onClick={() => setEditModalVisible(false)}>Cancel</Button>
                            <Button type="primary" onClick={handleSave}>Save Changes</Button>
                        </Flexbox>
                    </Form>
                ) : (
                    <div style={{ height: '60vh', display: 'flex', flexDirection: 'column' }}>
                        <ThreadView mode="foundry" initialGoal="Help me design a new agent team." />
                    </div>
                )}
            </Modal>
        </div>
    );
};

export default AgentRegistry;
