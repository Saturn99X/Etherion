"use client";

import React from "react";

interface ExcelGeneratorProps {
  title?: string;
  sheetName?: string;
  rows?: Array<Record<string, any>>;
}

export default function ExcelGeneratorUI({ title = "Excel Generator", sheetName = "Sheet1", rows = [] }: ExcelGeneratorProps) {
  const columns = rows.length ? Object.keys(rows[0]) : [];
  return (
    <div className="glass-card border border-white/10 rounded-lg p-3 text-white text-sm w-full max-w-3xl overflow-auto">
      <div className="font-semibold mb-2">{title}</div>
      <div className="text-white/80 text-xs mb-2">Worksheet: {sheetName} • Rows: {rows.length}</div>
      <table className="min-w-full text-xs border border-white/10">
        <thead>
          <tr className="bg-white/5">
            {columns.map((c) => (
              <th key={c} className="text-left px-2 py-1 border-b border-white/10">{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="odd:bg-white/0 even:bg-white/5">
              {columns.map((c) => (
                <td key={c} className="px-2 py-1 border-b border-white/10 whitespace-pre">{String(r[c] ?? "")}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {!rows.length && (
        <div className="text-white/60 mt-2">No rows provided.</div>
      )}
    </div>
  );
}

