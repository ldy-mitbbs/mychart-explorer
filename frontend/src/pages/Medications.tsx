import { useEffect, useState } from 'react';
import { api } from '../api';
import { useT } from '../i18n';

export default function Medications() {
  const { t } = useT();
  const [rows, setRows] = useState<any[]>([]);
  const [filter, setFilter] = useState<'all' | 'active'>('active');
  useEffect(() => { api<any[]>('/api/medications').then(setRows); }, []);

  const filtered = rows.filter((r) => filter === 'all' || !r.discontinue_reason);
  const label = (f: 'active' | 'all') =>
    f === 'active' ? t('meds.filter.active') : t('meds.filter.all');

  return (
    <>
      <h1>{t('meds.title')} <span className="muted small">{t('common.countOf', { n: filtered.length, total: rows.length })}</span></h1>
      <div className="row" style={{ marginBottom: 12 }}>
        {(['active', 'all'] as const).map((f) => (
          <button key={f} className={filter === f ? 'primary' : ''} onClick={() => setFilter(f)}>
            {label(f)}
          </button>
        ))}
      </div>
      <div className="card">
        <table className="dtable">
          <thead>
            <tr>
              <th>{t('meds.col.medication')}</th>
              <th>{t('meds.col.dosage')}</th>
              <th>{t('meds.col.quantity')}</th>
              <th>{t('meds.col.refills')}</th>
              <th>{t('meds.col.started')}</th>
              <th>{t('meds.col.ended')}</th>
              <th>{t('meds.col.prescriber')}</th>
              <th>{t('meds.col.pharmacy')}</th>
              <th>{t('meds.col.discontinued')}</th>
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
