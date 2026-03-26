"use client";

import { createStyles } from 'antd-style';
import { FileText, Download, Copy, CheckCircle } from 'lucide-react';
import React from 'react';
import { Flexbox } from 'react-layout-kit';
import { Button, message, Tag } from 'antd';

const useStyles = createStyles(({ token, css }) => ({
  container: css`
    background: ${token.colorBgContainer};
    border-radius: ${token.borderRadiusLG}px;
    padding: ${token.paddingLG}px;
    border: 1px solid ${token.colorBorder};
    max-width: 800px;
  `,
  header: css`
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: ${token.marginMD}px;
  `,
  titleSection: css`
    display: flex;
    align-items: center;
    gap: ${token.marginSM}px;
  `,
  title: css`
    color: ${token.colorText};
    font-size: ${token.fontSizeLG}px;
    font-weight: 600;
    margin: 0;
  `,
  icon: css`
    color: ${token.colorPrimary};
  `,
  preview: css`
    background: ${token.colorBgLayout};
    border: 1px solid ${token.colorBorder};
    border-radius: ${token.borderRadius}px;
    padding: ${token.paddingLG}px;
    min-height: 300px;
    max-height: 500px;
    overflow-y: auto;
    color: ${token.colorText};
    white-space: pre-wrap;
    font-family: ${token.fontFamily};
    line-height: 1.6;
  `,
  metadata: css`
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-top: ${token.marginMD}px;
    padding-top: ${token.marginMD}px;
    border-top: 1px solid ${token.colorBorder};
  `,
  stats: css`
    color: ${token.colorTextSecondary};
    font-size: ${token.fontSizeSM}px;
  `,
  actions: css`
    display: flex;
    gap: ${token.marginSM}px;
  `,
}));

interface DocumentGeneratorProps {
  content?: string;
  filename?: string;
  downloadUrl?: string;
  fileSize?: number;
  generatedAt?: string;
  jobId?: string;
}

/**
 * DocumentGeneratorUI - Display-only component for AI-generated documents
 * 
 * This component is triggered automatically by the backend when generate_document_file
 * tool completes. It displays the generated content in read-only format with download capability.
 * 
 * Triggered by: UI Event Dispatcher when backend publishes "open_component" event
 * Component ID: "file-generation/document-generator-ui"
 */
export default function DocumentGeneratorUI({
  content = "",
  filename = "document.txt",
  downloadUrl,
  fileSize,
  generatedAt,
  jobId,
}: DocumentGeneratorProps) {
  const { styles } = useStyles();

  const handleCopy = () => {
    navigator.clipboard.writeText(content);
    message.success('Content copied to clipboard');
  };

  const handleDownload = () => {
    if (downloadUrl) {
      // Use backend-provided signed URL
      window.open(downloadUrl, '_blank');
    } else {
      // Fallback: create blob from content
      const blob = new Blob([content], { type: 'text/plain' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    }
    message.success('Document downloaded');
  };

  const formatFileSize = (bytes?: number) => {
    if (!bytes) return 'Unknown size';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const formatTimestamp = (timestamp?: string) => {
    if (!timestamp) return 'Just now';
    try {
      return new Date(timestamp).toLocaleString();
    } catch {
      return timestamp;
    }
  };

  return (
    <Flexbox className={styles.container}>
      <div className={styles.header}>
        <div className={styles.titleSection}>
          <FileText className={styles.icon} size={20} />
          <h3 className={styles.title}>{filename}</h3>
        </div>
        <Tag icon={<CheckCircle size={14} />} color="success">
          Generated
        </Tag>
      </div>

      <div className={styles.preview}>
        {content || <span style={{ opacity: 0.5 }}>No content available</span>}
      </div>

      <div className={styles.metadata}>
        <div className={styles.stats}>
          {formatFileSize(fileSize || content.length)} • {content.split(/\s+/).filter(Boolean).length} words • Generated {formatTimestamp(generatedAt)}
        </div>
        <div className={styles.actions}>
          <Button
            icon={<Copy size={16} />}
            onClick={handleCopy}
            disabled={!content}
          >
            Copy
          </Button>
          <Button
            type="primary"
            icon={<Download size={16} />}
            onClick={handleDownload}
            disabled={!content}
          >
            Download
          </Button>
        </div>
      </div>
    </Flexbox>
  );
}
