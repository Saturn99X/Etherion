'use client';

import { useEffect, useState } from 'react';
import { createStyles } from 'antd-style';
import { Flexbox } from 'react-layout-kit';
import { Card, Input, List, Typography, Empty, Button, Tag, App } from 'antd';
import { Search, FileText, Calendar, ExternalLink, RefreshCw } from 'lucide-react';
import { listKnowledgeItems, type KnowledgeItem } from '@etherion/bridge/knowledge';

const { Text, Title } = Typography;
const { Search: SearchInput } = Input;

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
  searchBox: css`
    margin-bottom: ${token.marginLG}px;
  `,
  resultItem: css`
    padding: ${token.paddingMD}px;
    background: ${token.colorFillQuaternary};
    border-radius: ${token.borderRadius}px;
    border: 1px solid ${token.colorBorder};
    transition: all 0.3s ease;
    cursor: pointer;
    
    &:hover {
      border-color: ${token.colorPrimary};
      box-shadow: ${token.boxShadowTertiary};
    }
  `,
  snippet: css`
    color: ${token.colorTextSecondary};
    font-size: ${token.fontSizeSM}px;
    line-height: 1.6;
    margin-top: ${token.marginXS}px;
  `,
}));

export interface KnowledgeBrowserProps {
  onSelectDocument?: (assetId: string) => void;
  limit?: number;
}

export function KnowledgeBrowser({ onSelectDocument, limit = 50 }: KnowledgeBrowserProps) {
  const { styles, theme } = useStyles();
  const { message } = App.useApp();
  const [query, setQuery] = useState('');
  const [items, setItems] = useState<KnowledgeItem[]>([]);
  const [loading, setLoading] = useState(false);

  const loadItems = async () => {
    setLoading(true);
    try {
      const data = await listKnowledgeItems({ limit, includeDownload: true });
      setItems(data);
    } catch (err: any) {
      console.error('Knowledge items load error:', err);
      message.error(err.message || 'Failed to load knowledge items');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadItems();
  }, [limit]);

  // Client-side filtering by filename
  const filtered = items.filter((item) =>
    item.filename.toLowerCase().includes(query.toLowerCase())
  );

  const handleItemClick = (item: KnowledgeItem) => {
    if (onSelectDocument) {
      onSelectDocument(item.assetId);
    } else if (item.downloadUrl) {
      window.open(item.downloadUrl, '_blank');
    }
  };

  return (
    <Card className={styles.card}>
      <Flexbox className={styles.header} horizontal align="center" justify="space-between">
        <Flexbox horizontal align="center" gap={8}>
          <Search size={20} color={theme.colorPrimary} />
          <Title level={5} style={{ margin: 0 }}>
            Knowledge Base
          </Title>
        </Flexbox>
        <Button
          icon={<RefreshCw size={16} />}
          onClick={loadItems}
          loading={loading}
          size="small"
        >
          Refresh
        </Button>
      </Flexbox>

      <div className={styles.content}>
        <Flexbox gap={16}>
          {/* Search Input */}
          <div className={styles.searchBox}>
            <Input
              prefix={<Search size={14} />}
              placeholder="Filter by filename..."
              size="large"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              allowClear
            />
          </div>

          {/* Results */}
          {loading ? (
            <Empty description="Loading..." />
          ) : filtered.length === 0 && query ? (
            <Empty description="No items match your filter" />
          ) : filtered.length === 0 ? (
            <Empty description="No knowledge items found" />
          ) : (
            <List
              dataSource={filtered}
              renderItem={(item) => (
                <List.Item style={{ border: 'none', padding: 0, marginBottom: theme.marginMD }}>
                  <div
                    className={styles.resultItem}
                    onClick={() => handleItemClick(item)}
                  >
                    <Flexbox gap={8}>
                      {/* Title and Download */}
                      <Flexbox horizontal align="center" justify="space-between">
                        <Flexbox horizontal align="center" gap={8}>
                          <FileText size={16} color={theme.colorPrimary} />
                          <Text strong ellipsis title={item.filename}>
                            {item.filename}
                          </Text>
                        </Flexbox>
                        {item.downloadUrl && (
                          <Button
                            type="text"
                            size="small"
                            icon={<ExternalLink size={14} />}
                            onClick={(e) => {
                              e.stopPropagation();
                              window.open(item.downloadUrl, '_blank');
                            }}
                          />
                        )}
                      </Flexbox>

                      {/* MIME type */}
                      <Text type="secondary" style={{ fontSize: theme.fontSizeSM }}>
                        {item.mimeType}
                      </Text>

                      {/* Metadata */}
                      <Flexbox horizontal align="center" gap={8} style={{ marginTop: theme.marginXS }}>
                        <Tag color="default" style={{ fontSize: theme.fontSizeSM }}>
                          {Math.round(item.sizeBytes / 1024)} KB
                        </Tag>
                        <Flexbox horizontal align="center" gap={4}>
                          <Calendar size={12} color={theme.colorTextSecondary} />
                          <Text type="secondary" style={{ fontSize: theme.fontSizeSM }}>
                            {new Date(item.createdAt).toLocaleDateString()}
                          </Text>
                        </Flexbox>
                        {item.jobId && (
                          <Tag style={{ fontSize: 10 }}>
                            Job: {item.jobId.slice(0, 8)}
                          </Tag>
                        )}
                      </Flexbox>
                    </Flexbox>
                  </div>
                </List.Item>
              )}
            />
          )}
        </Flexbox>
      </div>
    </Card>
  );
}

export default KnowledgeBrowser;
