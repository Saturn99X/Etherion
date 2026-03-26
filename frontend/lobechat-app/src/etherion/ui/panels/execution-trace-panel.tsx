'use client';

import React from 'react';
import {
  Card, Timeline, Typography, Badge,
  Space, Collapse, Empty, Divider
} from 'antd';
import { createStyles } from 'antd-style';
import { Flexbox } from 'react-layout-kit';
import {
  CheckCircle, Loader2, Brain, Wrench,
  Circle, XCircle
} from 'lucide-react';
import { useJobStore } from '@etherion/stores/job-store';

const { Text, Paragraph } = Typography;

const useStyles = createStyles(({ token, css }) => ({
  traceCard: css`
    background: ${token.colorBgContainer};
    border: 1px solid ${token.colorBorderSecondary};
    border-radius: ${token.borderRadiusLG}px;
    box-shadow: ${token.boxShadowTertiary};
    width: 100%;
  `,
  stepHeader: css`
    display: flex;
    flex-direction: column;
    gap: 2px;
  `,
  toolCard: css`
    background: ${token.colorFillQuaternary};
    border: 1px solid ${token.colorBorderSecondary};
    padding: 12px;
    border-radius: ${token.borderRadius}px;
    margin-top: 8px;
  `,
  codeBlock: css`
    font-family: ${token.fontFamilyCode};
    font-size: 11px;
    background: ${token.colorBgLayout};
    padding: 8px;
    border-radius: ${token.borderRadiusSM}px;
    border: 1px solid ${token.colorBorderSecondary};
    margin-top: 4px;
    max-height: 200px;
    overflow: auto;
    word-break: break-all;
    white-space: pre-wrap;
  `,
  timeline: css`
    margin-top: ${token.marginMD}px;
    .ant-timeline-item-tail {
      border-inline-start: 1px solid ${token.colorBorderSecondary};
    }
  `,
}));

export function ExecutionTraceUI({ jobId }: { jobId: string }) {
  const { styles, theme } = useStyles();
  const job = useJobStore((s) => s.jobs[jobId]);

  if (!job) return (
    <Card className={styles.traceCard} size="small">
      <Empty description="No job found" />
    </Card>
  );

  const steps = job.executionTrace || [];
  const loading = !job.isCompleted && !job.isFailed;

  const getStepDot = (status: string) => {
    const s = (status || '').toLowerCase();
    if (s === 'completed') return <CheckCircle size={16} color={theme.colorSuccess} />;
    if (s === 'running') return <Loader2 size={16} className="animate-spin" color={theme.colorPrimary} />;
    if (s === 'failed') return <XCircle size={16} color={theme.colorError} />;
    return <Circle size={16} color={theme.colorTextQuaternary} />;
  };

  return (
    <Card
      className={styles.traceCard}
      title={<Space><Brain size={18} color={theme.colorPrimary} />Execution Trace</Space>}
      size="small"
    >
      {steps.length === 0 && !loading && (
        <Empty description="No trace steps recorded" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      )}
      <Timeline className={styles.timeline}>
        {steps.map((step, idx) => (
          <Timeline.Item
            key={idx}
            dot={getStepDot(step.status)}
            color={step.status === 'failed' ? 'red' : step.status === 'running' ? 'blue' : 'gray'}
          >
            <Flexbox className={styles.stepHeader}>
              <Flexbox horizontal align="center" justify="space-between">
                <Text strong style={{ fontSize: 13 }}>{step.title}</Text>
                <Text type="secondary" style={{ fontSize: 10 }}>{new Date(step.timestamp).toLocaleTimeString()}</Text>
              </Flexbox>
              <Paragraph style={{ fontSize: 12, margin: '2px 0 0 0' }}>{step.summary}</Paragraph>
            </Flexbox>

            {step.toolCall && (
              <div className={styles.toolCard}>
                <Flexbox horizontal align="center" gap={8} style={{ marginBottom: 4 }}>
                  <Wrench size={12} color={theme.colorWarning} />
                  <Text strong style={{ fontSize: 11 }}>Tool: {step.toolCall.toolName}</Text>
                </Flexbox>
                <div className={styles.codeBlock}>{step.toolCall.arguments}</div>
                {step.toolCall.output && (
                  <>
                    <Divider style={{ margin: '8px 0', borderColor: theme.colorBorderSecondary }} />
                    <Text type="secondary" style={{ fontSize: 10, display: 'block', marginBottom: 4 }}>Output:</Text>
                    <div className={styles.codeBlock} style={{ background: theme.colorFillSecondary }}>{step.toolCall.output}</div>
                  </>
                )}
              </div>
            )}
          </Timeline.Item>
        ))}
        {loading && (
          <Timeline.Item dot={<Loader2 size={16} className="animate-spin" color={theme.colorPrimary} />}>
            <Text type="secondary" style={{ fontSize: 12 }}>{job.currentStep || 'Processing...'}</Text>
          </Timeline.Item>
        )}
      </Timeline>
    </Card>
  );
}

export default ExecutionTraceUI;
