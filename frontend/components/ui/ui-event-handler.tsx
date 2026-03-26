"use client";

import React, { useState, useEffect } from 'react';
import { useUIEvents } from '@/hooks/use-ui-events';
import { ConfirmationModal } from './confirmation-modal';

export const UIEventHandler: React.FC = () => {
  const { lastEvent } = useUIEvents();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [modalProps, setModalProps] = useState<any>({});

  useEffect(() => {
    if (lastEvent && lastEvent.type === 'show_confirmation_modal') {
      setModalProps(lastEvent.payload);
      setIsModalOpen(true);
    }
  }, [lastEvent]);

  const handleConfirm = () => {
    if (modalProps.onConfirm) {
      // In a real app, you would send a mutation back to the backend
      // to confirm the action.
      console.log('Confirmed!', modalProps.onConfirm);
    }
    setIsModalOpen(false);
  };

  const handleClose = () => {
    setIsModalOpen(false);
  };

  return (
    <ConfirmationModal
      isOpen={isModalOpen}
      onClose={handleClose}
      onConfirm={handleConfirm}
      title={modalProps.title || 'Confirm Action'}
      description={modalProps.description || 'Are you sure you want to proceed?'}
    />
  );
};
