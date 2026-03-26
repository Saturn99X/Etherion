'use client';

import React from 'react';
import { Modal, Button, Typography, Space } from 'antd';
import { createStyles } from 'antd-style';
import { Flexbox } from 'react-layout-kit';
import { AlertCircle, CheckCircle, Info, XCircle } from 'lucide-react';

const { Text, Paragraph } = Typography;

const useStyles = createStyles(({ token, css }) => ({
  modal: css`
    .ant-modal-content {
      background: ${token.colorBgContainer};
      border: 1px solid ${token.colorBorder};
      border-radius: ${token.borderRadiusLG}px;
    }
  `,
  header: css`
    padding: ${token.paddingMD}px ${token.paddingLG}px;
    border-bottom: 1px solid ${token.colorBorderSecondary};
  `,
  body: css`
    padding: ${token.paddingLG}px;
  `,
  footer: css`
    padding: ${token.paddingMD}px ${token.paddingLG}px;
    border-top: 1px solid ${token.colorBorderSecondary};
  `,
  message: css`
    color: ${token.colorText};
    font-size: ${token.fontSize}px;
    line-height: 1.6;
    white-space: pre-wrap;
  `,
}));

interface ConfirmationAction {
  label: string;
  value: string;
  variant?: 'primary' | 'default' | 'danger';
}

interface ConfirmationModalProps {
  open: boolean;
  title?: string;
  message?: string;
  actions?: ConfirmationAction[];
  type?: 'info' | 'success' | 'warning' | 'error';
  onClose: () => void;
  onAction: (value: string) => void;
}

const ICON_MAP = {
  info: <Info size={20} />,
  success: <CheckCircle size={20} />,
  warning: <AlertCircle size={20} />,
  error: <XCircle size={20} />,
};

export function ConfirmationModal({
  open,
  title = 'Confirm action',
  message = 'Are you sure?',
  actions,
  type = 'info',
  onClose,
  onAction,
}: ConfirmationModalProps) {
  const { styles, theme } = useStyles();

  // Default actions if none provided
  const safeActions: ConfirmationAction[] =
    actions && actions.length > 0
      ? actions
      : [
          { label: 'Cancel', value: 'cancel', variant: 'default' },
          { label: 'Confirm', value: 'confirm', variant: 'primary' },
        ];

  const icon = ICON_MAP[type];
  const iconColor =
    type === 'error'
      ? theme.colorError
      : type === 'warning'
        ? theme.colorWarning
        : type === 'success'
          ? theme.colorSuccess
          : theme.colorInfo;

  return (
    <Modal
      open={open}
      onCancel={onClose}
      footer={null}
      closable={false}
      centered
      width={480}
      className={styles.modal}
    >
      <Flexbox gap={20}>
        {/* Header */}
        <Flexbox horizontal align="center" gap={12} className={styles.header}>
          <div style={{ color: iconColor }}>{icon}</div>
          <Text strong style={{ fontSize: theme.fontSizeLG }}>
            {title}
          </Text>
        </Flexbox>

        {/* Body */}
        <div className={styles.body}>
          <Paragraph className={styles.message}>{message}</Paragraph>
        </div>

        {/* Footer */}
        <Flexbox horizontal justify="flex-end" gap={12} className={styles.footer}>
          {safeActions.map((action) => (
            <Button
              key={action.value}
              type={action.variant === 'primary' ? 'primary' : 'default'}
              danger={action.variant === 'danger'}
              onClick={() => onAction(action.value)}
            >
              {action.label}
            </Button>
          ))}
        </Flexbox>
      </Flexbox>
    </Modal>
  );
}

export default ConfirmationModal;
