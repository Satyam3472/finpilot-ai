"use client";

import {
  Activity, ChartNoAxesCombined, CircleHelp, LoaderCircle, MessageSquare, Plus, Send, ShieldCheck, Sparkles, WalletCards,
} from "lucide-react";
import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { Empty, ErrorState, PageTitle, Skeleton } from "@/components/shared";
import { Button } from "@/components/ui/button";
import { useApi } from "@/hooks/use-api";
import { api, streamReply, type ChatHistory, type ChatMessage, type ChatSession } from "@/lib/api";

const prompts = [
  { text: "Analyze my expenses this month.", icon: Activity },
  { text: "Where am I spending the most?", icon: ChartNoAxesCombined },
  { text: "Compare my last two months.", icon: ChartNoAxesCombined },
  { text: "Have I exceeded my budget?", icon: WalletCards },
  { text: "Identify unusual transactions.", icon: CircleHelp },
  { text: "Suggest ways to save money.", icon: Sparkles },
];

type PendingTurn = { id: string; userText: string; response: string };

export function AssistantView({ initialSession }: { initialSession: string }) {
  const sessions = useApi<ChatSession[]>("/chat/sessions");
  const [selection, setSelection] = useState(initialSession);
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [turn, setTurn] = useState<PendingTurn>();
  const [localHistory, setLocalHistory] = useState<ChatHistory>();
  const end = useRef<HTMLDivElement>(null);
  const active = useRef<AbortController | null>(null);
  const chosen = selection || sessions.data?.[0]?.id || "";
  const history = useApi<ChatHistory>(chosen ? `/chat/sessions/${chosen}` : null);
  const stored = localHistory?.id === chosen ? localHistory : history.data;
  const transcript = stored?.messages ?? [];
  const currentTurn = turn?.id === chosen ? turn : undefined;

  useEffect(() => () => active.current?.abort(), []);
  useEffect(() => { end.current?.scrollIntoView({ block: "end" }); }, [chosen, transcript.length, currentTurn?.response]);

  function select(id: string) {
    setSelection(id);
    window.history.replaceState(null, "", `/assistant?session=${encodeURIComponent(id)}`);
  }

  async function create(signal: AbortSignal) {
    const session = await api<ChatSession>("/chat/sessions", { method: "POST", signal });
    select(session.id);
    setLocalHistory({ ...session, messages: [] });
    sessions.refresh();
    return session;
  }

  async function run(createOnly: boolean, message = "") {
    if (active.current || (!createOnly && !message.trim())) return;
    const controller = new AbortController();
    active.current = controller;
    setPending(true);
    setError("");
    let sessionId = chosen;
    let started = false;
    let base = stored;
    try {
      if (createOnly || !sessionId || !stored) {
        if (!createOnly && sessionId && history.loading) return;
        const session = await create(controller.signal);
        sessionId = session.id;
        base = { ...session, messages: [] };
      }
      if (createOnly) {
        setDraft("");
        return;
      }
      started = true;
      setDraft("");
      setTurn({ id: sessionId, userText: message, response: "" });
      const reply = await streamReply(sessionId, message, (delta) => {
        setTurn((current) => current ? { ...current, response: current.response + delta } : current);
      }, controller.signal);
      if (base) {
        setLocalHistory({
          ...base, title: base.messages.length ? base.title : message.slice(0, 72),
          messages: [...base.messages, { role: "user", text: message }, { role: "assistant", text: reply }],
        });
      }
      history.refresh();
      sessions.refresh();
    } catch (problem) {
      if (!controller.signal.aborted) {
        setError(problem instanceof Error ? problem.message : "The assistant could not reply.");
        if (!createOnly) setDraft(message);
        if (started && sessionId) {
          // Reload the committed transcript after an interrupted turn.
          api<ChatHistory>(`/chat/sessions/${sessionId}`, { signal: controller.signal })
            .then((data) => setLocalHistory(data)).catch(() => {});
          sessions.refresh();
        }
      }
    } finally {
      if (!controller.signal.aborted) {
        setTurn(undefined);
        setPending(false);
      }
      active.current = null;
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    void run(false, draft.trim());
  }

  function handleEnter(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void run(false, draft.trim());
    }
  }

  return <div className="page">
    <PageTitle title="AI Assistant" description="Ask FinPilot about spending, budgets, or financial concepts."
      actions={<Button onClick={() => run(true)} disabled={pending}><Plus size={17} /> New conversation</Button>} />
    <div className="chat-layout">
      <aside className="panel chat-sidebar" aria-label="Conversations">
        <h2>Conversations</h2>
        {sessions.loading && !sessions.data && <Skeleton />}
        {sessions.error && <ErrorState message={sessions.error} retry={sessions.refresh} />}
        {sessions.data?.length ? <ul>{sessions.data.map((item) => <li key={item.id}>
          <button type="button" className="conversation-item" aria-pressed={chosen === item.id} disabled={pending}
            onClick={() => { select(item.id); setError(""); setDraft(""); }}>
            <MessageSquare size={15} /><span>{item.title}</span>
          </button>
        </li>)}</ul> : sessions.data && <p className="muted text-sm">Your conversations appear here.</p>}
      </aside>
      <section className="panel chat-panel" aria-label="Assistant conversation">
        <div className="chat-heading"><span className="brand-mark"><Sparkles size={19} /></span>
          <div><h2>{stored?.title ?? "FinPilot Assistant"}</h2><p>Your finance workspace</p></div></div>
        <div className="chat-flow" aria-live="polite">
          {history.loading && !stored && <Skeleton />}
          {history.error && !stored && <ErrorState message={history.error} retry={history.refresh} />}
          {!transcript.length && !currentTurn && !history.loading && !history.error && <>
            <Empty icon={Sparkles} title="What would you like to explore?" text="Ask a question about your imported records or start with a suggested prompt." />
            <div className="prompt-grid">{prompts.map(({ text, icon: Icon }) =>
              <button key={text} type="button" disabled={pending} onClick={() => run(false, text)}>
                <Icon size={17} /><span>{text}</span>
              </button>)}</div>
          </>}
          {transcript.map((item, index) => <Bubble key={index} item={item} />)}
          {currentTurn && <>
            <Bubble item={{ role: "user", text: currentTurn.userText }} />
            {currentTurn.response ? <Bubble item={{ role: "assistant", text: currentTurn.response }} /> :
              <div className="thinking" role="status"><LoaderCircle size={17} className="animate-spin" /> FinPilot is preparing a reply…</div>}
          </>}
          <div ref={end} />
        </div>
        <div className="chat-compose">
          {error && <ErrorState message={error} />}
          <form className="composer" onSubmit={submit}>
            <textarea aria-label="Message FinPilot" rows={2} maxLength={4000} disabled={pending}
              value={draft} placeholder="Ask about your finances…" onChange={(event) => setDraft(event.target.value)} onKeyDown={handleEnter} />
            <Button type="submit" size="icon" aria-label="Send message" disabled={pending || !draft.trim()}><Send size={17} /></Button>
          </form>
          <p className="chat-privacy"><ShieldCheck size={14} /> Chat and selected tool results go to Gemini. FinPilot cannot access bank accounts or change your budgets.</p>
        </div>
      </section>
    </div>
  </div>;
}

function Bubble({ item }: { item: ChatMessage }) {
  return <div className={`message message-${item.role}`}>
    {item.role === "assistant" && <span className="message-icon"><Sparkles size={16} /></span>}
    <div><span className="message-label">{item.role === "user" ? "You" : "FinPilot"}</span><p>{item.text}</p></div>
  </div>;
}
