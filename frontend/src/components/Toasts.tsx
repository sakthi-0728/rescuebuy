import { useEffect } from "react";

export type ToastItem = {
  id: number;
  kind: "success" | "error" | "info";
  text: string;
  action?: { label: string; onClick: () => void };
};

type ToastProps = {
  toast: ToastItem;
  onDismiss: (id: number) => void;
};

function Toast({ toast, onDismiss }: ToastProps) {
  useEffect(() => {
    const timer = setTimeout(() => onDismiss(toast.id), toast.kind === "error" ? 12000 : 6500);
    return () => clearTimeout(timer);
  }, [toast.id, toast.kind, onDismiss]);

  return (
    <li className={`toast ${toast.kind}`} role={toast.kind === "error" ? "alert" : "status"}>
      <span className="toast-text">{toast.text}</span>
      {toast.action && (
        <button
          className="toast-action"
          onClick={() => {
            toast.action?.onClick();
            onDismiss(toast.id);
          }}
        >
          {toast.action.label}
        </button>
      )}
      <button className="toast-close" aria-label="Dismiss" onClick={() => onDismiss(toast.id)}>
        ×
      </button>
    </li>
  );
}

export function ToastHost({ toasts, onDismiss }: { toasts: ToastItem[]; onDismiss: (id: number) => void }) {
  return (
    <ul className="toasts" aria-live="polite">
      {toasts.map((t) => (
        <Toast key={t.id} toast={t} onDismiss={onDismiss} />
      ))}
    </ul>
  );
}
