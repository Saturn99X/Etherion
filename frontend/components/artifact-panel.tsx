"use client"

import React from "react"
import DOMPurify from "isomorphic-dompurify"

export type Artifact = { kind: 'html' | 'svg' | 'doc' | 'code'; content: string; title?: string }

interface ArtifactPanelProps {
  artifacts: Artifact[]
}

export function ArtifactPanel({ artifacts }: ArtifactPanelProps) {
  return (
    <div className="space-y-3 w-full">
      {artifacts.map((a, idx) => (
        <div key={idx} className="glass p-3 rounded">
          {a.title && <div className="text-xs font-medium text-white/80 mb-2">{a.title}</div>}
          {a.kind === 'html' && (
            <div
              className="prose prose-invert max-w-none sandboxed-html"
              dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(a.content) }}
            />
          )}
          {a.kind === 'svg' && (
            <div
              className="max-w-full overflow-auto"
              dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(a.content) }}
            />
          )}
          {a.kind === 'code' && (
            <pre className="text-xs bg-black/40 p-3 rounded overflow-auto">
              <code>{a.content}</code>
            </pre>
          )}
          {a.kind === 'doc' && (
            <div className="text-xs text-white/80 whitespace-pre-wrap">{a.content}</div>
          )}
        </div>
      ))}
    </div>
  )
}
