'use client';

import { useEffect, useState, useMemo } from 'react';
import { createStyles } from 'antd-style';
import { Flexbox } from 'react-layout-kit';
import { Card, Typography, Tag, Badge } from 'antd';
import { Brain, Search, Wrench } from 'lucide-react';
import { useApolloClient } from '@etherion/ui/layout/apollo-provider';
import { SUBSCRIBE_TO_EXECUTION_TRACE } from '@etherion/lib/graphql-operations';

const { Text } = Typography;

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
  scrollArea: css`
    max-height: 320px;
    overflow-y: auto;
    padding: ${token.paddingMD}px;
    
    &::-webkit-scrollbar {
      width: 6px;
    }
    
    &::-webkit-scrollbar-thumb {
      background: ${token.colorBorderSecondary};
      border-radius: 3px;
    }
  `,
  eventItem: css`
    padding: ${token.paddingSM}px;
    border-radius: ${token.borderRadius}px;
    background: ${token.colorFillQuaternary};
    transition: all 0.2s ease;
    
    &:hover {
      background: ${token.colorFillTertiary};
    }
  `,
  eventHighlight: css`
    background: ${token.colorSuccessBg};
    border: 1px solid ${token.colorSuccessBorder};
  `,
  eventTool: css`
    background: ${token.colorInfoBg};
    border: 1px solid ${token.colorInfoBorder};
  `,
  timestamp: css`
    color: ${token.colorTextSecondary};
    font-size: ${token.fontSizeSM}px;
  `,
  message: css`
    color: ${token.colorText};
    font-size: ${token.fontSizeSM}px;
    margin-top: 4px;
  `,
}));

interface ExecutionTraceUIProps {
  jobId: string;
  autoOpen?: boolean;
  className?: string;
  toolHints?: ToolHint[];
  onToolEvent?: (hint: ToolHint, event: TraceEvent, phase: 'running' | 'succeeded' | 'failed') => void;
  showToolBadge?: boolean;
}

interface TraceEvent {
  timestamp: string;
  message?: string;
  current_step_description?: string;
  additional_data?: Record<string, unknown>;
}

type ToolHint = {
  threadId: string;
  messageId: string;
  invocationId: string;
  toolName: string;
};

export function ExecutionTraceUI({
  jobId,
  autoOpen = true,
  className,
  toolHints = [],
  onToolEvent,
  showToolBadge = true,
}: ExecutionTraceUIProps) {
  const { styles, theme } = useStyles();
  const [open, setOpen] = useState<boolean>(autoOpen);
  const [events, setEvents] = useState<TraceEvent[]>([]);
  const client = useApolloClient();

  // Subscribe to execution trace events
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

          const evt: TraceEvent = {
            timestamp: data.timestamp,
            message: data.message,
            current_step_description: data.current_step_description,
            additional_data: data.additional_data,
          };

          setEvents((prev) => prev.concat(evt));

          // Map trace events to tool runs
          try {
            const txt = ((evt.current_step_description || evt.message || '') + '').toLowerCase();
            const data = (evt.additional_data || {}) as any;
            const toolNameInData = (data.tool_name || data.tool || '').toString().toLowerCase();
            const norms = (toolHints || []).map((h) => ({ ...h, n: h.toolName.toLowerCase() }));

            for (const h of norms) {
              const match = toolNameInData.includes(h.n) || txt.includes(h.n);
              if (!match) continue;

              let phase: 'running' | 'succeeded' | 'failed' = 'running';
              if (/(success|succeed|complete|done)/.test(txt)) phase = 'succeeded';
              if (/(fail|error|exception)/.test(txt)) phase = 'failed';

              onToolEvent && onToolEvent(h, evt, phase);
            }
          } catch {}

          if (!open && autoOpen) setOpen(true);
        },
        error: (err: any) => {
          setEvents((prev) =>
            prev.concat({
              timestamp: new Date().toISOString(),
              message: `Trace error: ${String(err)}`,
            })
          );
        },
      });

    return () => subscription.unsubscribe();
  }, [jobId, autoOpen, open, toolHints, onToolEvent]);

  // Render events with highlighting
  const rendered = useMemo(() => {
    const isRetrieval = (ev: TraceEvent): boolean => {
      const txt = (ev.current_step_description || ev.message || '').toLowerCase();
      if (txt.includes('retriev') || txt.includes('search')) return true;
      const data = ev.additional_data || {};
      return Boolean((data as any).retrieval || (data as any).search || (data as any).kb);
    };

    const isToolRun = (ev: TraceEvent): string | null => {
      if (!showToolBadge || !toolHints?.length) return null;
      const txt = (ev.current_step_description || ev.message || '').toLowerCase();
      const toolInData = (
        (ev.additional_data as any)?.tool_name ||
        (ev.additional_data as any)?.tool ||
        ''
      )
        .toString()
        .toLowerCase();

      for (const h of toolHints) {
        const n = h.toolName.toLowerCase();
        if (toolInData.includes(n) || txt.includes(n)) return h.toolName;
      }
      return null;
    };

    return events.map((e, idx) => {
      const highlight = isRetrieval(e);
      const toolName = isToolRun(e);
      const eventClass = highlight
        ? styles.eventHighlight
        : toolName
          ? styles.eventTool
          : styles.eventItem;

      return (
        <div key={`${e.timestamp}-${idx}`} className={eventClass}>
          <Flexbox horizontal justify="space-between" align="center">
            <Text className={styles.timestamp}>
              {new Date(e.timestamp).toLocaleTimeString()}
            </Text>
            <Flexbox horizontal gap={8}>
              {highlight && (
                <Tag icon={<Search size={12} />} color="success">
                  Retrieval
                </Tag>
              )}
              {toolName && (
                <Tag icon={<Wrench size={12} />} color="processing">
                  {toolName}
                </Tag>
              )}
            </Flexbox>
          </Flexbox>
          {e.current_step_description && (
            <Text className={styles.message}>{e.current_step_description}</Text>
          )}
          {!e.current_step_description && e.message && (
            <Text className={styles.message}>{e.message}</Text>
          )}
        </div>
      );
    });
  }, [events, showToolBadge, toolHints, styles, theme]);

  if (!open) return null;

  return (
    <Card className={`${styles.card} ${className || ''}`} bordered={false}>
      <Flexbox className={styles.header} horizontal align="center" gap={8}>
        <Brain size={20} color={theme.colorPrimary} />
        <Text strong>Execution Trace</Text>
        <Badge count={events.length} showZero style={{ marginLeft: 'auto' }} />
      </Flexbox>
      <div className={styles.scrollArea}>
        <Flexbox gap={8}>{rendered}</Flexbox>
      </div>
    </Card>
  );
}

export default ExecutionTraceUI;
