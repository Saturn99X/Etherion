'use client';

import React, { useMemo } from 'react';
import { createStyles } from 'antd-style';
import { Flexbox } from 'react-layout-kit';
import { Card, Table, Typography, Empty } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { Table as TableIcon } from 'lucide-react';

const { Text } = Typography;

const useStyles = createStyles(({ token, css }) => ({
  card: css`
    background: ${token.colorBgContainer};
    border: 1px solid ${token.colorBorder};
    border-radius: ${token.borderRadiusLG}px;
  `,
  header: css`
    padding: ${token.paddingMD}px ${token.paddingLG}px;
    border-bottom: 1px solid ${token.colorBorderSecondary};
  `,
  content: css`
    padding: ${token.paddingLG}px;
  `,
  table: css`
    .ant-table {
      background: transparent;
    }
    
    .ant-table-thead > tr > th {
      background: ${token.colorFillQuaternary};
      color: ${token.colorText};
      font-weight: 600;
      border-bottom: 1px solid ${token.colorBorder};
    }
    
    .ant-table-tbody > tr > td {
      border-bottom: 1px solid ${token.colorBorderSecondary};
    }
    
    .ant-table-tbody > tr:hover > td {
      background: ${token.colorFillTertiary};
    }
  `,
}));

export interface DataTableProps {
  title?: string;
  columns?: string[];
  rows?: Array<Record<string, any>>;
  emptyMessage?: string;
  pagination?: boolean;
  pageSize?: number;
}

export function DataTable({
  title = 'Data Table',
  columns,
  rows = [],
  emptyMessage = 'No data available',
  pagination = true,
  pageSize = 10,
}: DataTableProps) {
  const { styles, theme } = useStyles();

  // Derive columns from data if not explicitly provided
  const derivedColumns = useMemo(() => {
    if (columns && columns.length > 0) return columns;
    if (rows.length === 0) return [];
    return Object.keys(rows[0]);
  }, [columns, rows]);

  // Convert to AntD table columns format
  const tableColumns: ColumnsType<Record<string, any>> = useMemo(() => {
    return derivedColumns.map((col) => ({
      title: col,
      dataIndex: col,
      key: col,
      render: (value: any) => {
        if (value === null || value === undefined) return '-';
        if (typeof value === 'object') return JSON.stringify(value);
        return String(value);
      },
    }));
  }, [derivedColumns]);

  // Add keys to rows for AntD table
  const dataSource = useMemo(() => {
    return rows.map((row, index) => ({ ...row, key: index }));
  }, [rows]);

  return (
    <Card className={styles.card} bordered={false}>
      <Flexbox className={styles.header} horizontal align="center" gap={8}>
        <TableIcon size={20} color={theme.colorPrimary} />
        <Text strong>{title}</Text>
        <Text type="secondary" style={{ marginLeft: 'auto', fontSize: theme.fontSizeSM }}>
          {rows.length} {rows.length === 1 ? 'row' : 'rows'}
        </Text>
      </Flexbox>
      <div className={styles.content}>
        {rows.length === 0 ? (
          <Empty description={emptyMessage} />
        ) : (
          <div className={styles.table}>
            <Table
              columns={tableColumns}
              dataSource={dataSource}
              pagination={
                pagination
                  ? {
                      pageSize,
                      showSizeChanger: true,
                      showTotal: (total) => `Total ${total} items`,
                    }
                  : false
              }
              scroll={{ x: 'max-content' }}
              size="small"
            />
          </div>
        )}
      </div>
    </Card>
  );
}

export default { DataTable };
