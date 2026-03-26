"use client";

import { useEffect, useState, useMemo } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import { useApolloClient } from "@/components/apollo-provider";
import { SUBSCRIBE_TO_EXECUTION_TRACE } from "@/lib/graphql-operations";
import { Brain } from "lucide-react";

interface ExecutionTraceUIProps {
  jobId: string;
  autoOpen?: boolean;
  className?: string;
}

interface TraceEvent {
  timestamp: string;
  message?: string;
  current_step_description?: string;
  additional_data?: Record<string, unknown>;
}

type ToolHint = { threadId: string; messageId: string; invocationId: string; toolName: string }

export function ExecutionTraceUI({ jobId, autoOpen = true, className, toolHints = [], onToolEvent, showToolBadge = true }: ExecutionTraceUIProps & { toolHints?: ToolHint[]; onToolEvent?: (hint: ToolHint, event: TraceEvent, phase: 'running'|'succeeded'|'failed') => void; showToolBadge?: boolean; }) {
  const [open, setOpen] = useState<boolean>(autoOpen);
  const [events, setEvents] = useState<TraceEvent[]>([]);
  const client = useApolloClient();

  useEffect(() => {
    if (!jobId) return;

const subscription = client
      .subscribe({ query: SUBSCRIBE_TO_EXECUTION_TRACE, variables: { job_id: jobId } })
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
          // Heuristic: map trace events to tool runs
          try {
            const txt = ((evt.current_step_description || evt.message || '') + '').toLowerCase()
            const data = (evt.additional_data || {}) as any
            const toolNameInData = (data.tool_name || data.tool || '').toString().toLowerCase()
            const norms = (toolHints || []).map((h) => ({ ...h, n: h.toolName.toLowerCase() }))
            for (const h of norms) {
              const match = toolNameInData.includes(h.n) || txt.includes(h.n)
              if (!match) continue
              let phase: 'running'|'succeeded'|'failed' = 'running'
              if (/(success|succeed|complete|done)/.test(txt)) phase = 'succeeded'
              if (/(fail|error|exception)/.test(txt)) phase = 'failed'
              onToolEvent && onToolEvent(h, evt, phase)
            }
          } catch {}
          if (!open && autoOpen) setOpen(true);
        },
        error: (err: any) => {
          // Surface error minimally in the UI stream for visibility
          setEvents((prev) =>
            prev.concat({ timestamp: new Date().toISOString(), message: `Trace error: ${String(err)}` })
          );
        },
      });

    return () => subscription.unsubscribe();
  }, [jobId, autoOpen, open]);

  const rendered = useMemo(() => {
    const isRetrieval = (ev: TraceEvent): boolean => {
      const txt = (ev.current_step_description || ev.message || '').toLowerCase()
      if (txt.includes('retriev') || txt.includes('search')) return true
      const data = ev.additional_data || {}
      return Boolean((data as any).retrieval || (data as any).search || (data as any).kb);
    }
    const isToolRun = (ev: TraceEvent): string | null => {
      if (!showToolBadge || !toolHints?.length) return null
      const txt = (ev.current_step_description || ev.message || '').toLowerCase()
      const toolInData = ((ev.additional_data as any)?.tool_name || (ev.additional_data as any)?.tool || '').toString().toLowerCase()
      for (const h of toolHints) {
        const n = h.toolName.toLowerCase()
        if (toolInData.includes(n) || txt.includes(n)) return h.toolName
      }
      return null
    }
    return events.map((e, idx) => {
      const highlight = isRetrieval(e)
      const toolName = isToolRun(e)
      return (
        <div key={`${e.timestamp}-${idx}`} className={cn("text-xs text-white/80 p-2 rounded", highlight ? "bg-emerald-500/15 border border-emerald-400/20" : toolName ? "bg-indigo-500/15 border border-indigo-400/20" : "bg-white/5")}> 
          <div className="flex items-center justify-between text-white/60">
            <span>{new Date(e.timestamp).toLocaleTimeString()}</span>
            <span className="flex items-center gap-2">
              {highlight && <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-400/20 text-emerald-200">Retrieval</span>}
              {toolName && <span className="text-[10px] px-1.5 py-0.5 rounded bg-indigo-400/20 text-indigo-200">Tool Run: {toolName}</span>}
            </span>
          </div>
          {e.current_step_description && <div className="mt-1">{e.current_step_description}</div>}
          {!e.current_step_description && e.message && <div className="mt-1">{e.message}</div>}
        </div>
      )
    });
  }, [events]);

  if (!open) return null;

  return (
    <Card className={cn("glass-card border-white/20", className)}>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-white">
          <Brain className="h-5 w-5 text-white" />
          <span className="text-white">Execution Trace</span>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <ScrollArea className="h-40">
          <div className="space-y-2">{rendered}</div>
        </ScrollArea>
      </CardContent>
    </Card>
  );
}

export default ExecutionTraceUI;


