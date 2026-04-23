import { useEffect, useState } from 'react';
import { api } from '../api';

export default function Messages() {
  const [rows, setRows] = useState<any[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<any>(null);
  const [q, setQ] = useState('');

  useEffect(() => {
    const url = q ? `/api/messages?limit=200&q=${encodeURIComponent(q)}` : '/api/messages?limit=200';
    api<any[]>(url).then(setRows);
  }, [q]);

  useEffect(() => {
    if (!selected) return setDetail(null);
    api<any>(`/api/messages/${selected}`).then(setDetail);
  }, [selected]);

  return (
    <>
      <h1>MyChart messages <span className="muted small">({rows.length})</span></h1>
      <input
        placeholder="search messages"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        style={{ width: 500, marginBottom: 12 }}
      />
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.2fr', gap: 16 }}>
        <div className="card" style={{ maxHeight: 'calc(100vh - 200px)', overflowY: 'auto' }}>
          <table className="dtable">
            <thead><tr><th>Subject</th><th>Sent</th><th>From</th></tr></thead>
            <tbody>
              {rows.map((m) => (
                <tr
                  key={m.msg_id}
                  onClick={() => setSelected(m.msg_id)}
                  style={{ cursor: 'pointer', background: m.msg_id === selected ? 'var(--panel-2)' : undefined }}
                >
                  <td>
                    <b>{m.subject || <span className="muted">(no subject)</span>}</b>
                    {m.snippet && <div className="small" dangerouslySetInnerHTML={{ __html: m.snippet }} />}
                  </td>
                  <td className="mono small">{(m.sent || '').slice(0, 10)}</td>
                  <td className="small">{m.from_user}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div>
          {!detail && <div className="card muted">Select a message.</div>}
          {detail && (
            <div className="card">
              <div className="row" style={{ justifyContent: 'space-between' }}>
                <div>
                  <h2 style={{ margin: 0, border: 0 }}>{detail.subject || '(no subject)'}</h2>
                  <div className="small muted">
                    {detail.from_user && `from ${detail.from_user} · `}{(detail.sent || '').slice(0, 16)} · msg {detail.msg_id}
                  </div>
                </div>
                <button onClick={() => setSelected(null)}>×</button>
              </div>
              <div className="note-body" style={{ marginTop: 10 }}>{detail.body || <span className="muted">(no body)</span>}</div>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
