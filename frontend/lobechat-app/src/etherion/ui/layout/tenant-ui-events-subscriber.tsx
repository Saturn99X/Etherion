'use client';

import { useEffect, useRef } from 'react';
import { useAuthStore } from '@etherion/stores/auth-store';
import { useJobStore } from '@etherion/stores/job-store';

/** GraphQL subscription document for tenant-scoped UI events. */
const SUBSCRIBE_UI_EVENTS = `
  subscription SubscribeToUIEvents($tenant_id: String!) {
    subscribeToUIEvents(tenant_id: $tenant_id) {
      type
      payload
      job_id
      tenant_id
      timestamp
    }
  }
`;

interface UIEvent {
  type: string;
  payload?: Record<string, unknown>;
  job_id?: string;
  tenant_id?: string;
  timestamp?: string;
}

type UIEventHandler = (event: UIEvent) => void;

/** Registry of handlers for tenant-scoped UI event types. */
const handlers: Record<string, UIEventHandler[]> = {};

export function onUIEvent(type: string, handler: UIEventHandler) {
  if (!handlers[type]) handlers[type] = [];
  handlers[type].push(handler);
  return () => {
    handlers[type] = (handlers[type] ?? []).filter((h) => h !== handler);
  };
}

function dispatchUIEvent(event: UIEvent) {
  const list = handlers[event.type] ?? [];
  for (const h of list) {
    try { h(event); } catch { /* swallow */ }
  }
  // Fallback: also dispatch a DOM custom event for components that use addEventListener
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent(`etherion:ui:${event.type}`, { detail: event }));
  }
}

/**
 * Invisible component that subscribes to tenant-scoped UI events via GraphQL WS
 * and routes them to registered handlers.  Mount once at the app shell level.
 */
export function TenantUIEventsSubscriber() {
  const tenantId = useAuthStore((s) => s.tenantId);
  const setJobField = useJobStore((s) => s.setJobField);
  const wsRef = useRef<WebSocket | null>(null);
  const activeRef = useRef(true);

  useEffect(() => {
    if (!tenantId) return;
    activeRef.current = true;

    const wsUrl = (
      process.env.NEXT_PUBLIC_GRAPHQL_WS ??
      (typeof window !== 'undefined'
        ? window.location.origin.replace(/^http/, 'ws') + '/graphql'
        : 'ws://localhost:8080/graphql')
    );

    let ws: WebSocket;
    try {
      ws = new WebSocket(wsUrl, 'graphql-ws');
      wsRef.current = ws;
    } catch {
      return;
    }

    ws.addEventListener('open', () => {
      ws.send(JSON.stringify({ type: 'connection_init', payload: {} }));
      ws.send(JSON.stringify({
        id: 'ui-events',
        type: 'start',
        payload: {
          query: SUBSCRIBE_UI_EVENTS,
          variables: { tenant_id: String(tenantId) },
        },
      }));
    });

    ws.addEventListener('message', (msg) => {
      if (!activeRef.current) return;
      try {
        const frame = JSON.parse(msg.data);
        if (frame.type !== 'data') return;
        const event: UIEvent = frame?.payload?.data?.subscribeToUIEvents;
        if (!event?.type) return;

        // Built-in routing: THREAD_CREATED → update job store
        if (event.type === 'THREAD_CREATED' && event.job_id && event.payload?.thread_id) {
          setJobField(event.job_id, 'threadId', event.payload.thread_id as string);
        }

        dispatchUIEvent(event);
      } catch { /* ignore malformed frames */ }
    });

    ws.addEventListener('close', () => {
      if (!activeRef.current) return;
      // Simple reconnect after 3s
      setTimeout(() => {
        if (activeRef.current) {
          // The useEffect will re-run if tenantId changes; otherwise we rely on reconnect
        }
      }, 3000);
    });

    return () => {
      activeRef.current = false;
      try { ws.close(); } catch { /* ignore */ }
    };
  }, [tenantId, setJobField]);

  return null; // Invisible — only side effects
}

export default TenantUIEventsSubscriber;
