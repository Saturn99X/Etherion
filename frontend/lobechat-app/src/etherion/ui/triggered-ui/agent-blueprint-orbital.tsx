'use client';

import React from 'react';
import { createStyles } from 'antd-style';
import { Flexbox } from 'react-layout-kit';
import { Button, Typography } from 'antd';
import { Check, X, Sparkles, Wrench, Zap } from 'lucide-react';

const { Text } = Typography;

const useStyles = createStyles(({ token, css }) => ({
  orbital: css`
    position: relative;
    width: 100%;
    min-height: 400px;
    background: ${token.colorBgContainer};
    border-radius: ${token.borderRadiusLG}px;
    padding: ${token.paddingLG}px;
    overflow: hidden;
  `,
  agentCore: css`
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    text-align: center;
    z-index: 10;
    background: linear-gradient(135deg, ${token.colorPrimary}, ${token.colorPrimaryHover});
    border-radius: 50%;
    width: 120px;
    height: 120px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.15);
    border: 2px solid ${token.colorBorder};
  `,
  coreTitle: css`
    color: white;
    font-size: ${token.fontSizeLG}px;
    font-weight: 600;
    margin: 0;
  `,
  coreSubtitle: css`
    color: rgba(255, 255, 255, 0.85);
    font-size: ${token.fontSizeSM}px;
    margin: 0;
  `,
  orbitalContainer: css`
    position: relative;
    width: 100%;
    height: 400px;
  `,
  orbitPath: css`
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    border: 1px dashed ${token.colorBorder};
    border-radius: 50%;
    animation: rotate 20s linear infinite;
    
    @keyframes rotate {
      from { transform: translate(-50%, -50%) rotate(0deg); }
      to { transform: translate(-50%, -50%) rotate(360deg); }
    }
  `,
  mainOrbit: css`
    width: 280px;
    height: 280px;
  `,
  secondaryOrbit: css`
    width: 340px;
    height: 340px;
    animation-duration: 25s;
  `,
  tertiaryOrbit: css`
    width: 400px;
    height: 400px;
    animation-duration: 30s;
  `,
  sphere: css`
    position: absolute;
    width: 80px;
    height: 80px;
    background: ${token.colorBgElevated};
    border: 1px solid ${token.colorBorder};
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
    cursor: pointer;
    transition: all 0.3s ease;
    
    &:hover {
      transform: scale(1.1);
      box-shadow: 0 6px 16px rgba(0, 0, 0, 0.15);
      border-color: ${token.colorPrimary};
    }
  `,
  systemPromptSphere: css`
    top: 0;
    left: 50%;
    transform: translate(-50%, -50%);
    background: linear-gradient(135deg, ${token.colorSuccessBg}, ${token.colorSuccessBorder});
  `,
  toolsSphere: css`
    top: 50%;
    right: 0;
    transform: translate(50%, -50%);
    background: linear-gradient(135deg, ${token.colorInfoBg}, ${token.colorInfoBorder});
  `,
  capabilitiesSphere: css`
    bottom: 0;
    left: 50%;
    transform: translate(-50%, 50%);
    background: linear-gradient(135deg, ${token.colorWarningBg}, ${token.colorWarningBorder});
  `,
  sphereContent: css`
    text-align: center;
    padding: ${token.paddingSM}px;
  `,
  sphereTitle: css`
    font-size: ${token.fontSizeSM}px;
    font-weight: 600;
    color: ${token.colorText};
    margin-bottom: 4px;
  `,
  previewCard: css`
    display: none; // Hidden in orbital view, shown on hover/click
  `,
  controlButtons: css`
    position: absolute;
    bottom: ${token.paddingLG}px;
    left: 50%;
    transform: translateX(-50%);
    display: flex;
    gap: ${token.marginMD}px;
    z-index: 20;
  `,
}));

interface AgentBlueprintOrbitalProps {
  agentName: string;
  blueprintTitle: string;
  systemPromptPreview: React.ReactNode;
  toolsPreview: React.ReactNode;
  capabilitiesPreview: React.ReactNode;
  onApprove: () => void;
  onReject: () => void;
}

export function AgentBlueprintOrbital({
  agentName,
  blueprintTitle,
  systemPromptPreview,
  toolsPreview,
  capabilitiesPreview,
  onApprove,
  onReject,
}: AgentBlueprintOrbitalProps) {
  const { styles, theme } = useStyles();

  return (
    <div className={styles.orbital}>
      {/* Central Agent Core */}
      <div className={styles.agentCore}>
        <Sparkles size={24} color="white" style={{ marginBottom: 4 }} />
        <h2 className={styles.coreTitle}>{agentName}</h2>
        <p className={styles.coreSubtitle}>{blueprintTitle}</p>
      </div>

      {/* Orbital Spheres */}
      <div className={styles.orbitalContainer}>
        {/* Main Orbit - System Prompt */}
        <div className={`${styles.orbitPath} ${styles.mainOrbit}`}>
          <div className={`${styles.sphere} ${styles.systemPromptSphere}`}>
            <Flexbox align="center" justify="center" style={{ width: '100%', height: '100%' }}>
              <Zap size={20} color={theme.colorSuccess} />
              <Text className={styles.sphereTitle}>Prompt</Text>
            </Flexbox>
          </div>
        </div>

        {/* Secondary Orbit - Tools */}
        <div className={`${styles.orbitPath} ${styles.secondaryOrbit}`}>
          <div className={`${styles.sphere} ${styles.toolsSphere}`}>
            <Flexbox align="center" justify="center" style={{ width: '100%', height: '100%' }}>
              <Wrench size={20} color={theme.colorInfo} />
              <Text className={styles.sphereTitle}>Tools</Text>
            </Flexbox>
          </div>
        </div>

        {/* Tertiary Orbit - Capabilities */}
        <div className={`${styles.orbitPath} ${styles.tertiaryOrbit}`}>
          <div className={`${styles.sphere} ${styles.capabilitiesSphere}`}>
            <Flexbox align="center" justify="center" style={{ width: '100%', height: '100%' }}>
              <Sparkles size={20} color={theme.colorWarning} />
              <Text className={styles.sphereTitle}>Capabilities</Text>
            </Flexbox>
          </div>
        </div>
      </div>

      {/* Control Buttons */}
      <div className={styles.controlButtons}>
        <Button
          size="large"
          icon={<X size={18} />}
          onClick={onReject}
        >
          Reject
        </Button>
        <Button
          type="primary"
          size="large"
          icon={<Check size={18} />}
          onClick={onApprove}
        >
          Approve
        </Button>
      </div>
    </div>
  );
}

export default AgentBlueprintOrbital;
