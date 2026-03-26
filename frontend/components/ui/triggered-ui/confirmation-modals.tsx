"use client";

import React from "react";

interface ConfirmationAction {
  label: string;
  value: string;
  variant?: "primary" | "secondary" | "danger";
}

interface ConfirmationModalProps {
  open: boolean;
  title?: string;
  message?: string;
  actions?: ConfirmationAction[];
  onClose: () => void;
  onAction: (value: string) => void;
}

const backdropStyle: React.CSSProperties = {
  position: "fixed",
  inset: 0,
  background: "rgba(0,0,0,0.5)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  zIndex: 1000,
};

const modalStyle: React.CSSProperties = {
  width: "min(520px, 92vw)",
  background: "#0b0f17",
  border: "1px solid rgba(255,255,255,0.12)",
  borderRadius: 12,
  color: "white",
  boxShadow: "0 10px 40px rgba(0,0,0,0.5)",
};

const headerStyle: React.CSSProperties = {
  padding: "16px 20px",
  borderBottom: "1px solid rgba(255,255,255,0.08)",
  fontWeight: 600,
};

const bodyStyle: React.CSSProperties = {
  padding: 20,
  fontSize: 14,
  lineHeight: 1.5,
  color: "rgba(255,255,255,0.9)",
  whiteSpace: "pre-wrap",
};

const footerStyle: React.CSSProperties = {
  padding: 16,
  display: "flex",
  gap: 10,
  justifyContent: "flex-end",
  borderTop: "1px solid rgba(255,255,255,0.08)",
};

function buttonStyle(variant: ConfirmationAction["variant"]) : React.CSSProperties {
  const base: React.CSSProperties = {
    padding: "8px 14px",
    borderRadius: 8,
    border: "1px solid transparent",
    cursor: "pointer",
    fontSize: 13,
  };
  if (variant === "danger") {
    return { ...base, background: "#a4161a", color: "white", borderColor: "#a4161a" };
  }
  if (variant === "secondary") {
    return { ...base, background: "transparent", color: "white", borderColor: "rgba(255,255,255,0.2)" };
  }
  return { ...base, background: "#2563eb", color: "white", borderColor: "#2563eb" };
}

export default function ConfirmationModal({ open, title, message, actions, onClose, onAction }: ConfirmationModalProps) {
  if (!open) return null;
  const safeActions: ConfirmationAction[] = actions && actions.length ? actions : [
    { label: "Cancel", value: "cancel", variant: "secondary" as const },
    { label: "Confirm", value: "confirm", variant: "primary" as const },
  ];

  return (
    <div style={backdropStyle} onClick={onClose}>
      <div style={modalStyle} onClick={(e) => e.stopPropagation()}>
        <div style={headerStyle}>{title || "Confirm action"}</div>
        <div style={bodyStyle}>{message || "Are you sure?"}</div>
        <div style={footerStyle}>
          {safeActions.map((a) => (
            <button key={a.value} style={buttonStyle(a.variant)} onClick={() => onAction(a.value)}>
              {a.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}