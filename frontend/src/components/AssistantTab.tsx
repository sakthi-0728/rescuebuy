import { useEffect, useRef, useState } from "react";

import { messageOf, post } from "../api";
import type { AssistantResponse } from "../types";

type Message = {
  id: number;
  question: string;
  response: AssistantResponse | null;
  error: string | null;
};

const EXAMPLES = [
  "How many boxes do I have?",
  "How long will the flour last?",
  "Which items could run out within three days?",
  "What should I reorder this week?",
  "How much will the recommended order cost?",
  "Can I afford to restock everything?",
  "Which supplier offers the best eligible option?",
  "What happens if a supplier delivers two days late?",
];

function sourceNote(r: AssistantResponse): string {
  if (r.tool === "refuse_action") return "I only read your data. I never order, approve or pay.";
  return r.answer.source === "gemini"
    ? "Worded by Gemini. Every number was checked against your data."
    : "Calculated from your data.";
}

const LOOKUPS: Record<string, string> = {
  stock_of: "Stock levels",
  days_left: "Days of stock left",
  running_out: "Items that could run out",
  expiring: "Expiry dates",
  what_to_reorder: "What to reorder",
  order_cost: "Order cost",
  budget_check: "Budget check",
  best_supplier: "Supplier comparison",
  late_supplier: "Late-delivery what-if",
  order_status: "Order status",
  refuse_action: "None: it cannot place orders",
  none: "No matching lookup",
};

const UNDERSTOOD: Record<AssistantResponse["routed_by"], string> = {
  gemini: "Gemini chose the lookup",
  keywords: "Keyword matching (AI unavailable or unsure)",
  rules: "Fixed rules",
};

/** What happened to produce an answer, taken from the fields the backend returned. */
function Trace({ r }: { r: AssistantResponse }) {
  const steps = [
    { label: "Understood", value: UNDERSTOOD[r.routed_by] },
    { label: "Looked up", value: LOOKUPS[r.tool] ?? r.tool },
    { label: "Worded", value: r.answer.source === "gemini" ? "Gemini, numbers checked" : "Calculated from your data" },
  ];
  return (
    <div className="trace">
      <ol aria-label="How this answer was produced">
        {steps.map((st) => (
          <li key={st.label}>
            <span className="trace-label">{st.label}</span>
            <span className="trace-value">{st.value}</span>
          </li>
        ))}
      </ol>
      <details className="basis">
        <summary>What it used</summary>
        <ul>
          {r.basis.map((b) => (
            <li key={b}>{b}</li>
          ))}
          <li>As of {new Date(r.as_of).toLocaleTimeString()} (your current records).</li>
          <li>Read-only: nothing was ordered, approved or paid.</li>
        </ul>
      </details>
    </div>
  );
}

export function AssistantTab() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const nextId = useRef(1);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (messages.length > 0) endRef.current?.scrollIntoView({ block: "end" });
  }, [messages]);

  async function ask(question: string) {
    const q = question.trim();
    if (!q || busy) return;
    const id = nextId.current++;
    setMessages((m) => [...m, { id, question: q, response: null, error: null }]);
    setText("");
    setBusy(true);
    try {
      const response = await post<AssistantResponse>("/assistant/ask", { question: q });
      setMessages((m) => m.map((x) => (x.id === id ? { ...x, response } : x)));
    } catch (e) {
      setMessages((m) => m.map((x) => (x.id === id ? { ...x, error: messageOf(e) } : x)));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack">
      <section className="panel" aria-labelledby="ask-title">
        <div className="panel-head">
          <h2 id="ask-title">Ask a question</h2>
          <p className="hint">Answers come from your inventory records. It cannot place orders.</p>
        </div>

        {messages.length === 0 && <p className="empty">Ask about your stock, suppliers, budget or orders. Try one of these:</p>}
        <div className="chips">
          {EXAMPLES.map((q) => (
            <button key={q} type="button" className="chip" disabled={busy} onClick={() => void ask(q)}>
              {q}
            </button>
          ))}
        </div>

        <ol className="chat" aria-live="polite">
          {messages.map((m) => (
            <li key={m.id} className="turn">
              <p className="bubble you">
                <span className="who">You</span>
                {m.question}
              </p>
              <div className="bubble bot">
                <span className="who">Rescue AI</span>
                {m.error && (
                  <p className="error-box" role="alert">
                    {m.error}
                  </p>
                )}
                {!m.response && !m.error && <p className="hint">Thinking…</p>}
                {m.response && (
                  <>
                    <p className="answer">{m.response.answer.text}</p>
                    {m.response.tool === "refuse_action" && <p className="hint">{sourceNote(m.response)}</p>}
                    {m.response.suggestions.length > 0 && (
                      <div className="chips">
                        {m.response.suggestions.map((s) => (
                          <button key={s} type="button" className="chip" disabled={busy} onClick={() => void ask(s)}>
                            {s}
                          </button>
                        ))}
                      </div>
                    )}
                    <Trace r={m.response} />
                  </>
                )}
              </div>
            </li>
          ))}
        </ol>
        <div ref={endRef} />

        <form
          className="ask-form"
          onSubmit={(e) => {
            e.preventDefault();
            void ask(text);
          }}
        >
          <input
            type="text"
            value={text}
            maxLength={500}
            placeholder="Ask about your stock, suppliers, budget or orders"
            aria-label="Your question"
            onChange={(e) => setText(e.target.value)}
          />
          <button className="primary" type="submit" disabled={busy || text.trim() === ""}>
            Ask
          </button>
        </form>
      </section>
    </div>
  );
}
