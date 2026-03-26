"use client";

import React from "react";

export interface DataTableProps {
  title?: string;
  columns?: string[]; // optional explicit column order
  rows?: Array<Record<string, any>>; // array of objects
  emptyMessage?: string;
}

export function DataTable({ title = "Data Table", columns, rows = [], emptyMessage = "No data" }: DataTableProps) {
  const derivedColumns = React.useMemo(() => {
    if (columns && columns.length) return columns;
    const first = rows[0];
    if (!first) return [] as string[];
    return Object.keys(first);
  }, [columns, rows]);

  return (
    <div className="glass-card border border-white/10 rounded-lg p-3 text-white text-sm overflow-auto">
      <div className="font-semibold mb-2">{title}</div>
      {rows.length === 0 ? (
        <div className="text-white/60">{emptyMessage}</div>
      ) : (
        <table className="w-full text-left border-collapse">
          <thead>
            <tr>
              {derivedColumns.map((col) => (
                <th key={col} className="border-b border-white/10 py-2 pr-3 text-white/80 font-medium">
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, idx) => (
              <tr key={idx} className="hover:bg-white/5">
                {derivedColumns.map((col) => (
                  <td key={col} className="py-2 pr-3 align-top text-white/90">
                    {String(row?.[col] ?? "")}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

export default { DataTable };

