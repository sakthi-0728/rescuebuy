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

function understoodNote(r: AssistantResponse): string | null {
  if (r.routed_by === "gemini") return "Question understood by Gemini.";
  if (r.routed_by === "keywords") return "Question understood by keyword matching (AI unavailable or unsure).";
  return null;
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
          <h2 id="ask-title">Ask Rescue AI</h2>
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
                    <p className="hint">{sourceNote(m.response)}</p>
                    {m.response.suggestions.length > 0 && (
                      <div className="chips">
                        {m.response.suggestions.map((s) => (
                          <button key={s} type="button" className="chip" disabled={busy} onClick={() => void ask(s)}>
                            {s}
                          </button>
                        ))}
                      </div>
                    )}
                    {(m.response.basis.length > 0 || understoodNote(m.response)) && (
                      <details className="basis">
                        <summary>How I got this</summary>
                        <ul>
                          {m.response.basis.map((b) => (
                            <li key={b}>{b}</li>
                          ))}
                          <li>As of {new Date(m.response.as_of).toLocaleTimeString()} (your current records).</li>
                          {understoodNote(m.response) && <li>{understoodNote(m.response)}</li>}
                        </ul>
                      </details>
                    )}
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
