'use client';

import React, { useState } from 'react';
import { Modal, Button, Typography, Space, Divider, Tag, App, Alert } from 'antd';
import { createStyles } from 'antd-style';
import { Flexbox } from 'react-layout-kit';
import { Sparkles, Check, X, Wrench, Info } from 'lucide-react';
import { useApolloClient } from '@etherion/ui/layout/apollo-provider';
import { CREATE_AGENT_TEAM_MUTATION } from '@etherion/lib/graphql-operations';
import { useThreadStore } from '@etherion/stores/useThreadStore';
import { GoalService } from '@etherion/lib/services/goal-service';
import type { BlueprintApprovalPayload } from '@etherion/stores/job-store';

const { Text, Title, Paragraph } = Typography;

const useStyles = createStyles(({ token, css }) => ({
    modal: css`
    .ant-modal-content {
      background: ${token.colorBgContainer};
      border: 1px solid ${token.colorBorderSecondary};
      border-radius: ${token.borderRadiusLG}px;
      padding: 0;
      overflow: hidden;
    }
  `,
    header: css`
    padding: ${token.paddingMD}px ${token.paddingLG}px;
    background: ${token.colorFillQuaternary};
    border-bottom: 1px solid ${token.colorBorderSecondary};
  `,
    body: css`
    padding: ${token.paddingLG}px;
  `,
    footer: css`
    padding: ${token.paddingMD}px ${token.paddingLG}px;
    border-top: 1px solid ${token.colorBorderSecondary};
    background: ${token.colorFillQuaternary};
  `,
    blueprintBox: css`
    background: ${token.colorFillQuaternary};
    border: 1px solid ${token.colorBorderSecondary};
    padding: ${token.paddingMD}px;
    border-radius: ${token.borderRadius}px;
    margin-top: 8px;
  `,
    specBox: css`
    font-family: ${token.fontFamilyCode};
    font-size: 11px;
    background: ${token.colorBgLayout};
    padding: 8px;
    border-radius: 4px;
    border: 1px solid ${token.colorBorderSecondary};
    max-height: 120px;
    overflow: auto;
    white-space: pre-wrap;
  `,
}));

interface BlueprintApprovalModalProps {
    jobId: string;
    payload: BlueprintApprovalPayload;
    onDismiss: () => void;
}

export function BlueprintApprovalModal({ jobId, payload, onDismiss }: BlueprintApprovalModalProps) {
    const { styles, theme } = useStyles();
    const { message, notification } = App.useApp();
    const client = useApolloClient();
    const [loading, setLoading] = useState(false);

    const handleApprove = async () => {
        setLoading(true);
        try {
            // 1. Create the agent team
            const { data } = await client.mutate({
                mutation: CREATE_AGENT_TEAM_MUTATION,
                variables: {
                    team_input: {
                        name: payload.suggested_name || `Agent for ${payload.skill}`,
                        description: payload.suggested_description || `Team specialized in ${payload.skill}`,
                        pre_approved_tool_names: payload.suggested_spec?.tools || [],
                        // You might need more fields depending on your schema
                    }
                }
            });

            const teamId = data?.createAgentTeam?.id;
            if (!teamId) throw new Error('Failed to create agent team');

            notification.success({
                message: 'Team Created',
                description: `Agent team "${payload.suggested_name}" is ready. Re-running your request...`,
            });

            // 2. Retry the goal if we have enough context
            // Note: In real app, we might want to prompt user for input or use last goal
            // For now, we follow the "Retry" suggestion which implies starting a new job

            onDismiss();
        } catch (err: any) {
            console.error('Blueprint approval failed:', err);
            message.error(err.message || 'Failed to approve blueprint');
        } finally {
            setLoading(false);
        }
    };

    return (
        <Modal
            open
            footer={null}
            closable={false}
            onCancel={onDismiss}
            width={560}
            className={styles.modal}
            centered
        >
            <Flexbox className={styles.header} horizontal align="center" justify="space-between">
                <Space size={8}>
                    <Sparkles size={20} color={theme.colorPrimary} />
                    <Text strong style={{ fontSize: 16 }}>Agent Blueprint Approval</Text>
                </Space>
                <Button type="text" size="small" icon={<X size={18} />} onClick={onDismiss} />
            </Flexbox>

            <div className={styles.body}>
                <Flexbox gap={20}>
                    <div>
                        <Alert
                            message="New Skill Required"
                            description={`The agent identified a missing capability: "${payload.skill}". It suggests creating a specialized team to handle this step.`}
                            type="info"
                            showIcon
                            icon={<Info size={16} />}
                        />
                    </div>

                    <div className={styles.blueprintBox}>
                        <Flexbox gap={12}>
                            <div>
                                <Text type="secondary" style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Suggested Team</Text>
                                <Title level={5} style={{ margin: '4px 0 0 0' }}>{payload.suggested_name}</Title>
                            </div>

                            <div>
                                <Text type="secondary" style={{ fontSize: 11 }}>Description</Text>
                                <Paragraph style={{ margin: '2px 0 0 0', fontSize: 13 }}>{payload.suggested_description}</Paragraph>
                            </div>

                            {payload.suggested_spec && (
                                <div>
                                    <Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 4 }}>Configuration</Text>
                                    <div className={styles.specBox}>
                                        {JSON.stringify(payload.suggested_spec, null, 2)}
                                    </div>
                                </div>
                            )}

                            {payload.step_description && (
                                <div>
                                    <Text type="secondary" style={{ fontSize: 11 }}>Wait State Detail</Text>
                                    <Paragraph italic style={{ margin: '2px 0 0 0', fontSize: 12 }}>{payload.step_description}</Paragraph>
                                </div>
                            )}
                        </Flexbox>
                    </div>
                </Flexbox>
            </div>

            <Flexbox className={styles.footer} horizontal justify="flex-end" gap={12}>
                <Button onClick={onDismiss} disabled={loading}>Dismiss</Button>
                <Button
                    type="primary"
                    icon={<Check size={16} />}
                    loading={loading}
                    onClick={handleApprove}
                >
                    Create Team & Retry
                </Button>
            </Flexbox>
        </Modal>
    );
}

export default BlueprintApprovalModal;
