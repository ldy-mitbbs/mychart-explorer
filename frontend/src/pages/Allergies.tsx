import { useEffect, useState } from 'react';
import { api } from '../api';
import { useT } from '../i18n';

export default function Allergies() {
  const { t } = useT();
  const [rows, setRows] = useState<any[]>([]);
  useEffect(() => { api<any[]>('/api/allergies').then(setRows); }, []);
  return (
    <>
      <h1>{t('allergies.title')} <span className="muted small">{t('common.count', { n: rows.length })}</span></h1>
      <div className="card">
        {rows.length === 0 ? (
          <div className="muted">{t('allergies.empty')}</div>
        ) : (
          <table className="dtable">
            <thead><tr><th>{t('allergies.col.allergen')}</th><th>{t('allergies.col.reactions')}</th><th>{t('allergies.col.severity')}</th><th>{t('allergies.col.noted')}</th><th>{t('allergies.col.status')}</th></tr></thead>
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
