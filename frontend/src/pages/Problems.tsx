import { useEffect, useState } from 'react';
import { api } from '../api';

export default function Problems() {
  const [rows, setRows] = useState<any[]>([]);
  const [filter, setFilter] = useState<'all' | 'active' | 'resolved'>('active');

  useEffect(() => { api<any[]>('/api/problems').then(setRows); }, []);

  const filtered = rows.filter((r) => {
    if (filter === 'all') return true;
    const active = (r.PROBLEM_STATUS_C_NAME === 'Active') || (!r.RESOLVED_DATE && r.PROBLEM_STATUS_C_NAME !== 'Resolved');
    return filter === 'active' ? active : !active;
  });

  return (
    <>
      <h1>Problems <span className="muted small">({filtered.length}/{rows.length})</span></h1>
      <div className="row" style={{ marginBottom: 12 }}>
        {(['active', 'resolved', 'all'] as const).map((f) => (
          <button key={f} className={filter === f ? 'primary' : ''} onClick={() => setFilter(f)}>
            {f}
          </button>
        ))}
      </div>
      <div className="card">
        <table className="dtable">
          <thead>
            <tr>
              <th>Problem</th>
              <th>Noted</th>
              <th>Resolved</th>
              <th>Status</th>
              <th>Priority</th>
              <th>Chronic</th>
              <th>Description</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((p) => (
              <tr key={p.PROBLEM_LIST_ID || p.id}>
                <td><b>{p.DX_ID_DX_NAME || p.description}</b></td>
                <td className="mono small">{(p.NOTED_DATE || '').slice(0, 10)}</td>
                <td className="mono small">{(p.RESOLVED_DATE || '').slice(0, 10)}</td>
                <td>{p.PROBLEM_STATUS_C_NAME && <span className="pill active">{p.PROBLEM_STATUS_C_NAME}</span>}</td>
                <td>{p.PRIORITY_C_NAME || ''}</td>
                <td>{p.CHRONIC_YN === 'Y' ? 'Yes' : ''}</td>
                <td className="small muted">{p.DESCRIPTION || ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
