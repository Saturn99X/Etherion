"use client";

import React, { useState } from "react";

interface DocumentGeneratorProps {
  title?: string;
  content?: string;
}

export default function DocumentGeneratorUI({ title = "Document Generator", content = "" }: DocumentGeneratorProps) {
  const [value, setValue] = useState<string>(content);

  return (
    <div className="glass-card border border-white/10 rounded-lg p-3 text-white text-sm w-full max-w-2xl">
      <div className="font-semibold mb-2">{title}</div>
      <textarea
        className="w-full h-40 bg-black/30 border border-white/10 rounded p-2 text-white"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="Write your document..."
      />
      <div className="mt-2 text-white/60 text-xs">Length: {value.length} chars</div>
    </div>
  );
}

