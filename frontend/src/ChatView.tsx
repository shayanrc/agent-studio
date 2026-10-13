import { useCallback, useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type {
  ChatEvent,
  Conversation,
  ConversationSummary,
  Meta,
  Msg,
  ToolEvent,
} from './types';
import { api, getApiKeys, streamNDJSON } from './api';
import { bus, on, uid } from './state';

const PKEY = 'studio-provider';
const MKEY = 'studio-model';
const RKEY = 'studio-review';

interface ChatRequest {
  prompt: string;
  projectId?: string;
  taskId?: string;
  label?: string;
}

export default function ChatView({ meta }: { meta: Meta | null }) {
  const [convs, setConvs] = useState<ConversationSummary[]>([]);
  const [conv, setConv] = useState<Conversation | null>(null);
  const [provider, setProvider] = useState(() => localStorage.getItem(PKEY) || 'deepseek');
  const [model, setModel] = useState(() => localStorage.getItem(MKEY) || 'deepseek-chat');
  const [review, setReview] = useState(() => localStorage.getItem(RKEY) === '1');
  const [capabilities, setCapabilities] = useState<string[]>(['calculator']);
  const [streaming, setStreaming] = useState(false);
  const [pending, setPending] = useState<{ content: string; toolEvents: ToolEvent[] } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ctxChip, setCtxChip] = useState<string | null>(null);
  const [text, setText] = useState('');
  const abortRef = useRef<AbortController | null>(null);

  const reloadConvs = useCallback(() => {
    api.listConversations().then(setConvs).catch(() => {});
  }, []);

  const selectConv = useCallback(async (id: string) => {
    try {
      setConv(await api.getConversation(id));
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    reloadConvs();
  }, [reloadConvs]);

  // bootstrap: pick the most recent conversation, or create one
  useEffect(() => {
    if (conv) return;
    api
      .listConversations()
      .then(async (list) => {
        if (list.length) {
          await selectConv(list[0].id);
        } else {
          const c = await api.createConversation();
          setConv(c);
          reloadConvs();
        }
      })
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // cross-view trigger (Board → "Implement task")
  useEffect(() => {
    return on('chat-request', (e) => {
      const req = (e as CustomEvent).detail as ChatRequest;
      setCtxChip(req.label || 'scoped task');
      void send(req.prompt, { projectId: req.projectId, taskId: req.taskId, review: true });
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conv, provider, model, capabilities, review, streaming]);

  useEffect(() => {
    localStorage.setItem(PKEY, provider);
    const models = meta?.providers.find((p) => p.id === provider)?.models ?? [];
    if (models.length && !models.some((m) => m.id === model)) setModel(models[0].id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [provider, meta]);

  async function send(
    prompt: string,
    opts: { projectId?: string; taskId?: string; review?: boolean } = {},
  ): Promise<void> {
    if (!prompt.trim() || streaming) return;
    let c = conv;
    if (!c) {
      try {
        c = await api.createConversation();
        setConv(c);
        reloadConvs();
      } catch {
        return;
      }
    }
    const branchId = c.activeBranchId;
    const useReview = opts.review ?? review;
    const optimistic: Msg = { id: uid(), role: 'user', kind: 'message', content: prompt, createdAt: Date.now() };
    setConv({
      ...c,
      title: c.title === 'New chat' ? prompt.slice(0, 48) + (prompt.length > 48 ? '…' : '') : c.title,
      branches: c.branches.map((b) =>
        b.id === branchId ? { ...b, messages: [...b.messages, optimistic] } : b,
      ),
    });
    setPending({ content: '', toolEvents: [] });
    setStreaming(true);
    setError(null);
    setText('');
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    const body = {
      branchId,
      content: prompt,
      provider,
      model,
      capabilities,
      apiKeys: getApiKeys(),
      review: useReview,
      projectId: opts.projectId,
      taskId: opts.taskId,
    };

    try {
      await streamNDJSON(`/api/conversations/${c.id}/chat`, body, (evRaw) => {
        const ev = evRaw as unknown as ChatEvent;
        if (ev.type === 'delta') {
          setPending((p) => (p ? { ...p, content: p.content + ev.text } : p));
        } else if (ev.type === 'tool') {
          setPending((p) => (p ? { ...p, toolEvents: [...p.toolEvents, ev.event] } : p));
        } else if (ev.type === 'done') {
          setConv(ev.conversation);
        } else if (ev.type === 'project') {
          bus.dispatchEvent(new CustomEvent('project-updated', { detail: ev.project }));
        } else if (ev.type === 'error') {
          setError(ev.message);
        }
      }, ctrl.signal);
    } catch (e) {
      if ((e as Error).name !== 'AbortError') setError(String((e as Error).message || e));
    } finally {
      setStreaming(false);
      setPending(null);
      abortRef.current = null;
      try {
        const fresh = await api.getConversation(c.id);
        setConv(fresh);
      } catch {
        /* ignore */
      }
      reloadConvs();
      bus.dispatchEvent(new CustomEvent('workspace-changed'));
    }
  }

  const activeBranch = conv?.branches.find((b) => b.id === conv.activeBranchId) ?? null;

  async function branchOp(op: () => Promise<Conversation>) {
    try {
      setConv(await op());
      reloadConvs();
    } catch (e) {
      setError(String((e as Error).message || e));
    }
  }

  const models = meta?.providers.find((p) => p.id === provider)?.models ?? [];

  return (
    <div className="chat-layout">
      <aside className="sidebar">
        <div className="sidebar-head">
          <span>Conversations</span>
          <button
            className="icon-btn"
            title="New chat"
            onClick={async () => {
              const c = await api.createConversation();
              setConv(c);
              reloadConvs();
            }}
          >
            ＋
          </button>
        </div>
        <div className="conv-list">
          {convs.map((c) => (
            <div
              key={c.id}
              className={conv?.id === c.id ? 'conv-item active' : 'conv-item'}
              onClick={() => selectConv(c.id)}
            >
              <span className="conv-title">{c.title}</span>
              <button
                className="icon-btn"
                title="Delete"
                onClick={async (e) => {
                  e.stopPropagation();
                  await api.deleteConversation(c.id);
                  if (conv?.id === c.id) setConv(null);
                  reloadConvs();
                }}
              >
                🗑
              </button>
            </div>
          ))}
        </div>
        {conv && (
          <div className="branch-panel">
            <div className="sidebar-head">
              <span>Branches</span>
              <button
                className="icon-btn"
                title="New branch (full copy)"
                onClick={() => branchOp(() => api.branch(conv.id, conv.activeBranchId, null))}
              >
                ⑂
              </button>
            </div>
            {conv.branches.map((b) => (
              <div key={b.id} className={b.id === conv.activeBranchId ? 'branch-item active' : 'branch-item'}>
                <span onClick={() => branchOp(() => api.activate(conv.id, b.id))}>{b.name}</span>
                {b.id !== conv.activeBranchId && (
                  <button
                    className="icon-btn"
                    title="Combine active branch onto this one"
                    onClick={() => branchOp(() => api.combine(conv.id, conv.activeBranchId, b.id))}
                  >
                    ⇶
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </aside>

      <div className="chat-main">
        {ctxChip && (
          <div className="ctx-chip">
            <span>🎯 {ctxChip}</span>
            <button className="icon-btn" onClick={() => setCtxChip(null)}>×</button>
          </div>
        )}
        <div className="messages">
          {activeBranch?.messages.map((m) => (
            <MessageRow
              key={m.id}
              msg={m}
              onRewind={(id) => branchOp(() => api.rewind(conv!.id, conv!.activeBranchId, id))}
              onSummarize={(id) =>
                api
                  .summarize(conv!.id, conv!.activeBranchId, id, id, provider, model, getApiKeys())
                  .then(setConv)
                  .catch((e) => setError(String(e.message || e)))
              }
            />
          ))}
          {pending && (
            <div className="msg assistant">
              <div className="msg-meta">
                <span className="role">Agent</span>
                <span className="badge">streaming…</span>
              </div>
              <div className="md">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{pending.content || '…'}</ReactMarkdown>
              </div>
              {pending.toolEvents.map((t, i) => (
                <ToolEventRow key={i} ev={t} />
              ))}
            </div>
          )}
          {error && <div className="error-banner">⚠ {error}</div>}
        </div>

        <div className="composer">
          <div className="composer-controls">
            <select value={provider} onChange={(e) => setProvider(e.target.value)}>
              {(meta?.providers ?? []).map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                  {p.hasKey ? '' : ' (no key)'}
                </option>
              ))}
            </select>
            <select value={model} onChange={(e) => { setModel(e.target.value); localStorage.setItem(MKEY, e.target.value); }}>
              {models.map((m) => (
                <option key={m.id} value={m.id}>{m.name}</option>
              ))}
            </select>
            {(meta?.capabilities ?? []).map((c) => (
              <label key={c.id} className="cap-toggle" title={c.available ? c.name : `${c.name} unavailable`}>
                <input
                  type="checkbox"
                  disabled={!c.available}
                  checked={capabilities.includes(c.id)}
                  onChange={(e) =>
                    setCapabilities(e.target.checked ? [...capabilities, c.id] : capabilities.filter((x) => x !== c.id))
                  }
                />
                {c.name}
              </label>
            ))}
            <label className="cap-toggle" title="Propose file changes for approval instead of applying immediately">
              <input
                type="checkbox"
                checked={review}
                onChange={(e) => {
                  setReview(e.target.checked);
                  localStorage.setItem(RKEY, e.target.checked ? '1' : '0');
                }}
              />
              Review
            </label>
          </div>
          <div className="composer-row">
            <textarea
              value={text}
              placeholder="Describe the change, or ask the agent to inspect the workspace…"
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  void send(text);
                }
              }}
            />
            {streaming ? (
              <button className="btn danger" onClick={() => abortRef.current?.abort()}>
                Stop
              </button>
            ) : (
              <button className="btn primary" disabled={!text.trim()} onClick={() => void send(text)}>
                Send
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function MessageRow({
  msg,
  onRewind,
  onSummarize,
}: {
  msg: Msg;
  onRewind: (id: string) => void;
  onSummarize: (id: string) => void;
}) {
  return (
    <div className={`msg ${msg.role}`}>
      <div className="msg-meta">
        <span className="role">{msg.role === 'user' ? 'You' : 'Agent'}</span>
        {msg.kind === 'summary' && <span className="badge">summary</span>}
        <span className="msg-actions">
          {msg.role === 'user' && (
            <button className="icon-btn" title="Rewind to here" onClick={() => onRewind(msg.id)}>
              ↩
            </button>
          )}
          <button className="icon-btn" title="Summarize this message" onClick={() => onSummarize(msg.id)}>
            ✂
          </button>
        </span>
      </div>
      <div className="md">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
      </div>
      {msg.summaryOf && (
        <details className="summary-orig">
          <summary>Show original ({msg.summaryOf.length} messages)</summary>
          {msg.summaryOf.map((m) => (
            <MessageRow key={m.id} msg={m} onRewind={onRewind} onSummarize={onSummarize} />
          ))}
        </details>
      )}
      {msg.toolEvents?.map((t, i) => (
        <ToolEventRow key={i} ev={t} />
      ))}
    </div>
  );
}

function ToolEventRow({ ev }: { ev: ToolEvent }) {
  if (ev.kind === 'file') return <DiffCard ev={ev} />;
  if (ev.kind === 'run') {
    return (
      <div className="run-card">
        <div className="run-label">
          <code>{ev.label}</code>
          <span className={ev.exitCode === 0 ? 'badge ok' : 'badge warn'}>
            {ev.exitCode === 0 ? 'exit 0' : `exit ${ev.exitCode}`}
          </span>
        </div>
        {ev.stdout && <pre className="run-out">{ev.stdout}</pre>}
        {ev.stderr && <pre className="run-err">{ev.stderr}</pre>}
      </div>
    );
  }
  return (
    <div className="tool-chip">
      {ev.label}: {ev.detail}
    </div>
  );
}

function DiffCard({ ev }: { ev: ToolEvent }) {
  const [state, setState] = useState<'pending' | 'applied' | 'discarded'>(
    ev.applied ? 'applied' : 'pending',
  );
  const [busy, setBusy] = useState(false);

  async function apply() {
    if (!ev.changeId) return;
    setBusy(true);
    try {
      await api.applyChanges([ev.changeId]);
      setState('applied');
      bus.dispatchEvent(new CustomEvent('workspace-changed'));
    } finally {
      setBusy(false);
    }
  }

  async function discard() {
    if (!ev.changeId) return;
    setBusy(true);
    try {
      await api.discardChanges([ev.changeId]);
      setState('discarded');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="diff-card">
      <div className="diff-head">
        <span className="diff-label">{ev.label}</span>
        {state === 'applied' && <span className="badge ok">applied</span>}
        {state === 'discarded' && <span className="badge muted">discarded</span>}
        {state === 'pending' && <span className="badge warn">awaiting review</span>}
      </div>
      {ev.diff && <DiffText diff={ev.diff} />}
      {state === 'pending' && ev.changeId && (
        <div className="diff-actions">
          <button className="btn small primary" disabled={busy} onClick={apply}>
            Apply
          </button>
          <button className="btn small ghost" disabled={busy} onClick={discard}>
            Discard
          </button>
        </div>
      )}
    </div>
  );
}

function DiffText({ diff }: { diff: string }) {
  const lines = diff.split('\n');
  return (
    <pre className="diff">
      {lines.map((l, i) => (
        <span
          key={i}
          className={
            l.startsWith('+') ? 'add' : l.startsWith('-') ? 'del' : l.startsWith('@@') ? 'hunk' : 'ctx'
          }
        >
          {l}
          {'\n'}
        </span>
      ))}
    </pre>
  );
}
