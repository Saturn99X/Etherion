'use client';

import { useState, useEffect } from 'react';
import {
    Button, Card, List, Badge, Typography,
    Tag, Empty, Skeleton, App, Space,
    Tooltip, Popconfirm
} from 'antd';
import { createStyles } from 'antd-style';
import { Flexbox } from 'react-layout-kit';
import {
    Plus, Edit, Trash2, TrendingUp,
    Calendar, Target, Mic2, Sparkles
} from 'lucide-react';

import { useApolloClient } from '@etherion/ui/layout/apollo-provider';
import {
    GET_TONE_PROFILES_QUERY,
    CREATE_TONE_PROFILE_MUTATION,
    APPLY_TONE_PROFILE_MUTATION
} from '@etherion/lib/graphql-operations';

const { Title, Text, Paragraph } = Typography;

const useStyles = createStyles(({ token, css }) => ({
    container: css`
    padding: ${token.paddingLG}px;
  `,
    header: css`
    margin-bottom: ${token.marginLG}px;
  `,
    profileCard: css`
    height: 100%;
    transition: all 0.3s;
    &:hover {
      box-shadow: ${token.boxShadowTertiary};
      transform: translateY(-2px);
    }
  `,
    effectiveness: css`
    display: flex;
    align-items: center;
    gap: 8px;
    margin-top: ${token.marginSM}px;
    font-size: 13px;
    font-weight: 500;
  `,
}));

interface ToneProfile {
    id: string;
    name: string;
    type: string;
    description: string;
    usageCount: number;
    lastUsed?: string;
    effectiveness?: number;
}

export const ToneOfVoiceLibrary = () => {
    const { styles, theme } = useStyles();
    const { message } = App.useApp();
    const client = useApolloClient();

    const [profiles, setProfiles] = useState<ToneProfile[]>([]);
    const [loading, setLoading] = useState(true);
    const [applyingProfile, setApplyingProfile] = useState<string | null>(null);

    const fetchToneProfiles = async () => {
        try {
            setLoading(true);
            const { data } = await client.query({
                query: GET_TONE_PROFILES_QUERY,
                variables: { user_id: 1 } // Placeholder as per original
            });
            setProfiles(data.getToneProfiles);
        } catch (err) {
            console.error('Failed to fetch tone profiles:', err);
            message.error('Failed to load tone profiles');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchToneProfiles();
    }, []);

    const handleApply = async (profile: ToneProfile) => {
        try {
            setApplyingProfile(profile.id);
            await client.mutate({
                mutation: APPLY_TONE_PROFILE_MUTATION,
                variables: {
                    profile_id: profile.id,
                    goal_id: 'current-goal'
                }
            });
            message.success(`Applied tone: ${profile.name}`);
        } catch {
            message.error('Failed to apply tone');
        } finally {
            setApplyingProfile(null);
        }
    };

    const getEffectivenessInfo = (val?: number) => {
        if (val === undefined) return null;
        if (val >= 0.8) return { color: theme.colorSuccess, icon: <TrendingUp size={14} />, label: 'High' };
        if (val >= 0.6) return { color: theme.colorWarning, icon: <Target size={14} />, label: 'Moderate' };
        return { color: theme.colorError, icon: <Target size={14} />, label: 'Low' };
    };

    return (
        <div className={styles.container}>
            <Flexbox className={styles.header} horizontal align="center" justify="space-between">
                <div>
                    <Title level={2} style={{ margin: 0 }}>Tone of Voice Library</Title>
                    <Text type="secondary">Define the stylistic and emotional core of AI responses</Text>
                </div>
                <Button
                    type="primary"
                    icon={<Plus size={16} />}
                    onClick={() => message.info('Create Profile modal coming soon')}
                >
                    Create Profile
                </Button>
            </Flexbox>

            {loading ? (
                <List
                    grid={{ gutter: 24, xs: 1, sm: 2, lg: 3 }}
                    dataSource={[1, 2, 3]}
                    renderItem={() => <List.Item><Card loading /></List.Item>}
                />
            ) : profiles.length === 0 ? (
                <Empty description="No tone profiles yet" />
            ) : (
                <List
                    grid={{ gutter: 24, xs: 1, sm: 2, lg: 3 }}
                    dataSource={profiles}
                    renderItem={(p) => {
                        const eff = getEffectivenessInfo(p.effectiveness);
                        return (
                            <List.Item>
                                <Card
                                    className={styles.profileCard}
                                    title={
                                        <Flexbox horizontal align="center" justify="space-between">
                                            <Space>
                                                <Mic2 size={16} color={theme.colorPrimary} />
                                                <span>{p.name}</span>
                                            </Space>
                                            <Tag color={p.type === 'system_default' ? 'blue' : 'default'}>
                                                {p.type === 'system_default' ? 'System' : 'Custom'}
                                            </Tag>
                                        </Flexbox>
                                    }
                                    actions={[
                                        <Button key="edit" type="text" icon={<Edit size={14} />} onClick={() => message.info('Edit mode')}>Edit</Button>,
                                        <Popconfirm key="del" title="Delete Profile?" okText="Yes" cancelText="No">
                                            <Button type="text" danger icon={<Trash2 size={14} />}>Delete</Button>
                                        </Popconfirm>,
                                        <Button
                                            key="apply"
                                            type="link"
                                            onClick={() => handleApply(p)}
                                            loading={applyingProfile === p.id}
                                            icon={<Sparkles size={14} />}
                                        >
                                            Apply
                                        </Button>
                                    ]}
                                >
                                    <Flexbox direction="vertical" gap={12}>
                                        <Paragraph type="secondary" style={{ fontSize: 13, height: 40, overflow: 'hidden' }}>
                                            {p.description}
                                        </Paragraph>

                                        <Flexbox horizontal justify="space-between" align="center" style={{ fontSize: 12 }}>
                                            <Space size={4}>
                                                <Calendar size={12} />
                                                <Text type="secondary">Used {p.usageCount}x</Text>
                                            </Space>
                                            {p.lastUsed && (
                                                <Text type="secondary">Last: {new Date(p.lastUsed).toLocaleDateString()}</Text>
                                            )}
                                        </Flexbox>

                                        {eff && (
                                            <div className={styles.effectiveness} style={{ color: eff.color }}>
                                                {eff.icon}
                                                <span>Effectiveness: {(p.effectiveness! * 100).toFixed(1)}% ({eff.label})</span>
                                            </div>
                                        )}
                                    </Flexbox>
                                </Card>
                            </List.Item>
                        );
                    }}
                />
            )}
        </div>
    );
};

export default ToneOfVoiceLibrary;
