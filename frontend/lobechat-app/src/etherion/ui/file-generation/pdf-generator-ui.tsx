"use client";

import { createStyles } from 'antd-style';
import { FileText, Download, Eye, CheckCircle } from 'lucide-react';
import React, { useState } from 'react';
import { Flexbox } from 'react-layout-kit';
import { Button, message, Tabs, Tag } from 'antd';

const useStyles = createStyles(({ token, css }) => ({
  container: css`
    background: ${token.colorBgContainer};
    border-radius: ${token.borderRadiusLG}px;
    padding: ${token.paddingLG}px;
    border: 1px solid ${token.colorBorder};
    max-width: 900px;
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
    min-height: 400px;
    max-height: 600px;
    overflow-y: auto;
    color: ${token.colorText};
    white-space: pre-wrap;
    font-family: ${token.fontFamily};
    line-height: 1.6;
  `,
  pdfEmbed: css`
    width: 100%;
    height: 600px;
    border: 1px solid ${token.colorBorder};
    border-radius: ${token.borderRadius}px;
  `,
  metadata: css`
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-top: ${token.marginMD}px;
    padding-top: ${token.marginMD}px;
    border-top: 1px solid ${token.colorBorder};
  `,
  fileInfo: css`
    color: ${token.colorTextSecondary};
    font-size: ${token.fontSizeSM}px;
  `,
  placeholder: css`
    text-align: center;
    padding: ${token.paddingXL}px;
    color: ${token.colorTextTertiary};
  `,
}));

interface PDFGeneratorProps {
  filename?: string;
  content?: string;
  downloadUrl?: string;
  fileSize?: number;
  generatedAt?: string;
  pageSize?: string;
  orientation?: string;
  jobId?: string;
}

/**
 * PDFGeneratorUI - Display-only component for AI-generated PDF files
 * 
 * This component is triggered automatically by the backend when generate_pdf_file
 * tool completes. It displays a preview of the generated PDF with download capability.
 * 
 * Triggered by: UI Event Dispatcher when backend publishes "open_component" event
 * Component ID: "file-generation/pdf-generator-ui"
 */
export default function PDFGeneratorUI({
  filename = "document.pdf",
  content = "",
  downloadUrl,
  fileSize,
  generatedAt,
  pageSize = "A4",
  orientation = "portrait",
  jobId,
}: PDFGeneratorProps) {
  const { styles, theme } = useStyles();
  const [activeTab, setActiveTab] = useState<string>('preview');

  const handleDownload = () => {
    if (downloadUrl) {
      // Use backend-provided signed URL
      window.open(downloadUrl, '_blank');
      message.success('PDF download started');
    } else {
      message.error('Download URL not available');
    }
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

  const tabItems = [
    {
      key: 'preview',
      label: (
        <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Eye size={16} />
          Preview
        </span>
      ),
      children: downloadUrl ? (
        <iframe
          src={`${downloadUrl}#view=FitH`}
          className={styles.pdfEmbed}
          title="PDF Preview"
        />
      ) : (
        <div className={styles.preview}>
          {content || (
            <div className={styles.placeholder}>
              <FileText size={48} style={{ opacity: 0.3, marginBottom: theme.marginMD }} />
              <p>PDF preview not available. Use the download button to view the file.</p>
            </div>
          )}
        </div>
      ),
    },
    {
      key: 'content',
      label: (
        <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <FileText size={16} />
          Content
        </span>
      ),
      children: (
        <div className={styles.preview}>
          {content || (
            <div className={styles.placeholder}>
              <FileText size={48} style={{ opacity: 0.3, marginBottom: theme.marginMD }} />
              <p>No text content available for this PDF.</p>
            </div>
          )}
        </div>
      ),
    },
  ];

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

      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={tabItems}
      />

      <div className={styles.metadata}>
        <div className={styles.fileInfo}>
          {formatFileSize(fileSize)} • {pageSize} {orientation} • Generated {formatTimestamp(generatedAt)}
        </div>
        <Button
          type="primary"
          icon={<Download size={16} />}
          onClick={handleDownload}
          disabled={!downloadUrl}
        >
          Download PDF
        </Button>
      </div>
    </Flexbox>
  );
}
