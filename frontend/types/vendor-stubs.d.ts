// Type-only stubs to prevent TS from traversing heavy vendored feature trees during integration
// Runtime uses webpack aliases to real code; these stubs are for the type-checker only.

declare module '@/features/AgentSetting' { const M: any; export = M; }
declare module '@/features/AgentSetting/*' { const M: any; export = M; }

declare module '@/features/PluginStore' { const M: any; export = M; }
declare module '@/features/PluginStore/*' { const M: any; export = M; }

declare module '@/features/PluginDevModal' { const M: any; export = M; }
declare module '@/features/PluginDevModal/*' { const M: any; export = M; }

declare module '@/components/Plugins/*' { const M: any; export = M; }
declare module '@/components/ModelSelect' { const M: any; export = M; }
declare module '@/components/InlineTable' { const M: any; export = M; }
declare module '@/components/ManifestPreviewer' { const M: any; export = M; }
declare module '@/components/KeyValueEditor' { const M: any; export = M; }
declare module '@/components/MCPStdioCommandInput' { const M: any; export = M; }
declare module '@/components/PublishedTime' { const M: any; export = M; }

declare module '@/features/MCP*' { const M: any; export = M; }

declare module '@/hooks/*' { const M: any; export = M; }

declare module '@/styles/electron' { const M: any; export = M; }

// Minimal stubs for vendored const and utils used by Lobe sources at type-time
declare module '@lobechat/const' {
  export const LOBE_CHAT_OBSERVATION_ID: any
  export const LOBE_CHAT_TRACE_ID: any
  export const MESSAGE_CANCEL_FLAT: any
  export const CURRENT_VERSION: any
}

declare module '@/utils/merge' {
  export function merge<T extends object, U extends object>(target: T, source: U): T & U
}
