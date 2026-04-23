import { useEffect, useState } from 'react';
import { api } from '../api';

export default function Medications() {
  const [rows, setRows] = useState<any[]>([]);
  const [filter, setFilter] = useState<'all' | 'active'>('active');
  useEffect(() => { api<any[]>('/api/medications').then(setRows); }, []);

  const filtered = rows.filter((r) => filter === 'all' || !r.discontinue_reason);

  return (
    <>
      <h1>Medications <span className="muted small">({filtered.length}/{rows.length})</span></h1>
      <div className="row" style={{ marginBottom: 12 }}>
        {(['active', 'all'] as const).map((f) => (
          <button key={f} className={filter === f ? 'primary' : ''} onClick={() => setFilter(f)}>
            {f}
          </button>
        ))}
      </div>
      <div className="card">
        <table className="dtable">
          <thead>
            <tr>
              <th>Medication</th>
              <th>Dosage</th>
              <th>Quantity</th>
              <th>Refills</th>
              <th>Started</th>
              <th>Ended</th>
              <th>Prescriber</th>
              <th>Pharmacy</th>
              <th>Discontinued</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((m) => (
              <tr key={m.ORDER_MED_ID}>
                <td><b>{m.medication}</b>{m.DESCRIPTION && <div className="small muted">{m.DESCRIPTION}</div>}</td>
                <td>{m.DOSAGE}</td>
                <td className="num">{m.QUANTITY}</td>
                <td className="num">{m.REFILLS}</td>
                <td className="mono small">{(m.START_DATE || '').slice(0, 10)}</td>
                <td className="mono small">{(m.END_DATE || '').slice(0, 10)}</td>
                <td className="small">{m.prescriber}</td>
                <td className="small">{m.pharmacy}</td>
                <td>{m.discontinue_reason && <span className="pill bad">{m.discontinue_reason}</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
