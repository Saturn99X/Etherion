"use client"

import { createStyles } from 'antd-style';
import { Flexbox } from 'react-layout-kit';
import { Button, Dropdown, Space, Tooltip, Avatar, Badge, Tag, Modal } from 'antd';
import { ActionIcon, Markdown } from '@lobehub/ui';
import { ChatItem } from '@lobehub/ui/chat';
import {
  Copy, RefreshCw, Trash2, User, Bot, GitBranch, Eye,
  Package, Volume2, VolumeX, Check, X, MoreVertical, Loader2
} from 'lucide-react';
import { useMemo, useRef, useState } from 'react';

import { useThreadPrefStore, EMPTY_PREFS } from '@etherion/stores/thread-pref-store';
import { useToolcallStore } from '@etherion/stores/toolcall-store';
import { summarizeParams, redactParams } from '@etherion/lib/lobe/toolcall-bridge';
import ConfirmationModal from '../triggered-ui/confirmation-modals';
import { ArtifactPanel } from './artifact-panel';

const useStyles = createStyles(({ token, css }) => ({
  toolSuggestion: css`
    padding: ${token.paddingXS}px ${token.paddingSM}px;
    background: ${token.colorFillQuaternary};
    border-radius: ${token.borderRadius}px;
    border: 1px solid ${token.colorBorderSecondary};
    font-size: 12px;
  `,
  cotContainer: css`
    margin-top: ${token.marginXS}px;
    padding: ${token.paddingXS}px;
    background: ${token.colorFillQuaternary};
    border-radius: ${token.borderRadius}px;
    font-size: 11px;
    color: ${token.colorTextSecondary};
    border-left: 2px solid ${token.colorPrimary};
  `,
}));

interface MessageMetadata {
  cot?: string;
  artifacts?: Array<{ kind: string; content?: string; title?: string }>;
  toolExecId?: string;
  showCot?: boolean;
  showArtifacts?: boolean;
}

interface Message {
  id: string;
  role: 'user' | 'assistant' | 'tool';
  content: string;
  timestamp: Date;
  metadata?: MessageMetadata;
}

interface MessageBubbleProps {
  message: Message;
  onCopy?: (content: string) => void;
  onRetry?: (messageId: string) => void;
  onDelete?: (messageId: string) => void;
  onBranch?: () => void;
  onToggleCot?: () => void;
  onToggleArtifacts?: () => void;
  statusChip?: string;
  forkIndicator?: boolean;
  threadId?: string;
  branchId?: string;
  onApproveTool?: (payload: { messageId: string; suggestionId: string; toolName: string; params: Record<string, any> }) => void;
  onDenyTool?: (payload: { messageId: string; suggestionId: string }) => void;
}

export const MessageBubble = ({
  message,
  onCopy,
  onRetry,
  onDelete,
  onBranch,
  onToggleCot,
  onToggleArtifacts,
  statusChip,
  forkIndicator,
  threadId,
  branchId,
  onApproveTool,
  onDenyTool,
}: MessageBubbleProps) => {
  const { styles } = useStyles();
  const isUser = message.role === 'user';
  const [speaking, setSpeaking] = useState(false);
  const utterRef = useRef<SpeechSynthesisUtterance | null>(null);

  const prefKey = useMemo(() => `${threadId || 'default'}::${branchId ?? 'root'}`, [threadId, branchId]);
  const prefs = useThreadPrefStore((s) => s.prefs[prefKey] || EMPTY_PREFS);
  const ttsVoicePref = prefs.ttsVoice;
  const setPrefs = useThreadPrefStore((s) => s.setPrefs);

  const pickVoice = useMemo(() => {
    if (typeof window === 'undefined') return undefined;
    const synth = window.speechSynthesis;
    if (!synth) return undefined;
    const voices = synth.getVoices() || [];
    if (ttsVoicePref) return voices.find((v) => v.name === ttsVoicePref) || voices[0];
    const lang = (navigator as any).language || 'en-US';
    return voices.find((v) => v.lang?.toLowerCase().startsWith(lang.toLowerCase().slice(0, 2))) || voices[0];
  }, [ttsVoicePref]);

  const stopTTS = () => {
    try {
      if (typeof window === 'undefined') return;
      window.speechSynthesis?.cancel();
      utterRef.current = null;
      setSpeaking(false);
    } catch { }
  };

  const startTTS = () => {
    if (typeof window === 'undefined' || !window.speechSynthesis) return;
    const text = (message.content || '').slice(0, 10000);
    const u = new SpeechSynthesisUtterance(text);
    const v = pickVoice;
    if (v) {
      u.voice = v;
      if (!ttsVoicePref) setPrefs(threadId || 'default', { ttsVoice: v.name }, branchId);
    }
    u.onend = () => setSpeaking(false);
    u.onerror = () => setSpeaking(false);
    utterRef.current = u;
    setSpeaking(true);
    const synth = window.speechSynthesis;
    const trySpeak = () => { synth.speak(u); };
    if (synth.getVoices().length === 0) {
      const handler = () => { trySpeak(); synth.removeEventListener('voiceschanged', handler); };
      synth.addEventListener('voiceschanged', handler);
    } else { trySpeak(); }
  };

  const threadKey = threadId || 'default';
  const toolStore = useToolcallStore();
  const suggestions = toolStore.getSuggestions(threadKey, message.id) || [];
  const invocations = toolStore.getInvocations(threadKey, message.id) || [];
  const clearSuggestion = toolStore.clearSuggestion;

  const [modalOpen, setModalOpen] = useState(false);
  const [selectedSuggestion, setSelectedSuggestion] = useState<null | { id: string; toolName: string; previewParams: Record<string, any> }>(null);

  const openApproveModal = (sugg: { id: string; toolName: string; previewParams: Record<string, any> }) => {
    setSelectedSuggestion(sugg);
    setModalOpen(true);
  };
  const closeApproveModal = () => {
    setModalOpen(false);
    setSelectedSuggestion(null);
  };

  const sanitizedCot = useMemo(() => {
    try {
      let t = (message.metadata?.cot || '').toString();
      t = t.replace(/<\/?(thought|reasoning|system|debug)[^>]*>/gi, '');
      t = t.replace(/(api[_-]?key|secret|token|password)\s*[:=]\s*[\w-]{6,}/gi, '$1: ***');
      if (t.length > 2000) t = t.slice(0, 2000) + '…';
      return t.trim();
    } catch { return ''; }
  }, [message.metadata?.cot]);

  const actions = (
    <Space size={2}>
      <ActionIcon icon={Copy} size={{ blockSize: 24 }} onClick={() => {
        navigator.clipboard.writeText(message.content);
        onCopy?.(message.content);
      }} title="Copy" />
      {!isUser && (
        <>
          <ActionIcon icon={speaking ? VolumeX : Volume2} size={{ blockSize: 24 }} onClick={() => (speaking ? stopTTS() : startTTS())} title={speaking ? "Stop" : "Speak"} />
          <ActionIcon icon={RefreshCw} size={{ blockSize: 24 }} onClick={() => onRetry?.(message.id)} title="Retry" />
        </>
      )}
      <ActionIcon icon={GitBranch} size={{ blockSize: 24 }} onClick={() => onBranch?.()} title="Branch" />
      <ActionIcon icon={Trash2} size={{ blockSize: 24 }} onClick={() => onDelete?.(message.id)} title="Delete" danger />
    </Space>
  );

  return (
    <>
      <ChatItem
        placement={isUser ? 'right' : 'left'}
        avatar={{
          avatar: isUser ? <User size={18} /> : <Bot size={18} />,
          title: isUser ? 'User' : 'Assistant',
          backgroundColor: isUser ? '#1890ff' : '#722ed1',
        }}
        time={message.timestamp.getTime()}
        actions={actions}
        message={
          <Flexbox gap={8}>
            {forkIndicator && !isUser && (
              <Tag icon={<GitBranch size={12} />} color="default">Branch Start</Tag>
            )}
            <Markdown>{message.content}</Markdown>

            {statusChip && !isUser && (
              <div style={{ fontSize: '11px', opacity: 0.6, fontStyle: 'italic' }}>Status: {statusChip}</div>
            )}
          </Flexbox>
        }
        messageExtra={
          <Flexbox gap={12} style={{ marginTop: 8 }}>
            {!isUser && suggestions.length > 0 && (
              <Flexbox gap={4}>
                {suggestions.map((s) => (
                  <Flexbox key={s.id} horizontal align="center" gap={8} className={styles.toolSuggestion}>
                    <span style={{ fontWeight: 500 }}>{s.toolName}</span>
                    <span style={{ opacity: 0.6, fontSize: 11 }}>{summarizeParams(s.previewParams)}</span>
                    <Space size={4}>
                      <Button size="small" type="link" icon={<Check size={12} />} onClick={() => openApproveModal(s)}>Approve</Button>
                      <Button size="small" type="link" danger icon={<X size={12} />} onClick={() => {
                        clearSuggestion(threadKey, message.id, s.id);
                        onDenyTool?.({ messageId: message.id, suggestionId: s.id });
                      }}>Deny</Button>
                    </Space>
                  </Flexbox>
                ))}
              </Flexbox>
            )}

            {invocations.filter(inv => inv.status === 'running').length > 0 && (
              <Flexbox horizontal align="center" gap={8}>
                <Loader2 size={16} className="animate-spin" />
                <span>Processing Tool Call...</span>
              </Flexbox>
            )}

            {!isUser && (
              <Space size={12}>
                {sanitizedCot && (
                  <Button type="link" size="small" style={{ padding: 0, height: 'auto', fontSize: 11 }} onClick={() => onToggleCot?.()}>
                    {message.metadata?.showCot ? 'Hide Reasoning' : 'View Reasoning'}
                  </Button>
                )}
                {message.metadata?.artifacts && message.metadata.artifacts.length > 0 && (
                  <Button type="link" size="small" style={{ padding: 0, height: 'auto', fontSize: 11 }} onClick={() => onToggleArtifacts?.()}>
                    Artifacts ({message.metadata.artifacts.length})
                  </Button>
                )}
              </Space>
            )}

            {message.metadata?.showCot && sanitizedCot && (
              <div className={styles.cotContainer}>
                <div style={{ fontWeight: 600, marginBottom: 4 }}>Reasoning</div>
                <div style={{ whiteSpace: 'pre-wrap' }}>{sanitizedCot}</div>
              </div>
            )}

            {message.metadata?.showArtifacts && message.metadata?.artifacts && (
              <ArtifactPanel artifacts={message.metadata.artifacts as any} />
            )}
          </Flexbox>
        }
      />

      <ConfirmationModal
        open={!isUser && modalOpen}
        title={selectedSuggestion ? `Run tool: ${selectedSuggestion.toolName}` : 'Run tool'}
        message={selectedSuggestion ? `Params preview (redacted):\n\n${JSON.stringify(redactParams(selectedSuggestion.previewParams), null, 2)}` : ''}
        actions={[
          { label: 'Cancel', value: 'cancel', variant: 'secondary' },
          { label: 'Approve', value: 'approve', variant: 'primary' },
        ]}
        onClose={closeApproveModal}
        onAction={(val) => {
          if (val === 'approve' && selectedSuggestion) {
            onApproveTool?.({
              messageId: message.id,
              suggestionId: selectedSuggestion.id,
              toolName: selectedSuggestion.toolName,
              params: selectedSuggestion.previewParams,
            });
            clearSuggestion(threadKey, message.id, selectedSuggestion.id);
          }
          closeApproveModal();
        }}
      />
    </>
  );
};

export default MessageBubble;
