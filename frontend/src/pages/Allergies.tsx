import { useEffect, useState } from 'react';
import { api } from '../api';

export default function Allergies() {
  const [rows, setRows] = useState<any[]>([]);
  useEffect(() => { api<any[]>('/api/allergies').then(setRows); }, []);
  return (
    <>
      <h1>Allergies <span className="muted small">({rows.length})</span></h1>
      <div className="card">
        {rows.length === 0 ? (
          <div className="muted">No documented allergies.</div>
        ) : (
          <table className="dtable">
            <thead><tr><th>Allergen</th><th>Reactions</th><th>Severity</th><th>Noted</th><th>Status</th></tr></thead>
            <tbody>
              {rows.map((a, i) => (
                <tr key={a.ALLERGY_ID || i}>
                  <td><b>{a.allergen || a.code}</b></td>
                  <td>
                    {a.REACTION || (a.reactions || []).join(', ')}
                    {a.structured_reactions?.length > 0 && (
                      <div className="small muted">
                        {a.structured_reactions.map((r: any) => r.REACTION_ID_NAME).filter(Boolean).join(', ')}
                      </div>
                    )}
                  </td>
                  <td>{a.severity || a.allergy_severity}</td>
                  <td className="mono small">{(a.DATE_NOTED || a.recordedDate || '').slice(0, 10)}</td>
                  <td>{a.status && <span className="pill active">{a.status}</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
