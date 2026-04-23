import { useEffect, useRef, useState } from 'react';
import { api } from '../api';

interface Msg {
  role: 'user' | 'assistant' | 'tool';
  content: string;
  tool_calls?: { id: string; function: { name: string; arguments: string } }[];
  tool_call_id?: string;
  name?: string;
}

interface ToolCallEvent { id: string; name: string; arguments: any; result?: string; }

function CopyCmd({ cmd, hint }: { cmd: string; hint?: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(cmd);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch { /* ignore */ }
  };
  return (
    <div
      className="small"
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        marginTop: 6,
        marginLeft: 8,
        padding: '4px 6px 4px 10px',
        background: 'var(--bg-2)',
        border: '1px solid var(--border)',
        borderRadius: 6,
        fontFamily: 'ui-monospace, monospace',
      }}
      title={hint || 'Run this in Terminal (macOS) or PowerShell (Windows)'}
    >
      <span>{cmd}</span>
      <button
        className="btn"
        onClick={copy}
        style={{ padding: '2px 8px', fontSize: 11 }}
      >
        {copied ? 'copied' : 'copy'}
      </button>
    </div>
  );
}

interface Settings {
  llm_provider?: string;
  ollama_model?: string;
  ollama_url?: string;
  openai_model?: string;
  anthropic_model?: string;
  max_tool_turns?: number;
  has_openai_key?: boolean;
  has_anthropic_key?: boolean;
}

interface Conversation {
  id: string;
  title: string;
  created_at: number;
  updated_at: number;
  message_count: number;
}

interface ConversationDetail extends Conversation {
  messages: Msg[];
}

function conversationLabel(c: Conversation): string {
  const t = (c.title || '').trim();
  if (t) return t.length > 60 ? t.slice(0, 57) + '…' : t;
  return 'Untitled chat';
}

function formatTime(ts: number): string {
  try { return new Date(ts * 1000).toLocaleString(); } catch { return ''; }
}

function renderContent(text: string): (JSX.Element | string)[] {
  // Linkify [note:ID] / [msg:ID] / [table:NAME ...] as pills.
  const parts: (JSX.Element | string)[] = [];
  const regex = /\[(note|msg|table):([^\]]+)\]/g;
  let last = 0, match, i = 0;
  while ((match = regex.exec(text)) !== null) {
    if (match.index > last) parts.push(text.slice(last, match.index));
    parts.push(
      <span key={`c${i++}`} className="pill" style={{ fontFamily: 'monospace', fontSize: 11 }}>
        {match[1]}:{match[2]}
      </span>,
    );
    last = match.index + match[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

export default function Chat({ onProviderChange }: { onProviderChange?: (p: string) => void }) {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [streamText, setStreamText] = useState('');
  const [streamTools, setStreamTools] = useState<ToolCallEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [settings, setSettings] = useState<Settings>({});
  const [showSettings, setShowSettings] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(
    () => localStorage.getItem('mychart.conversationId')
  );
  const [ollamaModels, setOllamaModels] = useState<string[] | null>(null);
  const [ollamaModelsError, setOllamaModelsError] = useState<string | null>(null);
  const [ollamaModelsLoading, setOllamaModelsLoading] = useState(false);
  const msgsRef = useRef<HTMLDivElement>(null);

  useEffect(() => { api<Settings>('/api/settings').then(setSettings); }, []);
  useEffect(() => { msgsRef.current?.scrollTo(0, msgsRef.current.scrollHeight); }, [messages, streamText, streamTools]);

  useEffect(() => {
    if (conversationId) {
      localStorage.setItem('mychart.conversationId', conversationId);
    } else {
      localStorage.removeItem('mychart.conversationId');
    }
  }, [conversationId]);

  async function refreshConversations() {
    try {
      const list = await api<Conversation[]>('/api/conversations');
      setConversations(list);
    } catch { /* ignore */ }
  }

  // Initial load: restore last conversation if it still exists.
  useEffect(() => {
    (async () => {
      await refreshConversations();
      if (conversationId) {
        try {
          const c = await api<ConversationDetail>(`/api/conversations/${conversationId}`);
          setMessages(c.messages.filter((m) => m.role === 'user' || m.role === 'assistant'));
        } catch {
          setConversationId(null);
        }
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function ensureConversation(): Promise<string> {
    if (conversationId) return conversationId;
    const c = await api<Conversation>('/api/conversations', {
      method: 'POST', body: JSON.stringify({}),
    });
    setConversationId(c.id);
    setConversations((cs) => [c, ...cs]);
    return c.id;
  }

  async function loadConversation(cid: string) {
    if (streaming) return;
    try {
      const c = await api<ConversationDetail>(`/api/conversations/${cid}`);
      setMessages(c.messages.filter((m) => m.role === 'user' || m.role === 'assistant'));
      setConversationId(cid);
      setShowHistory(false);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  function newChat() {
    if (streaming) return;
    setMessages([]);
    setConversationId(null);
    setError(null);
  }

  async function deleteConversation(cid: string) {
    if (streaming) return;
    if (!confirm('Delete this conversation?')) return;
    try {
      await api(`/api/conversations/${cid}`, { method: 'DELETE' });
      setConversations((cs) => cs.filter((c) => c.id !== cid));
      if (cid === conversationId) newChat();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function renameConversation(cid: string, current: string) {
    if (streaming) return;
    const title = prompt('Rename conversation:', current);
    if (title === null) return;
    try {
      const c = await api<Conversation>(`/api/conversations/${cid}`, {
        method: 'PATCH', body: JSON.stringify({ title }),
      });
      setConversations((cs) => cs.map((x) => (x.id === cid ? { ...x, title: c.title } : x)));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function send() {
    if (!input.trim() || streaming) return;
    setError(null);
    const nextMsgs: Msg[] = [...messages, { role: 'user', content: input }];
    setMessages(nextMsgs);
    setInput('');
    setStreaming(true);
    setStreamText('');
    setStreamTools([]);

    let assistantText = '';
    const toolEvents: ToolCallEvent[] = [];
    let cid: string | null = null;

    try {
      cid = await ensureConversation();
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          messages: nextMsgs.map(({ role, content }) => ({ role, content })),
          conversation_id: cid,
        }),
      });
      if (!res.ok || !res.body) throw new Error(`${res.status} ${res.statusText}`);

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = '';
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        let idx;
        while ((idx = buf.indexOf('\n\n')) !== -1) {
          const chunk = buf.slice(0, idx).trim();
          buf = buf.slice(idx + 2);
          if (!chunk.startsWith('data:')) continue;
          const payload = chunk.slice(5).trim();
          if (!payload) continue;
          let evt: any;
          try { evt = JSON.parse(payload); } catch { continue; }
          if (evt.type === 'text') {
            assistantText += evt.text;
            setStreamText(assistantText);
          } else if (evt.type === 'tool_call') {
            toolEvents.push({ id: evt.id, name: evt.name, arguments: evt.arguments });
            setStreamTools([...toolEvents]);
          } else if (evt.type === 'tool_result') {
            const tc = toolEvents.find((t) => t.id === evt.id);
            if (tc) { tc.result = evt.result; setStreamTools([...toolEvents]); }
          } else if (evt.type === 'error') {
            setError(evt.message);
          } else if (evt.type === 'done') {
            // stream end
          }
        }
      }
    } catch (e) {
      setError((e as Error).message);
    }

    setMessages((m) => [...m, { role: 'assistant', content: assistantText }]);
    setStreaming(false);
    setStreamText('');
    setStreamTools([]);
    if (cid) refreshConversations();
  }

  async function saveSettings(patch: Partial<Settings>) {
    const r = await api<Settings>('/api/settings', { method: 'POST', body: JSON.stringify(patch) });
    setSettings(r);
    if (patch.llm_provider && onProviderChange) onProviderChange(patch.llm_provider);
  }

  async function refreshOllamaModels(url?: string) {
    setOllamaModelsLoading(true);
    setOllamaModelsError(null);
    try {
      const qs = url ? `?url=${encodeURIComponent(url)}` : '';
      const r = await api<{ ok: boolean; models: string[]; error?: string }>(
        `/api/ollama/models${qs}`,
      );
      if (r.ok) {
        setOllamaModels(r.models);
      } else {
        setOllamaModels([]);
        setOllamaModelsError(r.error || 'Could not reach Ollama');
      }
    } catch (e) {
      setOllamaModels([]);
      setOllamaModelsError((e as Error).message);
    } finally {
      setOllamaModelsLoading(false);
    }
  }

  // Load the Ollama model list when the settings panel is first opened for
  // the ollama provider, or when the URL changes.
  useEffect(() => {
    if (showSettings && settings.llm_provider === 'ollama') {
      refreshOllamaModels(settings.ollama_url);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showSettings, settings.llm_provider, settings.ollama_url]);

  return (
    <div className="chat">
      <div className="row" style={{ justifyContent: 'space-between', marginBottom: 8 }}>
        <div>
          <h1 style={{ margin: 0 }}>Ask AI</h1>
          <div className="small muted">
            Provider: <b>{settings.llm_provider}</b>
            {settings.llm_provider === 'ollama' && settings.ollama_model && ` · ${settings.ollama_model}`}
            {settings.llm_provider === 'openai' && settings.openai_model && ` · ${settings.openai_model}`}
            {settings.llm_provider === 'anthropic' && settings.anthropic_model && ` · ${settings.anthropic_model}`}
          </div>
        </div>
        <div className="row">
          <button onClick={newChat} disabled={streaming}>New chat</button>
          <button onClick={() => setShowHistory((s) => !s)} disabled={streaming}>
            History{conversations.length ? ` (${conversations.length})` : ''}
          </button>
          <button onClick={() => setShowSettings((s) => !s)}>Settings</button>
        </div>
      </div>

      {showHistory && (
        <div className="card">
          <div className="row" style={{ justifyContent: 'space-between', marginBottom: 6 }}>
            <b>Conversation history</b>
            <button onClick={() => setShowHistory(false)}>Close</button>
          </div>
          {conversations.length === 0 && (
            <div className="small muted">No saved conversations yet.</div>
          )}
          {conversations.map((c) => (
            <div
              key={c.id}
              className="row"
              style={{
                justifyContent: 'space-between',
                padding: '6px 0',
                borderTop: '1px solid var(--border, #2a2a2a)',
                background: c.id === conversationId ? 'rgba(255,255,255,0.04)' : undefined,
              }}
            >
              <div
                style={{ flex: 1, cursor: 'pointer', overflow: 'hidden' }}
                onClick={() => loadConversation(c.id)}
                title="Load this conversation"
              >
                <div style={{ fontWeight: c.id === conversationId ? 600 : 400 }}>
                  {conversationLabel(c)}
                </div>
                <div className="small muted">
                  {c.message_count} msg · {formatTime(c.updated_at)}
                </div>
              </div>
              <div className="row" style={{ gap: 4 }}>
                <button onClick={() => renameConversation(c.id, c.title)} disabled={streaming}>
                  Rename
                </button>
                <button onClick={() => deleteConversation(c.id)} disabled={streaming}>
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {showSettings && (
        <div className="card">
          <div className="row" style={{ gap: 12, flexWrap: 'wrap' }}>
            <label>Provider
              <select
                value={settings.llm_provider || 'ollama'}
                onChange={(e) => saveSettings({ llm_provider: e.target.value })}
                style={{ marginLeft: 6 }}
              >
                <option value="ollama">ollama (local)</option>
                <option value="openai">openai (cloud)</option>
                <option value="anthropic">anthropic (cloud)</option>
              </select>
            </label>
            {settings.llm_provider === 'ollama' && (
              <>
                <label>Model
                  {ollamaModels && ollamaModels.length > 0 ? (
                    <select
                      value={
                        settings.ollama_model && ollamaModels.includes(settings.ollama_model)
                          ? settings.ollama_model
                          : '__custom__'
                      }
                      onChange={(e) => {
                        const v = e.target.value;
                        if (v === '__custom__') {
                          // Switch to a blank custom entry; text input appears below.
                          setSettings({ ...settings, ollama_model: '' });
                        } else {
                          saveSettings({ ollama_model: v });
                        }
                      }}
                      style={{ marginLeft: 6, minWidth: 220 }}
                    >
                      {settings.ollama_model &&
                        !ollamaModels.includes(settings.ollama_model) && (
                          <option value={settings.ollama_model}>
                            {settings.ollama_model} (not installed)
                          </option>
                        )}
                      {ollamaModels.map((m) => (
                        <option key={m} value={m}>{m}</option>
                      ))}
                      <option value="__custom__">Custom…</option>
                    </select>
                  ) : (
                    <input
                      value={settings.ollama_model || ''}
                      onChange={(e) => setSettings({ ...settings, ollama_model: e.target.value })}
                      onBlur={() => saveSettings({ ollama_model: settings.ollama_model })}
                      style={{ marginLeft: 6, width: 220 }}
                      placeholder="e.g. llama3.1:8b"
                    />
                  )}
                  <button
                    className="btn"
                    onClick={() => refreshOllamaModels(settings.ollama_url)}
                    disabled={ollamaModelsLoading}
                    style={{ marginLeft: 6 }}
                    title="Refresh list from Ollama"
                  >
                    {ollamaModelsLoading ? '…' : '↻'}
                  </button>
                  {ollamaModels &&
                    ollamaModels.length > 0 &&
                    settings.ollama_model !== undefined &&
                    !ollamaModels.includes(settings.ollama_model || '') && (
                      <input
                        value={settings.ollama_model || ''}
                        onChange={(e) => setSettings({ ...settings, ollama_model: e.target.value })}
                        onBlur={() => saveSettings({ ollama_model: settings.ollama_model })}
                        placeholder="custom model tag"
                        style={{ marginLeft: 6, width: 220 }}
                      />
                    )}
                  {ollamaModelsError && (
                    <>
                      <span className="small warn-text" style={{ marginLeft: 8 }}>
                        {ollamaModelsError} — is Ollama running?
                      </span>
                      <CopyCmd cmd="ollama serve" hint="Start the Ollama server" />
                    </>
                  )}
                  {ollamaModels && ollamaModels.length === 0 && !ollamaModelsError && (
                    <>
                      <span className="small muted" style={{ marginLeft: 8 }}>
                        No models installed. Run this to pull one:
                      </span>
                      <CopyCmd cmd="ollama pull llama3.1:8b" />
                    </>
                  )}
                  {ollamaModels &&
                    ollamaModels.length > 0 &&
                    settings.ollama_model &&
                    !ollamaModels.includes(settings.ollama_model) && (
                      <>
                        <span className="small warn-text" style={{ marginLeft: 8 }}>
                          Model <code>{settings.ollama_model}</code> is not installed.
                        </span>
                        <CopyCmd
                          cmd={`ollama pull ${settings.ollama_model}`}
                          hint="Run in Terminal (macOS) or PowerShell (Windows), then click ↻ to refresh"
                        />
                      </>
                    )}
                </label>
                <label>URL
                  <input
                    value={settings.ollama_url || ''}
                    onChange={(e) => setSettings({ ...settings, ollama_url: e.target.value })}
                    onBlur={() => saveSettings({ ollama_url: settings.ollama_url })}
                    style={{ marginLeft: 6, width: 260 }}
                  />
                </label>
              </>
            )}
            {settings.llm_provider === 'openai' && (
              <label>Model
                <input
                  value={settings.openai_model || ''}
                  onChange={(e) => setSettings({ ...settings, openai_model: e.target.value })}
                  onBlur={() => saveSettings({ openai_model: settings.openai_model })}
                  style={{ marginLeft: 6, width: 220 }}
                />
                <span className="small muted" style={{ marginLeft: 8 }}>
                  API key: {settings.has_openai_key ? 'OPENAI_API_KEY set' : 'missing — export OPENAI_API_KEY before starting backend'}
                </span>
              </label>
            )}
            {settings.llm_provider === 'anthropic' && (
              <label>Model
                <input
                  value={settings.anthropic_model || ''}
                  onChange={(e) => setSettings({ ...settings, anthropic_model: e.target.value })}
                  onBlur={() => saveSettings({ anthropic_model: settings.anthropic_model })}
                  style={{ marginLeft: 6, width: 220 }}
                />
                <span className="small muted" style={{ marginLeft: 8 }}>
                  API key: {settings.has_anthropic_key ? 'ANTHROPIC_API_KEY set' : 'missing — export ANTHROPIC_API_KEY before starting backend'}
                </span>
              </label>
            )}
            <label>Max tool turns
              <input
                type="number"
                min={1}
                max={100}
                value={settings.max_tool_turns ?? 20}
                onChange={(e) => setSettings({ ...settings, max_tool_turns: Number(e.target.value) })}
                onBlur={() => saveSettings({ max_tool_turns: settings.max_tool_turns })}
                style={{ marginLeft: 6, width: 80 }}
              />
              <span className="small muted" style={{ marginLeft: 8 }}>
                Cap on tool-call iterations per question (1–100).
              </span>
            </label>
          </div>
        </div>
      )}

      <div className="messages" ref={msgsRef}>
        {messages.length === 0 && !streaming && (
          <div className="card muted">
            <div><b>Try asking:</b></div>
            <ul>
              <li>What are my active problems and medications?</li>
              <li>Show my HbA1c trend over time.</li>
              <li>Summarize my most recent primary-care visit.</li>
              <li>Do I have any abnormal labs in the last year?</li>
            </ul>
          </div>
        )}

        {messages.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            <div className="bubble">{renderContent(m.content)}</div>
          </div>
        ))}

        {streaming && (streamText || streamTools.length > 0) && (
          <div className="msg assistant">
            {streamTools.map((t) => (
              <div key={t.id} className="toolcall">
                <span className="chip">🔧 {t.name}({JSON.stringify(t.arguments)})</span>
                {t.result !== undefined && (
                  <details><summary>result ({t.result.length} chars)</summary><pre>{t.result.slice(0, 2000)}</pre></details>
                )}
              </div>
            ))}
            {streamText && <div className="bubble">{renderContent(streamText)}</div>}
          </div>
        )}

        {error && (() => {
          const m = error.match(/model ["']?([\w.:\-/]+)["']? not found/i);
          const missing = m?.[1] || (/not found.*pulling it first/i.test(error) ? settings.ollama_model : null);
          const unreachable = /Connection refused|ECONNREFUSED|Could not reach|Failed to connect/i.test(error);
          return (
            <div className="msg assistant">
              <div className="bubble" style={{ color: 'var(--danger)' }}>
                <div>Error: {error}</div>
                {missing && settings.llm_provider === 'ollama' && (
                  <div style={{ marginTop: 6 }}>
                    <span className="small">Fix: pull the model, then retry.</span>
                    <CopyCmd
                      cmd={`ollama pull ${missing}`}
                      hint="Run in Terminal (macOS) or PowerShell (Windows)"
                    />
                  </div>
                )}
                {unreachable && settings.llm_provider === 'ollama' && (
                  <div style={{ marginTop: 6 }}>
                    <span className="small">Fix: start the Ollama server.</span>
                    <CopyCmd cmd="ollama serve" />
                  </div>
                )}
              </div>
            </div>
          );
        })()}
      </div>

      <div className="composer">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } }}
          placeholder="Ask about your health data… (Enter to send, Shift+Enter for newline)"
        />
        <button className="primary" onClick={send} disabled={streaming || !input.trim()}>
          {streaming ? 'Streaming…' : 'Send'}
        </button>
      </div>
    </div>
  );
}
