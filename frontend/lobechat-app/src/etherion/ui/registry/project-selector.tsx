'use client';

import { useState, useEffect } from 'react';
import {
    Button, Select, Modal, Form,
    Input, Typography, Space, App,
    Badge, Divider
} from 'antd';
import { createStyles } from 'antd-style';
import { Flexbox } from 'react-layout-kit';
import { FolderKanban, Plus, Settings } from 'lucide-react';

import { ProjectService, type Project } from '@etherion/lib/services/project-service';

const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;

const useStyles = createStyles(({ token, css }) => ({
    container: css`
    display: flex;
    align-items: center;
    gap: ${token.marginSM}px;
  `,
    selector: css`
    min-width: 200px;
    .ant-select-selector {
      background: rgba(255, 255, 255, 0.05) !important;
      border-color: ${token.colorBorderSecondary} !important;
      color: ${token.colorText} !important;
    }
  `,
    icon: css`
    color: ${token.colorTextSecondary};
  `,
}));

interface ProjectSelectorProps {
    selectedProjectId?: number;
    onProjectSelect?: (project: Project | null) => void;
    className?: string;
}

export const ProjectSelector = ({ selectedProjectId, onProjectSelect, className }: ProjectSelectorProps) => {
    const { styles, theme } = useStyles();
    const { message } = App.useApp();

    const [projects, setProjects] = useState<Project[]>([]);
    const [loading, setLoading] = useState(false);
    const [createModalOpen, setCreateModalOpen] = useState(false);
    const [form] = Form.useForm();
    const [creating, setCreating] = useState(false);

    const loadProjects = async () => {
        try {
            setLoading(true);
            const fetched = await ProjectService.getProjects();
            setProjects(fetched);
            if (!selectedProjectId && fetched.length > 0) {
                onProjectSelect?.(fetched[0]);
            }
        } catch {
            message.error('Failed to load projects');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        loadProjects();
    }, []);

    const handleCreate = async (values: any) => {
        try {
            setCreating(true);
            const newProject = await ProjectService.createProject({
                name: values.name.trim(),
                description: values.description?.trim(),
            });
            setProjects(prev => [...prev, newProject]);
            setCreateModalOpen(false);
            form.resetFields();
            onProjectSelect?.(newProject);
            message.success('Project created');
        } catch {
            message.error('Creation failed');
        } finally {
            setCreating(false);
        }
    };

    return (
        <div className={`${styles.container} ${className}`}>
            <FolderKanban size={16} className={styles.icon} />

            <Select
                className={styles.selector}
                loading={loading}
                value={selectedProjectId}
                onChange={(val) => onProjectSelect?.(projects.find(p => p.id === val) || null)}
                placeholder="Select workspace"
                options={projects.map(p => ({ label: p.name, value: p.id }))}
            />

            <Button
                type="text"
                size="small"
                icon={<Plus size={14} />}
                onClick={() => setCreateModalOpen(true)}
                style={{ color: theme.colorTextSecondary }}
            />

            <Modal
                title="Create New Project"
                open={createModalOpen}
                onCancel={() => setCreateModalOpen(false)}
                onOk={() => form.submit()}
                confirmLoading={creating}
                okText="Create Workspace"
            >
                <Form form={form} layout="vertical" onFinish={handleCreate}>
                    <Form.Item name="name" label="Project Name" rules={[{ required: true }]}>
                        <Input placeholder="Engineering, Marketing, etc." />
                    </Form.Item>
                    <Form.Item name="description" label="Description">
                        <TextArea rows={3} placeholder="Optional context for this workspace" />
                    </Form.Item>
                </Form>
            </Modal>
        </div>
    );
};

export default ProjectSelector;
