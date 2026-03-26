'use client';

import { useState } from 'react';
import { Button, Card, Input, Typography, Space, Badge, List } from 'antd';
import { createStyles } from 'antd-style';
import { Flexbox } from 'react-layout-kit';
import { useApolloClient } from '@etherion/ui/layout/apollo-provider';
import { EXECUTE_GOAL_MUTATION } from '@etherion/lib/graphql-operations';
import { useJobStore } from '@etherion/stores/job-store';

const { Title, Text } = Typography;
const { TextArea } = Input;

const useStyles = createStyles(({ token, css }) => ({
    container: css`
    display: flex;
    flex-direction: column;
    gap: ${token.marginLG}px;
    padding: ${token.paddingLG}px;
  `,
    card: css`
    background: ${token.colorBgContainer};
    border: 1px solid ${token.colorBorderSecondary};
  `,
    jobCard: css`
    margin-bottom: ${token.marginMD}px;
    background: ${token.colorFillQuaternary};
  `,
}));

interface InteractConsoleProps {
    teamId: string;
}

export const InteractConsole = ({ teamId }: InteractConsoleProps) => {
    const { styles } = useStyles();
    const client = useApolloClient();
    const [goal, setGoal] = useState('');
    const [context, setContext] = useState('');
    const [submitting, setSubmitting] = useState(false);

    const { jobs, addJob, subscribeToJob } = useJobStore();

    const onSubmit = async () => {
        if (!goal.trim()) return;
        try {
            setSubmitting(true);
            const { data } = await client.mutate({
                mutation: EXECUTE_GOAL_MUTATION,
                variables: {
                    goalInput: {
                        goal: goal.trim(),
                        context: context.trim() || null,
                        agentTeamId: teamId,
                    },
                },
            });
            const resp = data?.executeGoal;
            if (resp?.success && resp?.job_id) {
                addJob(resp.job_id);
                subscribeToJob(resp.job_id);
                setGoal('');
                setContext('');
            }
        } catch (e) {
            console.error('Failed to execute goal', e);
        } finally {
            setSubmitting(false);
        }
    };

    return (
        <div className={styles.container}>
            <Card className={styles.card} title="Interact Console (Debug)">
                <Flexbox gap={16}>
                    <div>
                        <Text type="secondary">Team ID: </Text>
                        <Text code>{teamId}</Text>
                    </div>

                    <TextArea
                        placeholder="Describe your goal..."
                        value={goal}
                        onChange={(e) => setGoal(e.target.value)}
                        rows={4}
                    />

                    <Input
                        placeholder="Optional context (links, IDs, hints)"
                        value={context}
                        onChange={(e) => setContext(e.target.value)}
                    />

                    <Flexbox horizontal justify="flex-end">
                        <Button
                            type="primary"
                            onClick={onSubmit}
                            loading={submitting}
                            disabled={!goal.trim()}
                        >
                            Run Execution
                        </Button>
                    </Flexbox>
                </Flexbox>
            </Card>

            <Title level={4}>Active Jobs</Title>

            {Object.values(jobs).length === 0 ? (
                <Text type="secondary">No jobs yet. Submit a goal above.</Text>
            ) : (
                <List
                    dataSource={Object.values(jobs).reverse()}
                    renderItem={(job) => (
                        <Card
                            key={job.id}
                            className={styles.jobCard}
                            size="small"
                            title={
                                <Flexbox horizontal justify="space-between" align="center">
                                    <Text strong>Job {job.id}</Text>
                                    <Badge
                                        status={job.isFailed ? 'error' : job.isCompleted ? 'success' : 'processing'}
                                        text={job.status}
                                    />
                                </Flexbox>
                            }
                        >
                            <Text type="secondary">
                                {job.currentStep || 'Initializing...'}
                            </Text>
                        </Card>
                    )}
                />
            )}
        </div>
    );
};

export default InteractConsole;
