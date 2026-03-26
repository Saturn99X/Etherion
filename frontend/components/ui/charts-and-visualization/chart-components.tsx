"use client";

import React from "react";

export interface ChartProps {
  title?: string;
  data?: Array<{ label: string; value: number }>;
}

export function BarChart({ title = "Bar Chart", data = [] }: ChartProps) {
  return (
    <div className="glass-card border border-white/10 rounded-lg p-3 text-white text-sm">
      <div className="font-semibold mb-2">{title}</div>
      <div className="flex items-end gap-2 h-24">
        {data.map((d, i) => (
          <div key={i} className="bg-blue-500/70" style={{ width: 16, height: Math.max(4, d.value) }} title={`${d.label}: ${d.value}`} />
        ))}
      </div>
    </div>
  );
}

export function LineChart({ title = "Line Chart", data = [] }: ChartProps) {
  // Placeholder simple renderer
  return (
    <div className="glass-card border border-white/10 rounded-lg p-3 text-white text-sm">
      <div className="font-semibold mb-2">{title}</div>
      <div className="text-white/70">points: {data.length}</div>
    </div>
  );
}

export default { BarChart, LineChart };
