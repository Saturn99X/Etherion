'use client';

import React from 'react';
import {
  Card, Button, Badge, Typography,
  Space, Tag, Divider
} from 'antd';
import { createStyles } from 'antd-style';
import { Flexbox } from 'react-layout-kit';
import { Sparkles, Check, Info, Wrench } from 'lucide-react';
import { useJobStore } from '@etherion/stores/job-store';

const { Title, Text } = Typography;

const useStyles = createStyles(({ token, css }) => ({
  blueprintCard: css`
    background: ${token.colorBgContainer};
    border: 1px solid ${token.colorPrimaryBorder};
    box-shadow: 0 4px 24px ${token.colorPrimaryBgHover};
    border-radius: ${token.borderRadiusLG}px;
    width: 100%;
  `,
  promptBox: css`
    background: ${token.colorFillQuaternary};
    border: 1px solid ${token.colorBorderSecondary};
    padding: ${token.paddingMD}px;
    border-radius: ${token.borderRadius}px;
    font-family: ${token.fontFamilyCode};
    font-size: 13px;
    color: ${token.colorTextSecondary};
    white-space: pre-wrap;
    max-height: 200px;
    overflow-y: auto;
  `,
  toolTag: css`
    margin-bottom: 4px;
    background: ${token.colorFillSecondary};
    border: none;
    color: ${token.colorText};
    display: flex;
    align-items: center;
    gap: 4px;
  `,
}));

import { App } from 'antd';
import { useApolloClient } from '@etherion/ui/layout/apollo-provider';
import { CREATE_AGENT_TEAM_MUTATION } from '@etherion/lib/graphql-operations';

export function AgentBlueprintUI({ jobId }: { jobId: string }) {
  const { styles, theme } = useStyles();
  const { message, notification } = App.useApp();
  const client = useApolloClient();
  const job = useJobStore((s) => s.jobs[jobId]);
  const [creating, setCreating] = React.useState(false);

  if (!job) return null;

  // Derive agent data from job metadata/input if available
  const agentName = (job as any).agentName || "New Agent";
  const systemPrompt = (job as any).systemPrompt || "No prompt specified";
  const tools = (job as any).tools || [];
  const loading = !job.isCompleted && !job.isFailed;

  const handleCreateAgent = async () => {
    setCreating(true);
    try {
      const { data } = await client.mutate({
        mutation: CREATE_AGENT_TEAM_MUTATION,
        variables: {
          team_input: {
            name: agentName,
            description: `Agent initialized from blueprint.`,
            pre_approved_tool_names: tools,
          }
        }
      });

      if (data?.createAgentTeam?.id) {
        notification.success({
          message: 'Agent Created',
          description: `The agent "${agentName}" has been successfully created and added to your registry.`,
        });
      }
    } catch (err: any) {
      message.error(err.message || 'Failed to create agent');
    } finally {
      setCreating(false);
    }
  };

  return (
    <Card
      className={styles.blueprintCard}
      title={
        <Space>
          <Sparkles size={18} color={theme.colorPrimary} />
          <Text strong>Agent Blueprint: {agentName}</Text>
        </Space>
      }
      size="small"
      actions={[
        <Button
          type="primary"
          key="validate"
          icon={<Check size={16} />}
          loading={creating || loading}
          onClick={handleCreateAgent}
          style={{ width: '90%' }}
        >
          Validate & Create Agent
        </Button>
      ]}
    >
      <Flexbox gap={12}>
        <div>
          <Text strong style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>
            System Prompt
          </Text>
          <div className={styles.promptBox}>
            {systemPrompt}
          </div>
        </div>

        <div>
          <Text strong style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>
            Tools
          </Text>
          <Flexbox horizontal wrap="wrap" gap={8}>
            {tools.map((tool: string, index: number) => (
              <Tag key={index} className={styles.toolTag}>
                <Wrench size={10} /> {tool}
              </Tag>
            ))}
            {tools.length === 0 && <Text type="secondary" italic style={{ fontSize: 11 }}>No tools selected</Text>}
          </Flexbox>
        </div>
      </Flexbox>
    </Card>
  );
}

export default AgentBlueprintUI;
