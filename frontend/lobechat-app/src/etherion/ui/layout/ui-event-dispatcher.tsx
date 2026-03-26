"use client";

import { createContext, useContext, useEffect, useState, useCallback, useMemo, type ReactNode } from 'react';
import React from 'react';
import { useApolloClient } from './apollo-provider';
import { SUBSCRIBE_TO_UI_EVENTS } from '@etherion/lib/graphql-operations';
import { useAuthStore } from '@etherion/stores/auth-store';
import { useJobStore, type BlueprintApprovalPayload } from '@etherion/stores/job-store';

/**
 * Pending blueprint approval state for the UI to render a modal.
 */
export interface PendingBlueprint {
    jobId: string;
    payload: BlueprintApprovalPayload;
}

import { BlueprintApprovalModal } from '../triggered-ui/blueprint-approval-modal';
import { renderUIComponent } from '../common/global-ui-repository';

interface UIEventDispatcherContextValue {
    pendingBlueprint: PendingBlueprint | null;
    dismissBlueprint: () => void;
}

const UIEventDispatcherContext = createContext<UIEventDispatcherContextValue | null>(null);

export function useUIEventDispatcher() {
    const ctx = useContext(UIEventDispatcherContext);
    if (!ctx) {
        throw new Error('useUIEventDispatcher must be used within UIEventDispatcherProvider');
    }
    return ctx;
}


interface UIEvent {
    type: string;
    component?: string;
    payload?: any;
    job_id?: string;
    message?: string;
    timestamp?: string;
    additional_data?: any;
    status?: string;
}

interface UIEventDispatcherProviderProps {
    children: ReactNode;
}

/**
 * UIEventDispatcherProvider subscribes to tenant-scoped UI events and job store
 * to dispatch blueprint approval modals and other tenant-wide UI triggers.
 *
 * Mount this high in the LobeChat layout tree (e.g., in _app or root layout).
 */
export function UIEventDispatcherProvider({ children }: UIEventDispatcherProviderProps) {
    const [pendingBlueprint, setPendingBlueprint] = useState<PendingBlueprint | null>(null);
    const [mountedComponents, setMountedComponents] = useState<Array<{ id: string; props: any }>>([]);

    // Try to get the Apollo client - may be null during SSR or before hydration
    let client: ReturnType<typeof useApolloClient> | null = null;
    try {
        client = useApolloClient();
    } catch {
        // Not inside ApolloProvider yet
    }

    const authState = useAuthStore();
    const tenantId = authState.user?.tenant_id;

    // Subscribe to tenant UI events via GraphQL subscription
    useEffect(() => {
        if (!client || !tenantId) return;

        const subscription = client.subscribe({
            query: SUBSCRIBE_TO_UI_EVENTS,
            variables: { tenant_id: tenantId },
        }).subscribe({
            next: ({ data }: any) => {
                const evt: UIEvent | undefined = data?.subscribeToUIEvents;
                if (!evt) return;

                const add = evt.additional_data || {};
                const evtType = (evt.status || add.type || evt.type || '').toString().toUpperCase();
                const action = evt.type;
                const component = evt.component;

                // Handle BLUEPRINT_APPROVAL_REQUIRED from tenant UI events channel
                if (evtType === 'BLUEPRINT_APPROVAL_REQUIRED') {
                    const jobId = evt.job_id;
                    if (jobId) {
                        setPendingBlueprint({
                            jobId,
                            payload: {
                                skill: add.skill,
                                suggested_name: add.suggested_name,
                                suggested_description: add.suggested_description,
                                suggested_spec: add.suggested_spec,
                                step_description: add.step_description,
                            },
                        });
                    }
                    return;
                }

                // Handle component mounting/unmounting
                if (!component) return;

                const key = `${component}-${evt.timestamp || Date.now()}`;
                const props = { ...evt, ...evt.payload };

                if (action === 'open_component' || action === 'append_trace_card') {
                    setMountedComponents((prev) => prev.concat({ id: key, props: { component, ...props } }));
                    return;
                }

                if (action === 'update_component') {
                    setMountedComponents((prev) => prev.concat({ id: key, props: { component, ...props } }));
                    return;
                }

                if (action === 'close_component') {
                    setMountedComponents((prev) => prev.filter((m) => !m.id.startsWith(component)));
                    return;
                }
            },
            error: (err: any) => {
                console.error('UI events subscription error:', err);
            },
        });

        return () => {
            try {
                subscription.unsubscribe();
            } catch {
                // ignore
            }
        };
    }, [client, tenantId]);

    // Also watch the job store for pending approvals (from job-scoped trace events)
    useEffect(() => {
        const unsubscribe = useJobStore.subscribe((state, prevState) => {
            // Find any job that just became isPendingApproval
            for (const [jobId, job] of Object.entries(state.jobs)) {
                const prevJob = prevState?.jobs?.[jobId];
                if (
                    job.isPendingApproval &&
                    job.pendingApprovalPayload &&
                    (!prevJob || !prevJob.isPendingApproval)
                ) {
                    // This job just entered pending approval state
                    setPendingBlueprint({
                        jobId,
                        payload: job.pendingApprovalPayload,
                    });
                    break; // Only show one at a time
                }
            }
        });

        return unsubscribe;
    }, []);

    const dismissBlueprint = useCallback(() => {
        setPendingBlueprint(null);
    }, []);

    // Render mounted components via central registry
    const renderedComponents = useMemo(() => {
        return mountedComponents.map((m) => {
            const componentId = m.props?.component as string;
            const rendered = renderUIComponent(componentId, m.props);
            if (!rendered) return null;
            return (
                <div key={m.id} style={{ marginBottom: 16 }}>
                    {rendered}
                </div>
            );
        });
    }, [mountedComponents]);

    return (
        <UIEventDispatcherContext.Provider value={{ pendingBlueprint, dismissBlueprint }}>
            {children}
            {renderedComponents}
            {pendingBlueprint && (
                <BlueprintApprovalModal
                    jobId={pendingBlueprint.jobId}
                    payload={pendingBlueprint.payload}
                    onDismiss={dismissBlueprint}
                />
            )}
        </UIEventDispatcherContext.Provider>
    );
}
