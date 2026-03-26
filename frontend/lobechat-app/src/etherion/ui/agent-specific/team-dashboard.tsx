'use client';

import { createStyles } from 'antd-style';
import { Empty } from 'antd';
import { Flexbox } from 'react-layout-kit';
import { useTeamStore } from '@etherion/stores/team-store';
import { AnalyticsTeamUI } from './analytics-team-ui';
import { ContentTeamUI } from './content-team-ui';
import { DevelopmentTeamUI } from './development-team-ui';
import { FinancialTeamUI } from './financial-team-ui';
import { MarketingTeamUI } from './marketing-team-ui';
import { SalesTeamUI } from './sales-team-ui';

const useStyles = createStyles(({ token, css }) => ({
  container: css`
    height: 100%;
    background: ${token.colorBgLayout};
  `,
  empty: css`
    padding: ${token.paddingXL}px;
    color: ${token.colorTextSecondary};
  `,
}));

/** Maps a team name (lowercased) to its specialised dashboard. */
function resolveTeamType(name: string): string {
  if (name.includes('sales') || name.includes('revenue')) return 'sales';
  if (name.includes('analytic') || name.includes('data') || name.includes('insight')) return 'analytics';
  if (name.includes('content') || name.includes('copywrite') || name.includes('writing')) return 'content';
  if (name.includes('dev') || name.includes('engineer') || name.includes('code')) return 'development';
  if (name.includes('financ') || name.includes('account') || name.includes('budget')) return 'financial';
  if (name.includes('market') || name.includes('campaign') || name.includes('growth')) return 'marketing';
  return 'generic';
}

interface TeamDashboardProps {
  teamId?: string;
  teamName?: string;
  teamData?: unknown;
  loading?: boolean;
}

export const TeamDashboard = ({ teamId, teamName, teamData, loading }: TeamDashboardProps) => {
  const { styles } = useStyles();
  const activeTeamId = useTeamStore((s) => s.activeTeamId);
  const resolvedId = teamId ?? activeTeamId;
  const resolvedName = teamName ?? '';
  const teamType = resolveTeamType(resolvedName.toLowerCase());

  if (!resolvedId && !teamName) {
    return (
      <Flexbox className={styles.empty} align="center" justify="center">
        <Empty description="Select a team to view its dashboard" />
      </Flexbox>
    );
  }

  const commonProps = { data: (teamData as any) ?? null, loading };

  return (
    <Flexbox className={styles.container}>
      {teamType === 'sales' && <SalesTeamUI {...commonProps} />}
      {teamType === 'analytics' && <AnalyticsTeamUI {...commonProps} />}
      {teamType === 'content' && <ContentTeamUI {...commonProps} />}
      {teamType === 'development' && <DevelopmentTeamUI {...commonProps} />}
      {teamType === 'financial' && <FinancialTeamUI {...commonProps} />}
      {teamType === 'marketing' && <MarketingTeamUI {...commonProps} />}
      {teamType === 'generic' && (
        <Flexbox className={styles.empty} align="center" justify="center">
          <Empty description={`No specialised dashboard for "${resolvedName}"`} />
        </Flexbox>
      )}
    </Flexbox>
  );
};

export default TeamDashboard;
