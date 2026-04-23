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
  const msgsRef = useRef<HTMLDivElement>(null);

  useEffect(() => { api<Settings>('/api/settings').then(setSettings); }, []);
  useEffect(() => { msgsRef.current?.scrollTo(0, msgsRef.current.scrollHeight); }, [messages, streamText, streamTools]);

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

    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: nextMsgs.map(({ role, content }) => ({ role, content })) }),
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
  }

  async function saveSettings(patch: Partial<Settings>) {
    const r = await api<Settings>('/api/settings', { method: 'POST', body: JSON.stringify(patch) });
    setSettings(r);
    if (patch.llm_provider && onProviderChange) onProviderChange(patch.llm_provider);
  }

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
          <button onClick={() => setMessages([])} disabled={streaming || messages.length === 0}>Clear</button>
          <button onClick={() => setShowSettings((s) => !s)}>Settings</button>
        </div>
      </div>

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
                  <input
                    value={settings.ollama_model || ''}
                    onChange={(e) => setSettings({ ...settings, ollama_model: e.target.value })}
                    onBlur={() => saveSettings({ ollama_model: settings.ollama_model })}
                    style={{ marginLeft: 6, width: 220 }}
                  />
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

        {error && (
          <div className="msg assistant">
            <div className="bubble" style={{ color: 'var(--danger)' }}>Error: {error}</div>
          </div>
        )}
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
