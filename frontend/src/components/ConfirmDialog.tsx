import { useEffect, useRef } from "react";

export type DialogSpec = {
  title: string;
  lines: string[];
  confirmLabel: string;
  tone?: "normal" | "danger";
};

type Props = {
  spec: DialogSpec | null;
  onResolve: (ok: boolean) => void;
};

/** A real modal (native <dialog>): focus is trapped, Escape cancels. Replaces the browser's confirm(). */
export function ConfirmDialog({ spec, onResolve }: Props) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (spec && !dialog.open) dialog.showModal();
    if (!spec && dialog.open) dialog.close();
  }, [spec]);

  return (
    <dialog
      ref={ref}
      className="modal"
      aria-labelledby="modal-title"
      onCancel={(e) => {
        e.preventDefault();
        onResolve(false);
      }}
    >
      {spec && (
        <div className="modal-body">
          <h2 id="modal-title">{spec.title}</h2>
          {spec.lines.map((line) => (
            <p key={line}>{line}</p>
          ))}
          <div className="modal-actions">
            <button autoFocus onClick={() => onResolve(false)}>
              Cancel
            </button>
            <button className={spec.tone === "danger" ? "danger" : "primary"} onClick={() => onResolve(true)}>
              {spec.confirmLabel}
            </button>
          </div>
        </div>
      )}
    </dialog>
  );
}
