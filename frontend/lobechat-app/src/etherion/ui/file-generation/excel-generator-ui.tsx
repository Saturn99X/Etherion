"use client";

import { createStyles } from 'antd-style';
import { FileSpreadsheet, Download, CheckCircle } from 'lucide-react';
import React from 'react';
import { Flexbox } from 'react-layout-kit';
import { Button, Table, message, Tag } from 'antd';

const useStyles = createStyles(({ token, css }) => ({
  container: css`
    background: ${token.colorBgContainer};
    border-radius: ${token.borderRadiusLG}px;
    padding: ${token.paddingLG}px;
    border: 1px solid ${token.colorBorder};
    max-width: 1000px;
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
  sheetInfo: css`
    color: ${token.colorTextSecondary};
    font-size: ${token.fontSizeSM}px;
    margin-bottom: ${token.marginMD}px;
  `,
  tableWrapper: css`
    background: ${token.colorBgLayout};
    border: 1px solid ${token.colorBorder};
    border-radius: ${token.borderRadius}px;
    overflow: auto;
    max-height: 500px;
    
    .ant-table {
      background: transparent;
    }
    
    .ant-table-thead > tr > th {
      background: ${token.colorBgElevated};
      color: ${token.colorText};
      font-weight: 600;
    }
    
    .ant-table-tbody > tr > td {
      color: ${token.colorText};
    }
    
    .ant-table-tbody > tr:hover > td {
      background: ${token.colorBgTextHover};
    }
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
  emptyState: css`
    text-align: center;
    padding: ${token.paddingXL}px;
    color: ${token.colorTextSecondary};
  `,
}));

interface ExcelGeneratorProps {
  sheetName?: string;
  rows?: Array<Record<string, any>>;
  filename?: string;
  downloadUrl?: string;
  fileSize?: number;
  generatedAt?: string;
  jobId?: string;
}

/**
 * ExcelGeneratorUI - Display-only component for AI-generated Excel files
 * 
 * This component is triggered automatically by the backend when generate_excel_file
 * tool completes. It displays a preview of the generated spreadsheet data in read-only
 * table format with download capability.
 * 
 * Triggered by: UI Event Dispatcher when backend publishes "open_component" event
 * Component ID: "file-generation/excel-generator-ui"
 */
export default function ExcelGeneratorUI({
  sheetName = "Sheet1",
  rows = [],
  filename = "spreadsheet.xlsx",
  downloadUrl,
  fileSize,
  generatedAt,
  jobId,
}: ExcelGeneratorProps) {
  const { styles, theme } = useStyles();

  const columns = rows.length > 0 ? Object.keys(rows[0]) : [];

  const tableColumns = columns.map((col) => ({
    title: col,
    dataIndex: col,
    key: col,
    ellipsis: true,
    render: (text: any) => String(text ?? ''),
  }));

  const handleDownload = () => {
    if (downloadUrl) {
      // Use backend-provided signed URL
      window.open(downloadUrl, '_blank');
      message.success('Excel file download started');
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

  return (
    <Flexbox className={styles.container}>
      <div className={styles.header}>
        <div className={styles.titleSection}>
          <FileSpreadsheet className={styles.icon} size={20} />
          <h3 className={styles.title}>{filename}</h3>
        </div>
        <Tag icon={<CheckCircle size={14} />} color="success">
          Generated
        </Tag>
      </div>

      <div className={styles.sheetInfo}>
        Worksheet: {sheetName} • Rows: {rows.length} • Columns: {columns.length}
      </div>

      <div className={styles.tableWrapper}>
        {rows.length > 0 ? (
          <Table
            dataSource={rows.map((row, index) => ({ ...row, key: index }))}
            columns={tableColumns}
            pagination={{ pageSize: 20, showSizeChanger: true }}
            size="small"
            scroll={{ x: 'max-content' }}
          />
        ) : (
          <div className={styles.emptyState}>
            <FileSpreadsheet size={48} style={{ opacity: 0.3, marginBottom: theme.marginMD }} />
            <p>No data available in this spreadsheet</p>
          </div>
        )}
      </div>

      <div className={styles.metadata}>
        <div className={styles.stats}>
          {formatFileSize(fileSize)} • Generated {formatTimestamp(generatedAt)}
        </div>
        <Button
          type="primary"
          icon={<Download size={16} />}
          onClick={handleDownload}
          disabled={!downloadUrl}
        >
          Download Excel
        </Button>
      </div>
    </Flexbox>
  );
}
