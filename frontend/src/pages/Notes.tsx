import { useEffect, useState } from 'react';
import { api } from '../api';

export default function Notes() {
  const [rows, setRows] = useState<any[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<any>(null);
  const [q, setQ] = useState('');

  useEffect(() => {
    const url = q
      ? `/api/notes?limit=200&q=${encodeURIComponent(q)}`
      : '/api/notes?limit=200';
    api<any[]>(url).then(setRows);
  }, [q]);

  useEffect(() => {
    if (!selected) return setDetail(null);
    api<any>(`/api/notes/${selected}`).then(setDetail);
  }, [selected]);

  return (
    <>
      <h1>Clinical notes <span className="muted small">({rows.length})</span></h1>
      <input
        placeholder="search notes (FTS5, e.g. cholesterol, back pain, knee)"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        style={{ width: 500, marginBottom: 12 }}
      />
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.2fr', gap: 16 }}>
        <div className="card" style={{ maxHeight: 'calc(100vh - 200px)', overflowY: 'auto' }}>
          <table className="dtable">
            <thead><tr><th>Type</th><th>Date</th><th>Author</th></tr></thead>
            <tbody>
              {rows.map((n) => (
                <tr
                  key={n.note_id}
                  onClick={() => setSelected(n.note_id)}
                  style={{ cursor: 'pointer', background: n.note_id === selected ? 'var(--panel-2)' : undefined }}
                >
                  <td>
                    <div>{n.note_type || n.description || <span className="muted">—</span>}</div>
                    {n.snippet && (
                      <div className="small" dangerouslySetInnerHTML={{ __html: n.snippet }} />
                    )}
                  </td>
                  <td className="mono small">{(n.created || '').slice(0, 10)}</td>
                  <td className="small">{n.author}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div>
          {!detail && <div className="card muted">Select a note to read its full text.</div>}
          {detail && (
            <div className="card">
              <div className="row" style={{ justifyContent: 'space-between' }}>
                <div>
                  <h2 style={{ margin: 0, border: 0 }}>{detail.note_type || detail.description || 'Note'}</h2>
                  <div className="small muted">
                    {detail.author && `${detail.author} · `}{(detail.created || '').slice(0, 16)}
                    {detail.pat_enc_csn && ` · CSN ${detail.pat_enc_csn}`}
                    {` · note id ${detail.note_id}`}
                  </div>
                </div>
                <button onClick={() => setSelected(null)}>×</button>
              </div>
              <div className="note-body" style={{ marginTop: 10 }}>
                {detail.full_text || <span className="muted">(no body)</span>}
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
