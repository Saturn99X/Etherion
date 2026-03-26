'use client';

import { useEffect, useMemo, useState } from 'react';
import { createStyles } from 'antd-style';
import { Flexbox } from 'react-layout-kit';
import { Card, Button, Typography, Tag, Space, Alert, App } from 'antd';
import { Brain, ExternalLink, Wrench, CheckCircle, AlertCircle } from 'lucide-react';
import Link from 'next/link';
import { useApolloClient } from '@etherion/ui/layout/apollo-provider';
import {
  SUBSCRIBE_TO_EXECUTION_TRACE,
  CREATE_CUSTOM_AGENT_DEFINITION,
  CREATE_AGENT_TEAM_FROM_DEFINITION,
} from '@etherion/lib/graphql-operations';
import AgentBlueprintOrbital from './agent-blueprint-orbital';

const { Text, Title, Paragraph } = Typography;

const useStyles = createStyles(({ token, css }) => ({
  card: css`
    background: ${token.colorBgContainer};
    border: 1px solid ${token.colorBorder};
    border-radius: ${token.borderRadiusLG}px;
  `,
  header: css`
    padding: ${token.paddingMD}px ${token.paddingLG}px;
    border-bottom: 1px solid ${token.colorBorderSecondary};
  `,
  content: css`
    padding: ${token.paddingLG}px;
  `,
  previewBox: css`
    background: ${token.colorFillQuaternary};
    border: 1px solid ${token.colorBorder};
    padding: ${token.paddingSM}px;
    border-radius: ${token.borderRadius}px;
    font-family: ${token.fontFamilyCode};
    font-size: ${token.fontSizeSM}px;
    max-height: 120px;
    overflow: auto;
    white-space: pre-wrap;
  `,
  teamCard: css`
    background: ${token.colorBgElevated};
    border: 1px solid ${token.colorBorder};
    padding: ${token.paddingMD}px;
    border-radius: ${token.borderRadius}px;
    transition: all 0.3s ease;
    
    &:hover {
      border-color: ${token.colorPrimary};
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
    }
  `,
  toolReadiness: css`
    background: ${token.colorBgLayout};
    border: 1px solid ${token.colorBorder};
    padding: ${token.paddingXS}px ${token.paddingSM}px;
    border-radius: ${token.borderRadiusSM}px;
    font-size: ${token.fontSizeSM}px;
  `,
}));

interface Blueprint {
  blueprint_id?: string;
  specification?: string;
  tool_requirements?: string[];
  agent_requirements?: any;
  team_structure?: any;
  user_personality?: any;
  platform_prompt?: string;
  recommended_teams?: Array<{
    team_id: string;
    name: string;
    reason?: string;
    deep_link?: string;
    action?: string;
    fit_score?: number;
    readiness?: {
      tools?: Array<{
        name: string;
        credentials_ok?: boolean;
        status?: string;
        manual_approval_required?: boolean;
      }>;
      credentials_ready_count?: number;
      manual_approval_needed?: string[];
      all_ready?: boolean;
    };
  }>;
}

interface AgentBlueprintUIProps {
  jobId: string;
}

export function AgentBlueprintUI({ jobId }: AgentBlueprintUIProps) {
  const { styles, theme } = useStyles();
  const { message } = App.useApp();
  const [blueprint, setBlueprint] = useState<Blueprint | null>(null);
  const [isValidating, setIsValidating] = useState(false);
  const [validateMsg, setValidateMsg] = useState<string | null>(null);
  const client = useApolloClient();

  // Subscribe to execution trace for blueprint events
  useEffect(() => {
    if (!jobId) return;

    const subscription = client
      .subscribe({
        query: SUBSCRIBE_TO_EXECUTION_TRACE,
        variables: { job_id: jobId },
      })
      .subscribe({
        next: (result: any) => {
          const data = result?.data?.subscribeToExecutionTrace;
          if (!data) return;

          const evt = data.additional_data || {};
          if (evt.type === 'agent_blueprint_created' && evt.blueprint) {
            setBlueprint(evt.blueprint as Blueprint);
          }
        },
        error: (err: any) => {
          console.error('Blueprint subscription error:', err);
        },
      });

    return () => subscription.unsubscribe();
  }, [jobId, client]);

  // Prepare preview content
  const previews = useMemo(() => {
    if (!blueprint) return null;

    const sysPrompt = blueprint?.user_personality
      ? JSON.stringify(blueprint.user_personality, null, 2)
      : '';
    const tools = Array.isArray(blueprint?.tool_requirements)
      ? blueprint.tool_requirements.join(', ')
      : JSON.stringify(blueprint?.tool_requirements || []);
    const caps = JSON.stringify(blueprint?.team_structure || {}, null, 2);

    return { sysPrompt, tools, caps };
  }, [blueprint]);

  const handleValidate = async () => {
    if (!blueprint) return;

    setIsValidating(true);
    setValidateMsg(null);

    try {
      // Create custom agent definition
      const defInput: any = {
        name: blueprint.blueprint_id || blueprint.specification || 'Agent Blueprint',
        specification: blueprint.specification || '',
        team_structure: blueprint.team_structure || {},
        user_personality: blueprint.user_personality || {},
      };

      const defRes: any = await client.mutate({
        mutation: CREATE_CUSTOM_AGENT_DEFINITION,
        variables: { input: defInput },
      });

      const defId = defRes?.data?.createCustomAgentDefinition?.id;

      // Create agent team
      const teamInput: any = {
        name: blueprint.recommended_teams?.[0]?.name || 'Generated Team',
        pre_approved_tool_names: blueprint.tool_requirements || [],
        customAgentIDs: defId ? [defId] : [],
      };

      const teamRes: any = await client.mutate({
        mutation: CREATE_AGENT_TEAM_FROM_DEFINITION,
        variables: { team_input: teamInput },
      });

      const teamName = teamRes?.data?.createAgentTeam?.name || 'team';
      setValidateMsg(`Validated and created ${teamName}.`);
      message.success(`Team "${teamName}" created successfully`);
    } catch (e: any) {
      const errorMsg = `Validation failed: ${String(e?.message || e)}`;
      setValidateMsg(errorMsg);
      message.error(errorMsg);
    } finally {
      setIsValidating(false);
    }
  };

  if (!blueprint || !previews) return null;

  return (
    <Card className={styles.card} bordered={false}>
      <Flexbox className={styles.header} horizontal align="center" gap={8}>
        <Brain size={20} color={theme.colorPrimary} />
        <Title level={4} style={{ margin: 0 }}>
          Agent Blueprint
        </Title>
      </Flexbox>

      <div className={styles.content}>
        <Flexbox gap={20}>
          {/* Orbital Visualization */}
          <AgentBlueprintOrbital
            agentName="Agent Team"
            blueprintTitle={blueprint.specification || blueprint.blueprint_id || 'Blueprint'}
            systemPromptPreview={<pre className={styles.previewBox}>{previews.sysPrompt}</pre>}
            toolsPreview={<div className={styles.previewBox}>{previews.tools}</div>}
            capabilitiesPreview={<pre className={styles.previewBox}>{previews.caps}</pre>}
            onApprove={handleValidate}
            onReject={() => message.info('Blueprint rejected')}
          />

          {/* Validate Action */}
          <Flexbox horizontal align="center" gap={12}>
            <Button
              size="large"
              type="primary"
              loading={isValidating}
              disabled={isValidating}
              onClick={handleValidate}
            >
              {isValidating ? 'Validating…' : 'Validate & Create Team'}
            </Button>
            {validateMsg && (
              <Text type="secondary" style={{ fontSize: theme.fontSizeSM }}>
                {validateMsg}
              </Text>
            )}
          </Flexbox>

          {/* Recommended Teams */}
          {Array.isArray(blueprint.recommended_teams) &&
            blueprint.recommended_teams.length > 0 && (
              <Flexbox gap={16}>
                <Title level={5}>Recommended Teams</Title>
                <Flexbox gap={12}>
                  {blueprint.recommended_teams.map((team) => (
                    <div key={team.team_id} className={styles.teamCard}>
                      <Flexbox gap={12}>
                        <Flexbox horizontal justify="space-between" align="flex-start">
                          <Flexbox gap={4}>
                            <Text strong style={{ fontSize: theme.fontSize }}>
                              {team.name || team.team_id}
                            </Text>
                            <Text type="secondary" style={{ fontSize: theme.fontSizeSM }}>
                              {team.reason || 'Suggested match'}
                            </Text>
                            {typeof team.fit_score === 'number' && (
                              <Tag color="blue">Fit score: {team.fit_score}</Tag>
                            )}
                          </Flexbox>

                          <Space>
                            <Link
                              href={
                                team.deep_link ||
                                `/interact?teamId=${encodeURIComponent(team.team_id)}`
                              }
                            >
                              <Button type="primary" icon={<ExternalLink size={14} />}>
                                Start with Team
                              </Button>
                            </Link>
                            <Link href="/integrations">
                              <Button icon={<Wrench size={14} />}>Connect Tools</Button>
                            </Link>
                          </Space>
                        </Flexbox>

                        {/* Tool Readiness */}
                        {team.readiness?.tools && team.readiness.tools.length > 0 && (
                          <Flexbox gap={8}>
                            <Text type="secondary" style={{ fontSize: theme.fontSizeSM }}>
                              Tool Readiness
                            </Text>
                            <Flexbox gap={8}>
                              {team.readiness.tools.map((tool) => (
                                <div key={tool.name} className={styles.toolReadiness}>
                                  <Space size={8}>
                                    <Text code>{tool.name}</Text>
                                    {tool.credentials_ok ? (
                                      <Tag icon={<CheckCircle size={12} />} color="success">
                                        Credentials OK
                                      </Tag>
                                    ) : (
                                      <Tag icon={<AlertCircle size={12} />} color="warning">
                                        Missing Credentials
                                      </Tag>
                                    )}
                                    {tool.manual_approval_required && (
                                      <Tag color="orange">Manual Review</Tag>
                                    )}
                                  </Space>
                                </div>
                              ))}
                            </Flexbox>
                          </Flexbox>
                        )}
                      </Flexbox>
                    </div>
                  ))}
                </Flexbox>
              </Flexbox>
            )}
        </Flexbox>
      </div>
    </Card>
  );
}

export default AgentBlueprintUI;
