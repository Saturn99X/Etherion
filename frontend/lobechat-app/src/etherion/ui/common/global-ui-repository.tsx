'use client';

/**
 * global-ui-repository.tsx
 *
 * Central registry of all renderable Etherion UI components.
 * Used by `ui-event-dispatcher` and any system that needs to
 * dynamically mount a named component from a backend UI event.
 *
 * Architecture:
 *   backend event → component: "charts-and-visualization/pie-chart"
 *                → renderUIComponent("charts-and-visualization/pie-chart", payload)
 *                → <PieChart {...payload} />
 */

import React, { Suspense, type ReactNode } from 'react';
import { Spin } from 'antd';
import { Flexbox } from 'react-layout-kit';

// ─── Chart / Viz ──────────────────────────────────────────────────────────────
import { BarChart, LineChart } from '../charts/chart-components';
import { DataTable } from '../charts/data-tables';
import { PieChart, Gauge, Sparkline, MetricCards, Heatmap, ActivityFeed } from '../charts/visualization-tools';

// ─── Agent-specific dashboards ────────────────────────────────────────────────
const SalesTeamUI = React.lazy(() => import('../agent-specific/sales-team-ui').then(m => ({ default: m.SalesTeamUI })));
const AnalyticsTeamUI = React.lazy(() => import('../agent-specific/analytics-team-ui').then(m => ({ default: m.AnalyticsTeamUI })));
const ContentTeamUI = React.lazy(() => import('../agent-specific/content-team-ui').then(m => ({ default: m.ContentTeamUI })));
const DevelopmentTeamUI = React.lazy(() => import('../agent-specific/development-team-ui').then(m => ({ default: m.DevelopmentTeamUI })));
const FinancialTeamUI = React.lazy(() => import('../agent-specific/financial-team-ui').then(m => ({ default: m.FinancialTeamUI })));
const MarketingTeamUI = React.lazy(() => import('../agent-specific/marketing-team-ui').then(m => ({ default: m.MarketingTeamUI })));

// ─── Triggered UI ─────────────────────────────────────────────────────────────
const AgentBlueprintUI = React.lazy(() => import('../triggered-ui/agent-blueprint-ui'));
const AgentBlueprintOrbital = React.lazy(() => import('../triggered-ui/agent-blueprint-orbital'));
const ExecutionTraceUI = React.lazy(() => import('../triggered-ui/execution-trace-ui'));
const ConfirmationModal = React.lazy(() => import('../triggered-ui/confirmation-modals'));

// ─── File generation UI ───────────────────────────────────────────────────────
const DocumentGeneratorUI = React.lazy(() => import('../file-generation/document-generator-ui'));
const PDFGeneratorUI = React.lazy(() => import('../file-generation/pdf-generator-ui'));
const ExcelGeneratorUI = React.lazy(() => import('../file-generation/excel-generator-ui'));

// ─── Panels ───────────────────────────────────────────────────────────────────
const ArtifactPanel = React.lazy(() => import('../panels/artifact-panel'));
const RepositoryBrowser = React.lazy(() => import('../panels/repository-browser'));
const ReplayViewer = React.lazy(() => import('../panels/replay-viewer'));
const ExecutionTracePanel = React.lazy(() => import('../panels/execution-trace-panel'));

// ─── Dashboard ────────────────────────────────────────────────────────────────
const JobStatusTracker = React.lazy(() => import('../dashboard/job-status-tracker'));
const JobApprovalCTA = React.lazy(() => import('../dashboard/job-approval-cta').then(m => ({ default: m.JobApprovalCTA })));

// ─── Types ────────────────────────────────────────────────────────────────────

export type UIComponentId = string;

export interface UIComponentEntry {
  /** Human-readable display name */
  displayName: string;
  /** Component category (charts, triggered-ui, etc.) */
  category: string;
  /** Factory function that renders the component with given props */
  render: (props: Record<string, unknown>) => ReactNode;
}

// ─── Loading fallback ─────────────────────────────────────────────────────────

const LoadingFallback = () => (
  <Flexbox align="center" justify="center" style={{ padding: 32 }}>
    <Spin size="small" />
  </Flexbox>
);

const lazy = (el: ReactNode) => (
  <Suspense fallback={<LoadingFallback />}>{el}</Suspense>
);

// ─── Registry ─────────────────────────────────────────────────────────────────

/**
 * Central map from event `component` field → renderer.
 * Keys match the `component` field emitted by backend UI events.
 */
export const UI_COMPONENT_REGISTRY: Record<UIComponentId, UIComponentEntry> = {
  // ── Charts (synchronous — no lazy needed) ────────────────────────────────
  'charts-and-visualization/chart-components:bar': {
    displayName: 'Bar Chart',
    category: 'charts',
    render: (p) => <BarChart title={p.title as string} data={p.data as any} />,
  },
  'charts-and-visualization/chart-components:line': {
    displayName: 'Line Chart',
    category: 'charts',
    render: (p) => <LineChart title={p.title as string} data={p.data as any} />,
  },
  'charts-and-visualization/data-table': {
    displayName: 'Data Table',
    category: 'charts',
    render: (p) => <DataTable title={p.title as string} columns={p.columns as any} rows={p.rows as any} />,
  },
  'charts-and-visualization/pie-chart': {
    displayName: 'Pie Chart',
    category: 'charts',
    render: (p) => <PieChart title={p.title as string} data={p.data as any} />,
  },
  'charts-and-visualization/gauge': {
    displayName: 'Gauge',
    category: 'charts',
    render: (p) => <Gauge title={p.title as string} value={p.value as number} max={p.max as number} unit={p.unit as string} />,
  },
  'charts-and-visualization/sparkline': {
    displayName: 'Sparkline',
    category: 'charts',
    render: (p) => <Sparkline data={p.data as any} label={p.label as string} />,
  },
  'charts-and-visualization/metric-cards': {
    displayName: 'Metric Cards',
    category: 'charts',
    render: (p) => <MetricCards metrics={p.metrics as any} />,
  },
  'charts-and-visualization/heatmap': {
    displayName: 'Heatmap',
    category: 'charts',
    render: (p) => <Heatmap title={p.title as string} data={p.data as any} rowLabels={p.rowLabels as any} colLabels={p.colLabels as any} />,
  },
  'charts-and-visualization/activity-feed': {
    displayName: 'Activity Feed',
    category: 'charts',
    render: (p) => <ActivityFeed title={p.title as string} items={p.items as any} />,
  },

  // ── Agent-specific dashboards ────────────────────────────────────────────
  'agent-specific/sales-team-ui': {
    displayName: 'Sales Team Dashboard',
    category: 'agent-specific',
    render: (p) => lazy(<SalesTeamUI data={p.data as any} loading={p.loading as any} />),
  },
  'agent-specific/analytics-team-ui': {
    displayName: 'Analytics Team Dashboard',
    category: 'agent-specific',
    render: (p) => lazy(<AnalyticsTeamUI data={p.data as any} loading={p.loading as any} />),
  },
  'agent-specific/content-team-ui': {
    displayName: 'Content Team Dashboard',
    category: 'agent-specific',
    render: (p) => lazy(<ContentTeamUI data={p.data as any} loading={p.loading as any} />),
  },
  'agent-specific/development-team-ui': {
    displayName: 'Development Team Dashboard',
    category: 'agent-specific',
    render: (p) => lazy(<DevelopmentTeamUI data={p.data as any} loading={p.loading as any} />),
  },
  'agent-specific/financial-team-ui': {
    displayName: 'Financial Team Dashboard',
    category: 'agent-specific',
    render: (p) => lazy(<FinancialTeamUI data={p.data as any} loading={p.loading as any} />),
  },
  'agent-specific/marketing-team-ui': {
    displayName: 'Marketing Team Dashboard',
    category: 'agent-specific',
    render: (p) => lazy(<MarketingTeamUI data={p.data as any} loading={p.loading as any} />),
  },

  // ── Triggered UI ─────────────────────────────────────────────────────────
  'triggered-ui/agent-blueprint-ui': {
    displayName: 'Agent Blueprint',
    category: 'triggered-ui',
    render: (p) => lazy(<AgentBlueprintUI {...(p as any)} />),
  },
  'triggered-ui/agent-blueprint-orbital': {
    displayName: 'Blueprint Orbital',
    category: 'triggered-ui',
    render: (p) => lazy(<AgentBlueprintOrbital {...(p as any)} />),
  },
  'triggered-ui/execution-trace-ui': {
    displayName: 'Execution Trace (Triggered)',
    category: 'triggered-ui',
    render: (p) => lazy(<ExecutionTraceUI jobId={p.job_id as string} />),
  },
  'triggered-ui/confirmation-modals:basic': {
    displayName: 'Confirmation Modal',
    category: 'triggered-ui',
    render: (p) => lazy(
      <ConfirmationModal
        open
        {...(p as any)}
        onClose={() => {}}
        onAction={(v: string) => console.log('modal action', v)}
      />
    ),
  },

  // ── File generation ───────────────────────────────────────────────────────
  'file-generation/document-generator-ui': {
    displayName: 'Document Generator',
    category: 'file-generation',
    render: (p) => lazy(<DocumentGeneratorUI {...(p as any)} />),
  },
  'file-generation/pdf-generator-ui': {
    displayName: 'PDF Generator',
    category: 'file-generation',
    render: (p) => lazy(<PDFGeneratorUI {...(p as any)} />),
  },
  'file-generation/excel-generator-ui': {
    displayName: 'Excel Generator',
    category: 'file-generation',
    render: (p) => lazy(<ExcelGeneratorUI {...(p as any)} />),
  },

  // ── Panels ────────────────────────────────────────────────────────────────
  'panels/artifact-panel': {
    displayName: 'Artifact Panel',
    category: 'panels',
    render: (p) => lazy(<ArtifactPanel {...(p as any)} />),
  },
  'panels/repository-browser': {
    displayName: 'Repository Browser',
    category: 'panels',
    render: (p) => lazy(<RepositoryBrowser {...(p as any)} />),
  },
  'panels/replay-viewer': {
    displayName: 'Replay Viewer',
    category: 'panels',
    render: (p) => lazy(<ReplayViewer jobId={p.job_id as string} />),
  },
  'panels/execution-trace-panel': {
    displayName: 'Execution Trace Panel',
    category: 'panels',
    render: (p) => lazy(<ExecutionTracePanel jobId={p.job_id as string} />),
  },

  // ── Dashboard ─────────────────────────────────────────────────────────────
  'dashboard/job-status-tracker': {
    displayName: 'Job Status Tracker',
    category: 'dashboard',
    render: (p) => lazy(<JobStatusTracker jobId={p.job_id as string} />),
  },
  'dashboard/job-approval-cta': {
    displayName: 'Job Approval CTA',
    category: 'dashboard',
    render: (p) => lazy(<JobApprovalCTA jobId={p.job_id as string} onOpenApproval={p.onOpenApproval as any} />),
  },
};

// ─── Public API ───────────────────────────────────────────────────────────────

/**
 * Render a named UI component by its registry ID.
 * Returns null if the componentId is not registered.
 */
export function renderUIComponent(
  componentId: UIComponentId,
  props: Record<string, unknown> = {},
): ReactNode {
  const entry = UI_COMPONENT_REGISTRY[componentId];
  if (!entry) {
    console.warn(`[GlobalUIRepository] Unknown component: ${componentId}`);
    return null;
  }
  return entry.render(props);
}

/**
 * List all registered component IDs, optionally filtered by category.
 */
export function listUIComponents(category?: string): Array<{ id: UIComponentId; entry: UIComponentEntry }> {
  return Object.entries(UI_COMPONENT_REGISTRY)
    .filter(([, e]) => !category || e.category === category)
    .map(([id, entry]) => ({ id, entry }));
}

/**
 * Check whether a component ID is registered.
 */
export function isUIComponentRegistered(componentId: UIComponentId): boolean {
  return componentId in UI_COMPONENT_REGISTRY;
}

export default { renderUIComponent, listUIComponents, isUIComponentRegistered, UI_COMPONENT_REGISTRY };
