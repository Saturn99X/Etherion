"use client";

import React, { useEffect, useMemo, useState } from "react";
import { useApolloClient } from "@/components/apollo-provider";
import { SUBSCRIBE_TO_UI_EVENTS } from "@/lib/graphql-operations";
import ConfirmationModal from "@/components/ui/triggered-ui/confirmation-modals";

// Optional lazy imports for heavy components
const AgentBlueprintUI = React.lazy(() => import("@/components/ui/triggered-ui/agent-blueprint-ui"));
const DocumentGeneratorUI = React.lazy(() => import("@/components/ui/file-generation/document-generator-ui"));
const PDFGeneratorUI = React.lazy(() => import("@/components/ui/file-generation/pdf-generator-ui"));
const ExcelGeneratorUI = React.lazy(() => import("@/components/ui/file-generation/excel-generator-ui"));

// Charts: import named components directly to avoid React.lazy default export constraint
import { BarChart, LineChart } from "@/components/ui/charts-and-visualization/chart-components";
import { DataTable } from "@/components/ui/charts-and-visualization/data-tables";

// Example mapping for agent-specific and other components
// Add more IDs here incrementally. Unknown components will be ignored safely.
const COMPONENT_RENDERERS: Record<string, (props: any) => React.ReactNode> = {
  "triggered-ui/agent-blueprint-ui": (props) => (
    <React.Suspense fallback={null}>
      <AgentBlueprintUI jobId={props?.jobId || props?.payload?.jobId} />
    </React.Suspense>
  ),
  // File generation components
  "file-generation/document-generator-ui": (props) => (
    <React.Suspense fallback={null}>
      <DocumentGeneratorUI {...(props?.payload || {})} />
    </React.Suspense>
  ),
  "file-generation/pdf-generator-ui": (props) => (
    <React.Suspense fallback={null}>
      <PDFGeneratorUI {...(props?.payload || {})} />
    </React.Suspense>
  ),
  "file-generation/excel-generator-ui": (props) => (
    <React.Suspense fallback={null}>
      <ExcelGeneratorUI {...(props?.payload || {})} />
    </React.Suspense>
  ),

  // Charts
  "charts-and-visualization/chart-components:bar": (props) => (
    <BarChart title={props?.payload?.title} data={props?.payload?.data} />
  ),
  "charts-and-visualization/chart-components:line": (props) => (
    <LineChart title={props?.payload?.title} data={props?.payload?.data} />
  ),
  "charts-and-visualization/data-table": (props) => (
    <DataTable title={props?.payload?.title} columns={props?.payload?.columns} rows={props?.payload?.rows} />
  ),

  // Agent-specific placeholders (replace with real renderers as these are classes not components)
  "agent-specific/marketing-team-ui:campaign-builder": (props) => (
    <div className="glass-card border-white/20 p-3 text-white text-sm">Marketing Campaign Builder (placeholder)</div>
  ),
  "agent-specific/development-team-ui:ci-panel": (props) => (
    <div className="glass-card border-white/20 p-3 text-white text-sm">Development CI Panel (placeholder)</div>
  ),
  "agent-specific/analytics-team-ui:overview": (props) => (
    <div className="glass-card border-white/20 p-3 text-white text-sm">Analytics Overview (placeholder)</div>
  ),
  "agent-specific/financial-team-ui:dashboard": (props) => (
    <div className="glass-card border-white/20 p-3 text-white text-sm">Financial Dashboard (placeholder)</div>
  ),
  "agent-specific/sales-team-ui:pipeline": (props) => (
    <div className="glass-card border-white/20 p-3 text-white text-sm">Sales Pipeline (placeholder)</div>
  ),
  "agent-specific/content-team-ui:editor": (props) => (
    <div className="glass-card border-white/20 p-3 text-white text-sm">Content Editor (placeholder)</div>
  ),
};

interface UIEvent {
  type: string; // action
  component?: string;
  payload?: any;
  job_id?: string;
  message?: string;
  timestamp?: string;
}

interface DispatcherProps {
  tenantId: number;
  mountArea?: "dashboard" | "drawer"; // Future: choose placement
}

export default function UIEventDispatcher({ tenantId }: DispatcherProps) {
  const client = useApolloClient();

  const [mounted, setMounted] = useState<Array<{ id: string; props: any }>>([]);
  const [modal, setModal] = useState<{
    open: boolean;
    title?: string;
    message?: string;
    actions?: Array<{ label: string; value: string; variant?: "primary" | "secondary" | "danger" }>;
  }>({ open: false });

  useEffect(() => {
    if (!tenantId) return;
    const sub = client
      .subscribe({ query: SUBSCRIBE_TO_UI_EVENTS, variables: { tenant_id: tenantId } })
      .subscribe({
        next: (result: any) => {
          const evt: UIEvent | undefined = result?.data?.subscribeToUIEvents;
          if (!evt) return;
          const action = evt.type;
          const component = evt.component;

          if (action === "show_modal") {
            const p = evt.payload || {};
            setModal({ open: true, title: p.title, message: p.message, actions: p.actions });
            return;
          }
          if (action === "close_modal") {
            setModal({ open: false });
            return;
          }

          if (!component) return;

          // Normalize key and props
          const key = `${component}-${evt.timestamp || Date.now()}`;
          const props = { ...evt, ...evt.payload };

          if (action === "open_component" || action === "append_trace_card") {
            setMounted((prev) => prev.concat({ id: key, props: { component, ...props } }));
            return;
          }

          if (action === "update_component") {
            // naive update: append another render instance
            setMounted((prev) => prev.concat({ id: key, props: { component, ...props } }));
            return;
          }

          if (action === "close_component") {
            setMounted((prev) => prev.filter((m) => !m.id.startsWith(component)));
            return;
          }
        },
        error: () => {},
      });

    return () => sub.unsubscribe();
  }, [tenantId, client]);

  const rendered = useMemo(() => {
    return mounted.map((m) => {
      const componentId = m.props?.component as string;
      const renderer = COMPONENT_RENDERERS[componentId];
      if (!renderer) return null;
      return (
        <div key={m.id} className="mb-3">
          {renderer(m.props)}
        </div>
      );
    });
  }, [mounted]);

  return (
    <>
      {rendered}
      <ConfirmationModal
        open={modal.open}
        title={modal.title}
        message={modal.message}
        actions={modal.actions}
        onClose={() => setModal({ open: false })}
        onAction={() => setModal({ open: false })}
      />
    </>
  );
}
