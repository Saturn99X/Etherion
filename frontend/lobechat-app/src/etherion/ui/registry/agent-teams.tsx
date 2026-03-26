'use client';

import { useEffect, useState } from 'react';
import {
    Button, Card, List, Typography,
    Input, Form, Space, Badge, Modal, App, Tag
} from 'antd';
import { createStyles } from 'antd-style';
import { Flexbox } from 'react-layout-kit';
import { Plus, Users, Pencil, Save, Shield, Workflow } from 'lucide-react';

import { useApolloClient } from '@etherion/ui/layout/apollo-provider';
import {
    LIST_AGENT_TEAMS_QUERY,
    CREATE_AGENT_TEAM_MUTATION,
    UPDATE_AGENT_TEAM_MUTATION
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
    createCard: css`
    margin-bottom: ${token.marginXL}px;
    background: ${token.colorBgContainer};
    border: 1px solid ${token.colorBorderSecondary};
  `,
    teamCard: css`
    height: 100%;
    transition: all 0.3s;
    &:hover {
      box-shadow: ${token.boxShadowTertiary};
    }
  `,
    teamIcon: css`
    padding: 8px;
    background: ${token.colorFillQuaternary};
    border-radius: 8px;
    color: ${token.colorPrimary};
  `,
}));

interface AgentTeam {
    id: string;
    name: string;
    description: string;
    createdAt: string;
    lastUpdatedAt: string;
    isActive: boolean;
    isSystemTeam: boolean;
    version: string;
    customAgentIDs: string[];
    preApprovedToolNames: string[];
}

export const AgentTeams = () => {
    const { styles, theme } = useStyles();
    const { message } = App.useApp();
    const client = useApolloClient();

    const [teams, setTeams] = useState<AgentTeam[]>([]);
    const [loading, setLoading] = useState(true);
    const [submitting, setSubmitting] = useState(false);
    const [editId, setEditId] = useState<string | null>(null);
    const [form] = Form.useForm();
    const [editForm] = Form.useForm();

    const fetchTeams = async () => {
        try {
            setLoading(true);
            const { data } = await client.query({
                query: LIST_AGENT_TEAMS_QUERY,
                variables: { limit: 50, offset: 0 },
                fetchPolicy: 'network-only',
            });
            setTeams(data?.listAgentTeams || []);
        } catch (e) {
            console.error('Failed to fetch teams', e);
            message.error('Failed to load agent teams');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchTeams();
    }, []);

    const handleCreate = async (values: any) => {
        try {
            setSubmitting(true);
            const { data } = await client.mutate({
                mutation: CREATE_AGENT_TEAM_MUTATION,
                variables: {
                    team_input: {
                        name: values.name.trim(),
                        description: values.description.trim(),
                        specification: values.specification.trim()
                    }
                },
            });
            const created = data?.createAgentTeam as AgentTeam;
            if (created) {
                setTeams(prev => [created, ...prev]);
                form.resetFields();
                message.success('Team created successfully');
            }
        } catch (e) {
            message.error('Failed to create team');
        } finally {
            setSubmitting(false);
        }
    };

    const handleUpdate = async (id: string, values: any) => {
        try {
            await client.mutate({
                mutation: UPDATE_AGENT_TEAM_MUTATION,
                variables: {
                    agent_team_id: id,
                    name: values.name,
                    description: values.description
                },
            });
            setTeams(prev => prev.map(t => t.id === id ? { ...t, name: values.name, description: values.description } : t));
            setEditId(null);
            message.success('Team updated');
        } catch (e) {
            message.error('Failed to update team');
        }
    };

    return (
        <div className={styles.container}>
            <Flexbox className={styles.header} horizontal align="center" justify="space-between">
                <div>
                    <Title level={2} style={{ margin: 0 }}>Agent Teams</Title>
                    <Text type="secondary">Organize your agents into specialized units</Text>
                </div>
            </Flexbox>

            {/* Create Team Form */}
            <Card className={styles.createCard} title={<Flexbox horizontal align="center" gap={8}><Plus size={16} /> Create New Team</Flexbox>}>
                <Form form={form} layout="vertical" onFinish={handleCreate}>
                    <Flexbox gap={16}>
                        <Flexbox horizontal gap={16}>
                            <Form.Item name="name" label="Team Name" rules={[{ required: true }]} style={{ flex: 1 }}>
                                <Input placeholder="e.g. Frontend Squad" />
                            </Form.Item>
                            <Form.Item name="description" label="Short Description" rules={[{ required: true }]} style={{ flex: 2 }}>
                                <Input placeholder="What does this team specialize in?" />
                            </Form.Item>
                        </Flexbox>
                        <Form.Item name="specification" label="Detailed Specification" rules={[{ required: true }]}>
                            <TextArea rows={3} placeholder="Describe the team's mission and constraints in detail..." />
                        </Form.Item>
                        <Flexbox horizontal justify="flex-end">
                            <Button type="primary" htmlType="submit" loading={submitting} icon={<Users size={16} />}>
                                Create Team
                            </Button>
                        </Flexbox>
                    </Flexbox>
                </Form>
            </Card>

            {/* Teams Grid */}
            <List
                loading={loading}
                grid={{ gutter: 24, xs: 1, sm: 1, md: 2, lg: 3, xl: 3, xxl: 3 }}
                dataSource={teams}
                renderItem={(t) => (
                    <List.Item>
                        <Card
                            className={styles.teamCard}
                            title={
                                editId === t.id ? (
                                    <Input
                                        defaultValue={t.name}
                                        onChange={(e) => editForm.setFieldsValue({ name: e.target.value })}
                                        size="small"
                                    />
                                ) : (
                                    <Flexbox horizontal align="center" gap={8}>
                                        <div className={styles.teamIcon}><Users size={16} /></div>
                                        <span>{t.name}</span>
                                    </Flexbox>
                                )
                            }
                            actions={[
                                editId === t.id ? (
                                    <Button
                                        key="save"
                                        type="link"
                                        icon={<Save size={14} />}
                                        onClick={() => {
                                            const vals = editForm.getFieldsValue();
                                            handleUpdate(t.id, { name: vals.name || t.name, description: vals.description || t.description });
                                        }}
                                    >
                                        Save
                                    </Button>
                                ) : (
                                    <Button
                                        key="edit"
                                        type="link"
                                        icon={<Pencil size={14} />}
                                        onClick={() => {
                                            setEditId(t.id);
                                            editForm.setFieldsValue({ name: t.name, description: t.description });
                                        }}
                                    >
                                        Edit
                                    </Button>
                                )
                            ]}
                        >
                            <Flexbox gap={12}>
                                {editId === t.id ? (
                                    <TextArea
                                        defaultValue={t.description}
                                        onChange={(e) => editForm.setFieldsValue({ description: e.target.value })}
                                        rows={3}
                                    />
                                ) : (
                                    <Paragraph type="secondary" style={{ fontSize: 13, minHeight: 40 }}>
                                        {t.description}
                                    </Paragraph>
                                )}

                                <Flexbox horizontal gap={12} style={{ marginTop: 8 }}>
                                    <Space>
                                        <Badge count={t.customAgentIDs.length} color={theme.colorInfo} overflowCount={99} />
                                        <Text type="secondary" style={{ fontSize: 12 }}>Agents</Text>
                                    </Space>
                                    <Space>
                                        <Badge count={t.preApprovedToolNames.length} color={theme.colorSuccess} overflowCount={99} />
                                        <Text type="secondary" style={{ fontSize: 12 }}>Tools</Text>
                                    </Space>
                                </Flexbox>

                                <div style={{ marginTop: 8 }}>
                                    {t.isSystemTeam && <Tag color="blue" icon={<Shield size={12} />}>System Team</Tag>}
                                    {t.isActive ? <Tag color="green">Active</Tag> : <Tag color="default">Inactive</Tag>}
                                </div>
                            </Flexbox>
                        </Card>
                    </List.Item>
                )}
            />
        </div>
    );
};

export default AgentTeams;
