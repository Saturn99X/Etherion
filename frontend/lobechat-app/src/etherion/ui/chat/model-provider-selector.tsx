'use client';

import { useMemo } from 'react';
import { Select, Space } from 'antd';
import { createStyles } from 'antd-style';
import { useThreadPrefStore, EMPTY_PREFS } from '@etherion/stores/thread-pref-store';
import { LOBE_DEFAULT_MODEL_LIST } from 'model-bank';
import type { LobeDefaultAiModelListItem } from 'model-bank';

const useStyles = createStyles(({ token, css }) => ({
    container: css`
    display: flex;
    align-items: center;
    gap: ${token.marginXS}px;
  `,
}));

interface ModelProviderSelectorProps {
    threadId: string;
    branchId?: string;
    className?: string;
}

const titleCase = (s: string) =>
    s.replace(/(^|[\s-_])([a-z])/g, (_, p1, p2) => p1 + p2.toUpperCase());

export const ModelProviderSelector = ({
    threadId,
    branchId,
    className
}: ModelProviderSelectorProps) => {
    const { styles } = useStyles();

    const prefKey = useMemo(() => `${threadId}::${branchId ?? 'root'}`, [threadId, branchId]);
    const prefs = useThreadPrefStore((s) => s.prefs[prefKey] || EMPTY_PREFS);
    const setPrefs = useThreadPrefStore((s) => s.setPrefs);

    const chatModels = useMemo(
        () => (LOBE_DEFAULT_MODEL_LIST.filter((m) => m.type === 'chat') as LobeDefaultAiModelListItem[]),
        []
    );

    const providerOptions = useMemo(() => {
        const set = new Set<string>(chatModels.map((m) => m.providerId));
        return Array.from(set).sort();
    }, [chatModels]);

    const modelsByProvider = useMemo(() => {
        const map = new Map<string, LobeDefaultAiModelListItem[]>();
        for (const m of chatModels) {
            const arr = map.get(m.providerId) || [];
            arr.push(m);
            map.set(m.providerId, arr);
        }
        for (const [k, arr] of map.entries()) {
            arr.sort((a, b) => (a.displayName || a.id).localeCompare(b.displayName || b.id));
            map.set(k, arr);
        }
        return map;
    }, [chatModels]);

    const provider = prefs.provider || providerOptions[0];
    const availableModels = modelsByProvider.get(provider) || [];
    const model = prefs.model || (availableModels[0]?.id || '');

    return (
        <div className={className}>
            <Space className={styles.container}>
                <Select
                    size="small"
                    style={{ minWidth: 120 }}
                    value={provider}
                    onChange={(v) => {
                        const firstModel = modelsByProvider.get(v)?.[0]?.id;
                        setPrefs(threadId, { provider: v, model: firstModel }, branchId);
                    }}
                    options={providerOptions.map((p) => ({
                        value: p,
                        label: titleCase(p),
                    }))}
                />

                <Select
                    size="small"
                    style={{ minWidth: 160 }}
                    value={model}
                    onChange={(v) => setPrefs(threadId, { model: v, provider }, branchId)}
                    options={availableModels.map((m) => ({
                        value: m.id,
                        label: m.displayName || m.id,
                    }))}
                    showSearch
                    filterOption={(input, option) =>
                        (option?.label ?? '').toString().toLowerCase().includes(input.toLowerCase())
                    }
                />
            </Space>
        </div>
    );
};

export default ModelProviderSelector;
