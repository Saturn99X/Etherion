// Ambient module declarations for vendored Lobe dependencies not installed in Etherion

declare module 'vitest';
declare module 'react-virtuoso';
declare module 'markdown-to-txt';
declare module 'numeral';
declare module 'zustand-utils' {
  const anyExport: any;
  export default anyExport;
  export const createContext: any;
}
declare module '@lobehub/tts';
declare module '@lobehub/tts/react' {
  export type TTSOptions = any;
  export type OpenAITTSOptions = any;
  export type EdgeSpeechOptions = any;
  export type MicrosoftSpeechOptions = any;
  export const useOpenAITTS: any;
  export const useEdgeSpeech: any;
  export const useMicrosoftSpeech: any;
}
declare module '@lobechat/prompts';
declare module '@lobehub/analytics';

declare module 'lodash-es' {
  export const merge: any;
  export const mergeWith: any;
  export const isEmpty: any;
  const anyExport: any;
  export default anyExport;
}

// Local app hooks used by components
declare module '@/hooks/use-toast' { export const useToast: any; export const toast: any }
declare module '@/hooks/use-mobile' { export const useIsMobile: any }
declare module '@/hooks/use-ui-events' { export const UIEventProvider: any; export const useUIEvents: any }

// Local libs/services/utilities referenced by vendor hooks
declare module '@/libs/swr' { export const useOnlyFetchOnceSWR: any }
declare module '@/services/_header' { export const createHeaderWithOpenAI: any }
declare module '@/services/_url' { export const API_ENDPOINTS: any }
declare module '@/utils/tokenizer' { export const encodeAsync: any }
