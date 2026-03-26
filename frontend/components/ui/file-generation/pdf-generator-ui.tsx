"use client";

import React from "react";

interface PDFGeneratorProps {
  title?: string;
  filename?: string;
  content?: string;
}

export default function PDFGeneratorUI({ title = "PDF Generator", filename = "document.pdf", content = "" }: PDFGeneratorProps) {
  return (
    <div className="glass-card border border-white/10 rounded-lg p-3 text-white text-sm w-full max-w-2xl">
      <div className="font-semibold mb-2">{title}</div>
      <div className="text-white/80 text-xs mb-2">Filename: {filename}</div>
      <div className="bg-black/30 border border-white/10 rounded p-3 text-white/90 whitespace-pre-wrap min-h-16">
        {content || "No content provided."}
      </div>
      <div className="mt-2 text-white/60 text-xs">This is a placeholder preview. Hook to a real PDF service next.</div>
    </div>
  );
}

