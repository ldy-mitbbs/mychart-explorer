import { useEffect, useState } from 'react';
import { api } from '../api';
import { useT, type TKey } from '../i18n';

type Kind = 'medical' | 'surgical' | 'family' | 'social';

export default function History() {
  const { t } = useT();
  const [kind, setKind] = useState<Kind>('medical');
  const [rows, setRows] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setError(null);
    api<any[]>(`/api/history/${kind}`).then(setRows).catch((e) => {
      setRows([]); setError(e.message);
    });
  }, [kind]);

  const columns = rows[0] ? Object.keys(rows[0]) : [];

  const kindKey: Record<Kind, TKey> = {
    medical: 'history.kind.medical',
    surgical: 'history.kind.surgical',
    family: 'history.kind.family',
    social: 'history.kind.social',
  };

  return (
    <>
      <h1>{t('history.title')}</h1>
      <div className="row" style={{ marginBottom: 12 }}>
        {(['medical', 'surgical', 'family', 'social'] as Kind[]).map((k) => (
          <button key={k} className={kind === k ? 'primary' : ''} onClick={() => setKind(k)}>{t(kindKey[k])}</button>
        ))}
      </div>
      {error && <div className="card muted small">{error}</div>}
      <div className="card" style={{ overflow: 'auto' }}>
        {rows.length === 0 ? <div className="muted">{t('history.empty')}</div> : (
          <table className="dtable">
            <thead><tr>{columns.map((c) => <th key={c}>{c}</th>)}</tr></thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i}>
                  {columns.map((c) => <td key={c} className="small">{String(r[c] ?? '')}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
