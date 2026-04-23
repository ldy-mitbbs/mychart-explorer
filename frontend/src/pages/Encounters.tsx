import { useEffect, useState } from 'react';
import { api } from '../api';
import { useT } from '../i18n';

export default function Encounters() {
  const { t } = useT();
  const [rows, setRows] = useState<any[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<any>(null);
  const [filter, setFilter] = useState('');

  useEffect(() => {
    api<any[]>(`/api/encounters?limit=500${filter ? `&q=${encodeURIComponent(filter)}` : ''}`).then(setRows);
  }, [filter]);

  useEffect(() => {
    if (!selected) return setDetail(null);
    api<any>(`/api/encounters/${selected}`).then(setDetail);
  }, [selected]);

  return (
    <>
      <h1>{t('encounters.title')} <span className="muted small">{t('common.count', { n: rows.length })}</span></h1>
      <input
        placeholder={t('encounters.filter.placeholder')}
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        style={{ width: 360, marginBottom: 12 }}
      />
      <div style={{ display: 'grid', gridTemplateColumns: selected ? '1fr 1fr' : '1fr', gap: 16 }}>
        <div className="card" style={{ maxHeight: 'calc(100vh - 200px)', overflowY: 'auto' }}>
          <table className="dtable">
            <thead><tr><th>{t('encounters.col.date')}</th><th>{t('encounters.col.provider')}</th><th>{t('encounters.col.department')}</th><th>{t('encounters.col.status')}</th></tr></thead>
            <tbody>
              {rows.map((e) => (
                <tr
                  key={e.csn}
                  onClick={() => setSelected(String(e.csn))}
                  style={{ cursor: 'pointer', background: String(e.csn) === selected ? 'var(--panel-2)' : undefined }}
                >
                  <td className="mono small">{(e.CONTACT_DATE || '').slice(0, 10)}</td>
                  <td>{e.provider}</td>
                  <td className="small">{e.department}</td>
                  <td>{e.status && <span className="pill">{e.status}</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {selected && detail && (
          <div className="card" style={{ maxHeight: 'calc(100vh - 200px)', overflowY: 'auto' }}>
            <div className="row" style={{ justifyContent: 'space-between' }}>
              <h2 style={{ margin: 0, border: 0 }}>{t('encounters.detail.title', { id: selected })}</h2>
              <button onClick={() => setSelected(null)}>×</button>
            </div>
            <div className="small muted mono">{detail.encounter?.CONTACT_DATE}</div>

            {detail.reasons?.length > 0 && (
              <>
                <h3 style={{ fontSize: 13 }}>{t('encounters.reasons')}</h3>
                <ul className="small">
                  {detail.reasons.map((r: any, i: number) => (
                    <li key={i}>{r.ENC_REASON_ID_NAME || r.REASON_COMMENTS}</li>
                  ))}
                </ul>
              </>
            )}

            {detail.diagnoses?.length > 0 && (
              <>
                <h3 style={{ fontSize: 13 }}>{t('encounters.diagnoses')}</h3>
                <ul className="small">
                  {detail.diagnoses.map((d: any, i: number) => (
                    <li key={i}>{d.DX_ID_DX_NAME}{d.PRIMARY_DX_YN === 'Y' && <em className="muted"> {t('encounters.primary')}</em>}</li>
                  ))}
                </ul>
              </>
            )}

            {detail.meds?.length > 0 && (
              <>
                <h3 style={{ fontSize: 13 }}>{t('encounters.medOrders', { n: detail.meds.length })}</h3>
                <ul className="small">
                  {detail.meds.map((m: any) => (
                    <li key={m.ORDER_MED_ID}><b>{m.MEDICATION_ID_MEDICATION_NAME}</b> {m.DOSAGE && `– ${m.DOSAGE}`}</li>
                  ))}
                </ul>
              </>
            )}

            {detail.orders?.length > 0 && (
              <>
                <h3 style={{ fontSize: 13 }}>{t('encounters.orders', { n: detail.orders.length })}</h3>
                <ul className="small">
                  {detail.orders.map((o: any) => (
                    <li key={o.ORDER_PROC_ID}>{o.PROC_ID_PROC_NAME} <span className="muted">({o.ORDER_STATUS_C_NAME})</span></li>
                  ))}
                </ul>
              </>
            )}

            {detail.notes?.length > 0 && (
              <>
                <h3 style={{ fontSize: 13 }}>{t('encounters.notes')}</h3>
                <ul className="small">
                  {detail.notes.map((n: any) => (
                    <li key={n.note_id}>
                      <b>{n.note_type || '(note)'}</b> – {n.author} {n.created && <span className="muted">· {(n.created || '').slice(0, 10)}</span>}
                      <div className="muted small">note id {n.note_id}</div>
                    </li>
                  ))}
                </ul>
              </>
            )}

            <details>
              <summary>{t('encounters.rawRow')}</summary>
              <pre className="mono small">{JSON.stringify(detail.encounter, null, 2)}</pre>
            </details>
          </div>
        )}
      </div>
    </>
  );
}
