'use client';

import React from 'react';
import DOMPurify from 'isomorphic-dompurify';
import { Card, Typography, Space, Divider } from 'antd';
import { createStyles } from 'antd-style';
import { Flexbox } from 'react-layout-kit';
import { Highlighter } from '@lobehub/ui';
import { FileText, Code, Layout, Image as ImageIcon } from 'lucide-react';

const { Text, Title, Paragraph } = Typography;

const useStyles = createStyles(({ token, css }) => ({
    container: css`
    width: 100%;
    margin-top: ${token.marginMD}px;
  `,
    artifactCard: css`
    background: ${token.colorBgContainer};
    border: 1px solid ${token.colorBorderSecondary};
    border-radius: ${token.borderRadiusLG}px;
    margin-bottom: ${token.marginMD}px;
    overflow: hidden;
  `,
    artifactHeader: css`
    padding: ${token.paddingSM}px ${token.paddingMD}px;
    background: ${token.colorFillQuaternary};
    border-bottom: 1px solid ${token.colorBorderSecondary};
  `,
    artifactContent: css`
    padding: ${token.paddingMD}px;
  `,
    renderArea: css`
    background: white;
    color: black;
    padding: ${token.paddingMD}px;
    border-radius: ${token.borderRadiusSM}px;
    min-height: 100px;
    overflow: auto;
    
    &.doc-mode {
      background: transparent;
      color: ${token.colorText};
      padding: 0;
    }
  `,
}));

export type ArtifactKind = 'html' | 'svg' | 'doc' | 'code';
export type Artifact = {
    kind: ArtifactKind;
    content: string;
    title?: string;
    language?: string;
};

interface ArtifactPanelProps {
    artifacts: Artifact[];
}

const getArtifactIcon = (kind: ArtifactKind) => {
    switch (kind) {
        case 'html': return <Layout size={14} />;
        case 'svg': return <ImageIcon size={14} />;
        case 'code': return <Code size={14} />;
        case 'doc': return <FileText size={14} />;
    }
};

export const ArtifactPanel = ({ artifacts }: ArtifactPanelProps) => {
    const { styles, theme } = useStyles();

    return (
        <div className={styles.container}>
            {artifacts.map((artifact, index) => (
                <div key={index} className={styles.artifactCard}>
                    <Flexbox className={styles.artifactHeader} horizontal align="center" justify="space-between">
                        <Space size={8}>
                            {getArtifactIcon(artifact.kind)}
                            <Text strong style={{ fontSize: 13 }}>{artifact.title || `Artifact ${index + 1}`}</Text>
                        </Space>
                        <Text type="secondary" style={{ fontSize: 11, textTransform: 'uppercase' }}>
                            {artifact.kind}
                        </Text>
                    </Flexbox>

                    <div className={styles.artifactContent}>
                        {artifact.kind === 'html' && (
                            <div
                                className={styles.renderArea}
                                dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(artifact.content) }}
                            />
                        )}

                        {artifact.kind === 'svg' && (
                            <div
                                className={styles.renderArea}
                                dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(artifact.content) }}
                            />
                        )}

                        {artifact.kind === 'code' && (
                            <Highlighter
                                language={artifact.language || 'typescript'}
                                fullFeatured
                            >
                                {artifact.content}
                            </Highlighter>
                        )}

                        {artifact.kind === 'doc' && (
                            <div className={`${styles.renderArea} doc-mode`}>
                                <Paragraph style={{ margin: 0, whiteSpace: 'pre-wrap' }}>
                                    {artifact.content}
                                </Paragraph>
                            </div>
                        )}
                    </div>
                </div>
            ))}
        </div>
    );
};

export default ArtifactPanel;
