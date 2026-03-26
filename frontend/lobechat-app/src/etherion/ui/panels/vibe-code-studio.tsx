'use client';

import { useMemo, useState } from 'react';
import { Typography, Space, App, Card, Divider } from 'antd';
import { createStyles } from 'antd-style';
import { Flexbox } from 'react-layout-kit';
import { Bot, User, Sparkles, Hammer } from 'lucide-react';

import { useJobStore } from '@etherion/stores/job-store';
import { GoalInputBar } from '@etherion/ui/chat/goal-input-bar';
import { AgentBlueprintUI } from '../triggered-ui/agent-blueprint-ui';

const { Title, Text, Paragraph } = Typography;

const useStyles = createStyles(({ token, css }) => ({
    container: css`
    display: flex;
    flex-direction: column;
    height: 100vh;
    background: ${token.colorBgLayout};
  `,
    header: css`
    padding: ${token.paddingMD}px ${token.paddingLG}px;
    background: ${token.colorBgContainer};
    border-bottom: 1px solid ${token.colorBorderSecondary};
  `,
    scrollArea: css`
    flex: 1;
    overflow-y: auto;
    padding: ${token.paddingLG}px;
  `,
    messageList: css`
    max-width: 900px;
    margin: 0 auto;
    width: 100%;
  `,
    messageItem: css`
    margin-bottom: 24px;
  `,
    avatar: css`
    width: 32px;
    height: 32px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
  `,
    assistantAvatar: css`
    background: ${token.colorPrimaryBg};
    color: ${token.colorPrimary};
    border: 1px solid ${token.colorPrimaryBorder};
  `,
    userAvatar: css`
    background: ${token.colorFillSecondary};
    color: ${token.colorTextSecondary};
  `,
    bubble: css`
    padding: 12px 16px;
    border-radius: ${token.borderRadiusLG}px;
    font-size: 14px;
    line-height: 1.6;
    max-width: 80%;
  `,
    assistantBubble: css`
    background: ${token.colorBgContainer};
    border: 1px solid ${token.colorBorderSecondary};
  `,
    userBubble: css`
    background: ${token.colorPrimary};
    color: ${token.colorTextLightSolid};
  `,
    footer: css`
    padding: ${token.paddingLG}px;
    background: ${token.colorBgContainer};
    border-top: 1px solid ${token.colorBorderSecondary};
  `,
    inputWrapper: css`
    max-width: 900px;
    margin: 0 auto;
    width: 100%;
  `,
}));

interface Message {
    id: string;
    type: "user" | "assistant";
    content: string;
    timestamp: Date;
}

export const VibeCodeStudioPage = () => {
    const { styles, theme } = useStyles();
    const { jobs } = useJobStore();

    const [messages, setMessages] = useState<Message[]>([
        {
            id: "1",
            type: "assistant",
            content: "Welcome to Agents Forgery! I'll help you create custom AI agents. Describe what kind of agent you'd like to build, including its purpose, capabilities, and any specific tools it should have access to.",
            timestamp: new Date(),
        },
    ]);

    const handleSendMessage = (content: string) => {
        const userMessage: Message = {
            id: Date.now().toString(),
            type: "user",
            content,
            timestamp: new Date(),
        };
        setMessages((prev) => [...prev, userMessage]);

        // In a real scenario, this would trigger an agent-creation goal
        // For now, we simulate the interaction pattern
    };

    // Identify the latest job to drive the blueprint UI
    const lastJobId = useMemo(() => {
        const arr = Object.values(jobs || {});
        if (!arr.length) return "";
        return (arr as any[]).sort((a, b) =>
            new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime()
        ).pop()?.id || "";
    }, [jobs]);

    return (
        <div className={styles.container}>
            <Flexbox className={styles.header} horizontal align="center" justify="space-between">
                <Space size={12}>
                    <Hammer size={24} color={theme.colorPrimary} />
                    <div>
                        <Title level={3} style={{ margin: 0 }}>Agents Forgery</Title>
                        <Text type="secondary" style={{ fontSize: 13 }}>Forge and customize AI agents for your specific needs</Text>
                    </div>
                </Space>
            </Flexbox>

            <div className={styles.scrollArea}>
                <div className={styles.messageList}>
                    {lastJobId && (
                        <div style={{ marginBottom: 32 }}>
                            <AgentBlueprintUI jobId={lastJobId} />
                            <Divider style={{ margin: '32px 0' }} />
                        </div>
                    )}

                    {messages.map((message) => (
                        <Flexbox
                            key={message.id}
                            className={styles.messageItem}
                            horizontal
                            gap={12}
                            align="start"
                            justify={message.type === 'user' ? 'flex-end' : 'flex-start'}
                        >
                            {message.type === 'assistant' && (
                                <div className={`${styles.avatar} ${styles.assistantAvatar}`}>
                                    <Bot size={18} />
                                </div>
                            )}

                            <div className={`${styles.bubble} ${message.type === 'user' ? styles.userBubble : styles.assistantBubble}`}>
                                {message.content}
                            </div>

                            {message.type === 'user' && (
                                <div className={`${styles.avatar} ${styles.userAvatar}`}>
                                    <User size={18} />
                                </div>
                            )}
                        </Flexbox>
                    ))}
                </div>
            </div>

            <div className={styles.footer}>
                <div className={styles.inputWrapper}>
                    <GoalInputBar
                        onSubmit={handleSendMessage}
                        placeholder="Describe the agent you want to create..."
                        autoFocus
                    />
                </div>
            </div>
        </div>
    );
};

export default VibeCodeStudioPage;
