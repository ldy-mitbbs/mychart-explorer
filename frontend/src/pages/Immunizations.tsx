import { useEffect, useState } from 'react';
import { api } from '../api';
import { useT } from '../i18n';

export default function Immunizations() {
  const { t } = useT();
  const [rows, setRows] = useState<any[]>([]);
  useEffect(() => { api<any[]>('/api/immunizations').then(setRows); }, []);
  return (
    <>
      <h1>{t('imms.title')} <span className="muted small">{t('common.count', { n: rows.length })}</span></h1>
      <div className="card">
        <table className="dtable">
          <thead><tr><th>{t('imms.col.vaccine')}</th><th>{t('imms.col.date')}</th><th>{t('imms.col.lot')}</th><th>{t('imms.col.route')}</th><th>{t('imms.col.site')}</th><th>{t('imms.col.status')}</th></tr></thead>
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
