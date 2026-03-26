'use client';

/**
 * execution-trace.tsx
 *
 * Lightweight, prop-driven execution trace renderer.
 * Unlike `panels/execution-trace-panel.tsx` (which reads from job store),
 * this component accepts raw trace steps as props — usable inline in
 * message bubbles, drawers, or anywhere trace data is passed directly.
 */

import { useMemo } from 'react';
import { createStyles } from 'antd-style';
import { Timeline, Typography, Badge, Collapse, Empty, Space } from 'antd';
import { Flexbox } from 'react-layout-kit';
import { CheckCircle, XCircle, Loader2, Circle, Wrench, Brain, Clock } from 'lucide-react';

const { Text, Paragraph } = Typography;

const useStyles = createStyles(({ token, css }) => ({
  root: css`
    width: 100%;
  `,
  timeline: css`
    margin-top: ${token.marginSM}px;
    .ant-timeline-item-tail {
      border-inline-start: 1px dashed ${token.colorBorderSecondary};
    }
  `,
  stepTitle: css`
    font-size: ${token.fontSizeSM}px;
    font-weight: 600;
    color: ${token.colorText};
  `,
  stepSummary: css`
    font-size: ${token.fontSizeSM}px;
    color: ${token.colorTextSecondary};
    margin: 2px 0 0;
  `,
  timestamp: css`
    font-size: 10px;
    color: ${token.colorTextQuaternary};
    margin-left: auto;
  `,
  toolCard: css`
    background: ${token.colorFillQuaternary};
    border: 1px solid ${token.colorBorderSecondary};
    border-radius: ${token.borderRadiusSM}px;
    padding: ${token.paddingXS}px ${token.paddingSM}px;
    margin-top: 6px;
  `,
  codeBlock: css`
    font-family: ${token.fontFamilyCode};
    font-size: 11px;
    background: ${token.colorBgLayout};
    padding: 6px 8px;
    border-radius: ${token.borderRadiusSM}px;
    border: 1px solid ${token.colorBorderSecondary};
    margin-top: 4px;
    max-height: 160px;
    overflow: auto;
    white-space: pre-wrap;
    word-break: break-all;
  `,
  collapsePanel: css`
    .ant-collapse-content-box {
      padding: 6px 0 0;
    }
    .ant-collapse-header {
      padding: 4px 0 !important;
      font-size: ${token.fontSizeSM}px;
      color: ${token.colorTextSecondary};
    }
  `,
  statusBadge: css`
    font-size: 10px;
  `,
}));

// ─── Types ────────────────────────────────────────────────────────────────────

export type TraceStepStatus = 'pending' | 'running' | 'completed' | 'failed' | 'skipped';

export interface TraceToolCall {
  toolName: string;
  arguments?: string;
  output?: string;
}

export interface TraceStep {
  id?: string;
  title: string;
  summary?: string;
  status: TraceStepStatus;
  timestamp: string;
  durationMs?: number;
  toolCall?: TraceToolCall;
  /** Nested sub-steps (specialist → tool calls) */
  children?: TraceStep[];
}

export interface ExecutionTraceProps {
  steps: TraceStep[];
  /** Show a live "processing" tail item */
  isRunning?: boolean;
  currentStep?: string;
  /** Collapse tool call details by default */
  collapseTools?: boolean;
  compact?: boolean;
}

// ─── Component ────────────────────────────────────────────────────────────────

export function ExecutionTrace({
  steps,
  isRunning = false,
  currentStep,
  collapseTools = false,
  compact = false,
}: ExecutionTraceProps) {
  const { styles, theme } = useStyles();

  const statusDot = (status: TraceStepStatus) => {
    switch (status) {
      case 'completed': return <CheckCircle size={14} color={theme.colorSuccess} />;
      case 'failed':    return <XCircle size={14} color={theme.colorError} />;
      case 'running':   return <Loader2 size={14} color={theme.colorPrimary} style={{ animation: 'spin 1s linear infinite' }} />;
      case 'skipped':   return <Circle size={14} color={theme.colorTextQuaternary} />;
      default:          return <Circle size={14} color={theme.colorTextTertiary} />;
    }
  };

  const statusColor = (status: TraceStepStatus): string => {
    switch (status) {
      case 'completed': return 'green';
      case 'failed':    return 'red';
      case 'running':   return 'blue';
      default:          return 'gray';
    }
  };

  const formatDuration = (ms?: number) => {
    if (!ms) return null;
    if (ms < 1000) return `${ms}ms`;
    return `${(ms / 1000).toFixed(1)}s`;
  };

  const renderedSteps = useMemo(() => steps, [steps]);

  if (renderedSteps.length === 0 && !isRunning) {
    return <Empty description="No trace steps" image={Empty.PRESENTED_IMAGE_SIMPLE} />;
  }

  return (
    <div className={styles.root}>
      <Timeline className={styles.timeline}>
        {renderedSteps.map((step, idx) => (
          <Timeline.Item
            key={step.id ?? idx}
            dot={statusDot(step.status)}
            color={statusColor(step.status)}
          >
            <Flexbox gap={compact ? 2 : 4}>
              {/* Header row */}
              <Flexbox horizontal align="center" gap={6}>
                <span className={styles.stepTitle}>{step.title}</span>
                {step.durationMs !== undefined && (
                  <Badge
                    className={styles.statusBadge}
                    count={formatDuration(step.durationMs)}
                    style={{ background: theme.colorFillSecondary, color: theme.colorTextSecondary }}
                  />
                )}
                <span className={styles.timestamp}>
                  {new Date(step.timestamp).toLocaleTimeString()}
                </span>
              </Flexbox>

              {/* Summary */}
              {step.summary && !compact && (
                <Paragraph className={styles.stepSummary} ellipsis={{ rows: 2, expandable: true }}>
                  {step.summary}
                </Paragraph>
              )}

              {/* Tool call */}
              {step.toolCall && (
                collapseTools ? (
                  <Collapse ghost className={styles.collapsePanel} size="small" items={[{
                    key: 'tool',
                    label: (
                      <Space size={4}>
                        <Wrench size={11} color={theme.colorWarning} />
                        <Text type="secondary" style={{ fontSize: 11 }}>
                          Tool: {step.toolCall.toolName}
                        </Text>
                      </Space>
                    ),
                    children: <ToolCallDetail tool={step.toolCall} theme={theme} codeStyle={styles.codeBlock} />,
                  }]} />
                ) : (
                  <div className={styles.toolCard}>
                    <Flexbox horizontal align="center" gap={6}>
                      <Wrench size={11} color={theme.colorWarning} />
                      <Text strong style={{ fontSize: 11 }}>Tool: {step.toolCall.toolName}</Text>
                    </Flexbox>
                    <ToolCallDetail tool={step.toolCall} theme={theme} codeStyle={styles.codeBlock} />
                  </div>
                )
              )}

              {/* Nested children (sub-steps) */}
              {step.children && step.children.length > 0 && (
                <div style={{ paddingLeft: 12, marginTop: 4 }}>
                  <ExecutionTrace
                    steps={step.children}
                    compact
                    collapseTools
                  />
                </div>
              )}
            </Flexbox>
          </Timeline.Item>
        ))}

        {/* Live "running" tail */}
        {isRunning && (
          <Timeline.Item
            dot={<Loader2 size={14} color={theme.colorPrimary} style={{ animation: 'spin 1s linear infinite' }} />}
            color="blue"
          >
            <Flexbox horizontal align="center" gap={6}>
              <Brain size={12} color={theme.colorPrimary} />
              <Text type="secondary" style={{ fontSize: theme.fontSizeSM }}>
                {currentStep ?? 'Processing…'}
              </Text>
            </Flexbox>
          </Timeline.Item>
        )}
      </Timeline>
    </div>
  );
}

// ─── Tool call detail sub-component ──────────────────────────────────────────

function ToolCallDetail({
  tool,
  theme,
  codeStyle,
}: {
  tool: TraceToolCall;
  theme: any;
  codeStyle: string;
}) {
  return (
    <>
      {tool.arguments && (
        <div className={codeStyle}>{tool.arguments}</div>
      )}
      {tool.output && (
        <>
          <Flexbox horizontal align="center" gap={4} style={{ marginTop: 6 }}>
            <Clock size={10} color={theme.colorTextQuaternary} />
            <Text type="secondary" style={{ fontSize: 10 }}>Output</Text>
          </Flexbox>
          <div className={codeStyle} style={{ background: theme.colorFillSecondary }}>
            {tool.output}
          </div>
        </>
      )}
    </>
  );
}

export default ExecutionTrace;
