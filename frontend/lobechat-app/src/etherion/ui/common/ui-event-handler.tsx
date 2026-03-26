'use client';

/**
 * ui-event-handler.tsx
 *
 * Reusable hooks and utilities for subscribing to Etherion UI events.
 *
 * Two complementary patterns:
 *
 * 1. `useJobUIEvents(jobId, handlers)` — subscribes to per-job execution-trace
 *    events via GraphQL subscription (`subscribeToExecutionTrace`).
 *
 * 2. `useTenantUIEvent(type, handler)` — subscribes to the global DOM custom
 *    event bus dispatched by `TenantUIEventsSubscriber`.  Works anywhere in the
 *    component tree without needing a WS connection per-component.
 *
 * 3. `UIEventHandlerProvider` — mounts both subscriptions in one place.
 *    Optionally renders `mountedComponents` triggered by `open_component` events.
 */

import { useEffect, useRef, useCallback, type ReactNode } from 'react';
import React from 'react';
import { Flexbox } from 'react-layout-kit';
import { renderUIComponent } from './global-ui-repository';

// ─── Types ────────────────────────────────────────────────────────────────────

export interface JobTraceEvent {
  job_id: string;
  type: string;
  status?: string;
  step_id?: string;
  title?: string;
  summary?: string;
  tool_name?: string;
  tool_args?: string;
  tool_output?: string;
  timestamp?: string;
  additional_data?: Record<string, unknown>;
}

export interface TenantUIEvent {
  type: string;
  payload?: Record<string, unknown>;
  job_id?: string;
  tenant_id?: string;
  timestamp?: string;
}

export type JobTraceHandlers = {
  onStep?: (event: JobTraceEvent) => void;
  onCompleted?: (event: JobTraceEvent) => void;
  onFailed?: (event: JobTraceEvent) => void;
  onPendingApproval?: (event: JobTraceEvent) => void;
  onThreadCreated?: (threadId: string, jobId: string) => void;
  onAny?: (event: JobTraceEvent) => void;
};

// ─── GraphQL subscription document ───────────────────────────────────────────

const SUBSCRIBE_EXECUTION_TRACE = `
  subscription SubscribeToExecutionTrace($job_id: String!) {
    subscribeToExecutionTrace(job_id: $job_id) {
      job_id
      type
      status
      step_id
      title
      summary
      tool_name
      tool_args
      tool_output
      timestamp
      additional_data
    }
  }
`;

// ─── Hook: useJobUIEvents ─────────────────────────────────────────────────────

/**
 * Subscribe to per-job execution trace events via GraphQL WS.
 * Automatically reconnects if the WebSocket drops.
 * Cleans up on unmount or jobId change.
 */
export function useJobUIEvents(jobId: string | null | undefined, handlers: JobTraceHandlers) {
  const handlersRef = useRef(handlers);
  handlersRef.current = handlers;

  useEffect(() => {
    if (!jobId) return;

    const wsUrl =
      process.env.NEXT_PUBLIC_GRAPHQL_WS ??
      (typeof window !== 'undefined'
        ? window.location.origin.replace(/^http/, 'ws') + '/graphql'
        : 'ws://localhost:8080/graphql');

    let ws: WebSocket;
    let active = true;

    const connect = () => {
      try {
        ws = new WebSocket(wsUrl, 'graphql-ws');
      } catch {
        return;
      }

      ws.addEventListener('open', () => {
        ws.send(JSON.stringify({ type: 'connection_init', payload: {} }));
        ws.send(JSON.stringify({
          id: `trace-${jobId}`,
          type: 'start',
          payload: {
            query: SUBSCRIBE_EXECUTION_TRACE,
            variables: { job_id: jobId },
          },
        }));
      });

      ws.addEventListener('message', (msg) => {
        if (!active) return;
        try {
          const frame = JSON.parse(msg.data as string);
          if (frame.type !== 'data') return;
          const event: JobTraceEvent = frame?.payload?.data?.subscribeToExecutionTrace;
          if (!event) return;

          const h = handlersRef.current;
          const evtType = (event.type ?? '').toUpperCase();

          h.onAny?.(event);

          if (evtType === 'STEP_COMPLETED' || evtType === 'STEP_STARTED') h.onStep?.(event);
          if (evtType === 'JOB_COMPLETED' || evtType === 'COMPLETED') h.onCompleted?.(event);
          if (evtType === 'JOB_FAILED' || evtType === 'FAILED') h.onFailed?.(event);
          if (evtType === 'PENDING_APPROVAL') h.onPendingApproval?.(event);
          if (evtType === 'THREAD_CREATED') {
            const threadId = (event.additional_data?.thread_id as string) ?? '';
            h.onThreadCreated?.(threadId, event.job_id);
          }
        } catch { /* ignore malformed frames */ }
      });

      ws.addEventListener('close', () => {
        if (!active) return;
        setTimeout(() => { if (active) connect(); }, 3000);
      });
    };

    connect();

    return () => {
      active = false;
      try { ws?.close(); } catch { /* ignore */ }
    };
  }, [jobId]);
}

// ─── Hook: useTenantUIEvent ───────────────────────────────────────────────────

/**
 * Subscribe to a specific Etherion tenant-scoped UI event type via the
 * DOM custom event bus (dispatched by `TenantUIEventsSubscriber`).
 *
 * The handler is stable — updates are applied via ref so no re-subscription
 * needed when the parent re-renders.
 *
 * @example
 * useTenantUIEvent('THREAD_CREATED', (evt) => {
 *   router.push(`/chat/${evt.payload?.thread_id}`);
 * });
 */
export function useTenantUIEvent(
  type: string,
  handler: (event: TenantUIEvent) => void,
) {
  const handlerRef = useRef(handler);
  handlerRef.current = handler;

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const eventName = `etherion:ui:${type}`;
    const listener = (e: Event) => {
      try {
        handlerRef.current((e as CustomEvent).detail as TenantUIEvent);
      } catch { /* swallow */ }
    };
    window.addEventListener(eventName, listener);
    return () => window.removeEventListener(eventName, listener);
  }, [type]);
}

// ─── Hook: useAllTenantUIEvents ───────────────────────────────────────────────

/**
 * Subscribe to ALL tenant UI events via a wildcard DOM listener.
 * Matches events prefixed with `etherion:ui:`.
 */
export function useAllTenantUIEvents(handler: (type: string, event: TenantUIEvent) => void) {
  const handlerRef = useRef(handler);
  handlerRef.current = handler;

  useEffect(() => {
    if (typeof window === 'undefined') return;

    // There is no native wildcard listener — we capture at window level
    // and filter by event name prefix.
    const listener = (e: Event) => {
      if (!e.type.startsWith('etherion:ui:')) return;
      const type = e.type.replace('etherion:ui:', '');
      try {
        handlerRef.current(type, (e as CustomEvent).detail as TenantUIEvent);
      } catch { /* swallow */ }
    };

    // We need to listen on every specific event type — capture approach:
    // Attach a listener that handles any custom event at the document level.
    document.addEventListener('etherion:ui:THREAD_CREATED', listener);
    document.addEventListener('etherion:ui:JOB_COMPLETED', listener);
    document.addEventListener('etherion:ui:JOB_FAILED', listener);
    document.addEventListener('etherion:ui:PENDING_APPROVAL', listener);
    document.addEventListener('etherion:ui:BLUEPRINT_APPROVAL_REQUIRED', listener);
    document.addEventListener('etherion:ui:CONFIRM_ACTION_REQUIRED', listener);
    document.addEventListener('etherion:ui:OPEN_COMPONENT', listener);
    document.addEventListener('etherion:ui:CLOSE_COMPONENT', listener);

    return () => {
      document.removeEventListener('etherion:ui:THREAD_CREATED', listener);
      document.removeEventListener('etherion:ui:JOB_COMPLETED', listener);
      document.removeEventListener('etherion:ui:JOB_FAILED', listener);
      document.removeEventListener('etherion:ui:PENDING_APPROVAL', listener);
      document.removeEventListener('etherion:ui:BLUEPRINT_APPROVAL_REQUIRED', listener);
      document.removeEventListener('etherion:ui:CONFIRM_ACTION_REQUIRED', listener);
      document.removeEventListener('etherion:ui:OPEN_COMPONENT', listener);
      document.removeEventListener('etherion:ui:CLOSE_COMPONENT', listener);
    };
  }, []);
}

// ─── UIEventHandlerProvider ───────────────────────────────────────────────────

interface MountedComponent {
  id: string;
  componentId: string;
  props: Record<string, unknown>;
}

interface UIEventHandlerProviderProps {
  children: ReactNode;
  /** If true, dynamically renders components triggered by open_component events */
  enableDynamicComponents?: boolean;
}

/**
 * Optional provider that listens for `open_component` / `close_component`
 * DOM events and renders the corresponding registered components inline.
 *
 * Mount below `TenantUIEventsSubscriber` in the layout tree.
 * Only needed if you want dynamic component injection outside of
 * `UIEventDispatcherProvider`.
 */
export function UIEventHandlerProvider({ children, enableDynamicComponents = true }: UIEventHandlerProviderProps) {
  const [mountedComponents, setMountedComponents] = React.useState<MountedComponent[]>([]);

  useTenantUIEvent('OPEN_COMPONENT', useCallback((evt) => {
    if (!enableDynamicComponents) return;
    const componentId = evt.payload?.component as string;
    if (!componentId) return;
    const id = `${componentId}-${evt.timestamp ?? Date.now()}`;
    setMountedComponents((prev) => [
      ...prev,
      { id, componentId, props: { ...(evt.payload ?? {}), job_id: evt.job_id } },
    ]);
  }, [enableDynamicComponents]));

  useTenantUIEvent('CLOSE_COMPONENT', useCallback((evt) => {
    const componentId = evt.payload?.component as string;
    if (!componentId) return;
    setMountedComponents((prev) => prev.filter((m) => !m.componentId.startsWith(componentId)));
  }, []));

  return (
    <>
      {children}
      {enableDynamicComponents && mountedComponents.length > 0 && (
        <Flexbox gap={12} style={{ padding: '8px 0' }}>
          {mountedComponents.map((m) => (
            <div key={m.id}>
              {renderUIComponent(m.componentId, m.props)}
            </div>
          ))}
        </Flexbox>
      )}
    </>
  );
}

export default { useJobUIEvents, useTenantUIEvent, useAllTenantUIEvents, UIEventHandlerProvider };
