export enum ChatErrorType {
  UnknownChatFetchError = 'UnknownChatFetchError',
  StreamChunkError = 'StreamChunkError',
}

export type ChatMessageError = {
  message: string;
  type: ChatErrorType | string;
  body?: any;
};

// Minimal error types used by vendored fetch/const modules
export type ErrorType = any;
export interface ErrorResponse {
  body: any;
  errorType: ErrorType | string;
}

// Token usage breakdown used across runtime/types
export interface ModelTokensUsage {
  inputCachedTokens?: number;
  inputCacheMissTokens?: number;
  inputWriteCacheTokens?: number;
  inputTextTokens?: number;
  inputImageTokens?: number;
  inputAudioTokens?: number;
  inputCitationTokens?: number;
  outputTextTokens?: number;
  outputImageTokens?: number;
  outputAudioTokens?: number;
  outputReasoningTokens?: number;
  acceptedPredictionTokens?: number;
  rejectedPredictionTokens?: number;
  totalInputTokens?: number;
  totalOutputTokens?: number;
  totalTokens?: number;
}

export interface ModelUsage extends ModelTokensUsage {
  cost?: number;
}

export interface ModelPerformance {
  tps?: number;
  ttft?: number;
  duration?: number;
  latency?: number;
}

export type ModelReasoning = {
  content?: string;
  signature?: string;
  [k: string]: any;
};

export type ChatImageChunk = {
  // keep flexible; fetchSSE treats this as opaque
  [k: string]: any;
};

export type GroundingSearch = {
  // opaque to UI; streaming payload container
  [k: string]: any;
};

// Minimal trace map type consumed by const/trace.ts
export type TraceNameMap = any;

export type ResponseAnimationStyle = 'smooth' | 'none';
export type ResponseAnimation =
  | ResponseAnimationStyle
  | {
      text?: ResponseAnimationStyle;
      speed?: number;
    };

// Re-export tool-call types from model-runtime to keep a single source of truth
export type { MessageToolCall } from '@lobechat/model-runtime';

// --- Additional stubs required by vendored const modules ---
export enum KeyEnum {
  Mod = 'Mod',
  Shift = 'Shift',
  Alt = 'Alt',
  Ctrl = 'Ctrl',
  Enter = 'Enter',
  K = 'K',
  Backquote = 'Backquote',
  Backslash = 'Backslash',
  BracketLeft = 'BracketLeft',
  BracketRight = 'BracketRight',
  QuestionMark = 'QuestionMark',
  Comma = 'Comma',
  Number = 'Number',
  LeftDoubleClick = 'LeftDoubleClick',
  Backspace = 'Backspace',
}

export enum HotkeyGroupEnum {
  Global = 'Global',
  Chat = 'Chat',
  Desktop = 'Desktop',
  Essential = 'Essential',
  Conversation = 'Conversation',
}

export enum HotkeyScopeEnum {
  Global = 'Global',
  Chat = 'Chat',
  Desktop = 'Desktop',
  Files = 'Files',
  Image = 'Image',
}

export enum HotkeyEnum {
  ToggleCommandPanel = 'ToggleCommandPanel',
  SendMessage = 'SendMessage',
  NewChat = 'NewChat',
}

export enum DesktopHotkeyEnum {
  ToggleWindow = 'ToggleWindow',
  ShowApp = 'ShowApp',
  OpenSettings = 'OpenSettings',
}

// Hotkey item shapes used by const/hotkeys.ts
export type HotkeyItem = {
  group: HotkeyGroupEnum;
  id: HotkeyEnum;
  keys: string;
  scopes?: HotkeyScopeEnum[];
  nonEditable?: boolean;
};

export type DesktopHotkeyItem = {
  id: DesktopHotkeyEnum;
  keys: string;
  nonEditable?: boolean;
};

export type DesktopHotkeyConfig = Record<DesktopHotkeyEnum, string>;

export enum LobeSessionType {
  Agent = 'agent',
  Group = 'group',
}

export enum TopicDisplayMode {
  ByTime = 'ByTime',
  ByCategory = 'ByCategory',
}
