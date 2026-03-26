'use client';

import { useState, useEffect } from 'react';
import {
    Card, Table, Input, Button,
    Typography, Space, App, Popconfirm,
    Form, Divider, Empty, Skeleton
} from 'antd';
import { createStyles } from 'antd-style';
import { Flexbox } from 'react-layout-kit';
import {
    RefreshCw, Plus, Save, Trash2,
    Edit, X, FolderKanban, Info
} from 'lucide-react';

import { useApolloClient } from '@etherion/ui/layout/apollo-provider';
import {
    GET_PROJECTS_QUERY,
    CREATE_PROJECT_MUTATION,
    UPDATE_PROJECT_MUTATION,
    DELETE_PROJECT_MUTATION
} from '@etherion/lib/graphql-operations';

const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;

const useStyles = createStyles(({ token, css }) => ({
    container: css`
    padding: ${token.paddingLG}px;
    background: ${token.colorBgLayout};
    min-height: 100vh;
  `,
    header: css`
    margin-bottom: ${token.marginLG}px;
  `,
    createCard: css`
    margin-bottom: ${token.marginLG}px;
    background: ${token.colorBgContainer};
    border: 1px solid ${token.colorBorderSecondary};
  `,
    listCard: css`
    background: ${token.colorBgContainer};
    border: 1px solid ${token.colorBorderSecondary};
  `,
    actionButton: css`
    color: ${token.colorTextSecondary};
    &:hover {
      color: ${token.colorPrimary};
    }
  `,
    deleteButton: css`
    color: ${token.colorError};
    &:hover {
      color: ${token.colorErrorHover} !important;
    }
  `,
}));

interface ProjectItem {
    id: string;
    name: string;
    description?: string;
    createdAt?: string;
}

export const ProjectsDashboard = () => {
    const { styles, theme } = useStyles();
    const { message } = App.useApp();
    const client = useApolloClient();

    const [projects, setProjects] = useState<ProjectItem[]>([]);
    const [loading, setLoading] = useState(false);
    const [hasAttemptedLoad, setHasAttemptedLoad] = useState(false);

    // New project form
    const [form] = Form.useForm();

    // Edit state
    const [editId, setEditId] = useState<string | null>(null);
    const [editForm] = Form.useForm();

    const loadProjects = async () => {
        try {
            setLoading(true);
            const { data } = await client.query({
                query: GET_PROJECTS_QUERY,
                fetchPolicy: "network-only"
            });
            setProjects((data as any)?.getProjectsByTenant || []);
            setHasAttemptedLoad(true);
        } catch {
            message.error('Failed to load projects');
            setHasAttemptedLoad(true);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        if (!hasAttemptedLoad) loadProjects();
    }, [hasAttemptedLoad]);

    const handleCreate = async (values: any) => {
        try {
            setLoading(true);
            await client.mutate({
                mutation: CREATE_PROJECT_MUTATION,
                variables: {
                    project_input: {
                        name: values.name.trim(),
                        description: values.description?.trim()
                    }
                },
            });
            form.resetFields();
            message.success('Project created');
            await loadProjects();
        } catch {
            message.error('Failed to create project');
        } finally {
            setLoading(false);
        }
    };

    const handleUpdate = async (values: any) => {
        if (!editId) return;
        try {
            setLoading(true);
            await client.mutate({
                mutation: UPDATE_PROJECT_MUTATION,
                variables: {
                    project_id: Number(editId),
                    project_input: {
                        name: values.name.trim(),
                        description: values.description?.trim()
                    }
                },
            });
            setEditId(null);
            message.success('Project updated');
            await loadProjects();
        } catch {
            message.error('Failed to update project');
        } finally {
            setLoading(false);
        }
    };

    const handleDelete = async (id: string) => {
        try {
            setLoading(true);
            await client.mutate({
                mutation: DELETE_PROJECT_MUTATION,
                variables: { project_id: Number(id) }
            });
            message.success('Project deleted');
            await loadProjects();
        } catch {
            message.error('Failed to delete project');
        } finally {
            setLoading(false);
        }
    };

    const columns = [
        {
            title: 'Name',
            dataIndex: 'name',
            key: 'name',
            render: (text: string, record: ProjectItem) => {
                if (editId === record.id) {
                    return (
                        <Form form={editForm} initialValues={{ name: record.name, description: record.description }} onFinish={handleUpdate}>
                            <Form.Item name="name" style={{ margin: 0 }} rules={[{ required: true }]}>
                                <Input size="small" />
                            </Form.Item>
                        </Form>
                    );
                }
                return <Text strong>{text}</Text>;
            }
        },
        {
            title: 'Description',
            dataIndex: 'description',
            key: 'description',
            render: (text: string, record: ProjectItem) => {
                if (editId === record.id) {
                    return (
                        <Form.Item form={editForm} name="description" style={{ margin: 0 }}>
                            <TextArea size="small" rows={1} autoSize />
                        </Form.Item>
                    );
                }
                return <Text type="secondary">{text || '-'}</Text>;
            }
        },
        {
            title: 'Created At',
            dataIndex: 'createdAt',
            key: 'createdAt',
            render: (date?: string) => <Text type="secondary" style={{ fontSize: 12 }}>{date ? new Date(date).toLocaleString() : '-'}</Text>
        },
        {
            title: 'Actions',
            key: 'actions',
            align: 'right' as const,
            render: (_: any, record: ProjectItem) => (
                <Space size="small">
                    {editId === record.id ? (
                        <>
                            <Button size="small" type="primary" icon={<Save size={14} />} onClick={() => editForm.submit()} loading={loading}>Save</Button>
                            <Button size="small" icon={<X size={14} />} onClick={() => setEditId(null)}>Cancel</Button>
                        </>
                    ) : (
                        <>
                            <Button
                                size="small"
                                type="text"
                                icon={<Edit size={14} />}
                                className={styles.actionButton}
                                onClick={() => { setEditId(record.id); editForm.setFieldsValue(record); }}
                            />
                            <Popconfirm title="Delete project?" onConfirm={() => handleDelete(record.id)}>
                                <Button
                                    size="small"
                                    type="text"
                                    icon={<Trash2 size={14} />}
                                    className={styles.deleteButton}
                                />
                            </Popconfirm>
                        </>
                    )}
                </Space>
            )
        }
    ];

    return (
        <div className={styles.container}>
            <Flexbox className={styles.header} horizontal align="center" justify="space-between">
                <div>
                    <Title level={2} style={{ margin: 0 }}>Projects</Title>
                    <Text type="secondary">Organize your conversations and jobs into logical workspaces</Text>
                </div>
                <Button icon={<RefreshCw size={14} />} onClick={loadProjects} loading={loading}>Refresh</Button>
            </Flexbox>

            <Card className={styles.createCard} title={<Space><Plus size={16} />Create Project</Space>} size="small">
                <Form form={form} layout="vertical" onFinish={handleCreate}>
                    <Flexbox horizontal gap={16}>
                        <Form.Item name="name" label="Name" style={{ flex: 1, margin: 0 }} rules={[{ required: true }]}>
                            <Input placeholder="Project name..." />
                        </Form.Item>
                        <Form.Item name="description" label="Description" style={{ flex: 2, margin: 0 }}>
                            <TextArea placeholder="Optional context..." rows={1} autoSize />
                        </Form.Item>
                        <div style={{ alignSelf: 'flex-end' }}>
                            <Button type="primary" htmlType="submit" loading={loading} icon={<Plus size={14} />}>Create</Button>
                        </div>
                    </Flexbox>
                </Form>
            </Card>

            <Card className={styles.listCard} title={<Space><FolderKanban size={16} />Project List</Space>} bodyStyle={{ padding: 0 }}>
                {loading && !projects.length ? (
                    <div style={{ padding: 24 }}><Skeleton active /></div>
                ) : (
                    <Table
                        columns={columns}
                        dataSource={projects}
                        pagination={false}
                        rowKey="id"
                        locale={{ emptyText: <Empty description="No projects found" /> }}
                    />
                )}
            </Card>
        </div>
    );
};

export default ProjectsDashboard;
