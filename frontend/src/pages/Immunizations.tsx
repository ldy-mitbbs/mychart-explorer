import { useEffect, useState } from 'react';
import { api } from '../api';

export default function Immunizations() {
  const [rows, setRows] = useState<any[]>([]);
  useEffect(() => { api<any[]>('/api/immunizations').then(setRows); }, []);
  return (
    <>
      <h1>Immunizations <span className="muted small">({rows.length})</span></h1>
      <div className="card">
        <table className="dtable">
          <thead><tr><th>Vaccine</th><th>Date</th><th>Lot</th><th>Route</th><th>Site</th><th>Status</th></tr></thead>
          <tbody>
            {rows.map((v, i) => (
              <tr key={i}>
                <td><b>{v.vaccine || v.code}</b></td>
                <td className="mono small">{(v.occurrenceDateTime || v.date || '').slice(0, 10)}</td>
                <td className="mono small">{v.lotNumber}</td>
                <td className="small">{v.route}</td>
                <td className="small">{v.site}</td>
                <td>{v.status && <span className="pill active">{v.status}</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
