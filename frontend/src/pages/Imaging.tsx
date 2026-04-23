import { useEffect, useState } from 'react';
import { api } from '../api';
import { useT } from '../i18n';

type Row = {
  note_id: string;
  description: string;
  author: string;
  created: string;
  pat_enc_csn: string;
  preview: string;
};

export default function Imaging() {
  const { t } = useT();
  const [rows, setRows] = useState<Row[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<any>(null);

  useEffect(() => {
    api<Row[]>('/api/imaging?limit=200').then(setRows);
  }, []);

  useEffect(() => {
    if (!selected) return setDetail(null);
    api<any>(`/api/notes/${selected}`).then(setDetail);
  }, [selected]);

  return (
    <>
      <h1>{t('imaging.title')} <span className="muted small">{t('common.count', { n: rows.length })}</span></h1>
      {rows.length === 0 && (
        <div className="card muted">
          {t('imaging.empty')}
        </div>
      )}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.4fr', gap: 16 }}>
        <div className="card" style={{ maxHeight: 'calc(100vh - 200px)', overflowY: 'auto' }}>
          <table className="dtable">
            <thead><tr><th>{t('imaging.col.date')}</th><th>{t('imaging.col.study')}</th><th>{t('imaging.col.reader')}</th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr
                  key={r.note_id}
                  onClick={() => setSelected(r.note_id)}
                  style={{ cursor: 'pointer', background: r.note_id === selected ? 'var(--panel-2)' : undefined }}
                >
                  <td className="mono small">{(r.created || '').slice(0, 10)}</td>
                  <td>
                    <div>{r.description || <span className="muted">—</span>}</div>
                    {r.preview && (
                      <div className="small muted" style={{ marginTop: 2 }}>
                        {r.preview.replace(/\s+/g, ' ').slice(0, 140)}…
                      </div>
                    )}
                  </td>
                  <td className="small">{r.author}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div>
          {!detail && <div className="card muted">{t('imaging.selectPrompt')}</div>}
          {detail && (
            <div className="card">
              <div className="row" style={{ justifyContent: 'space-between' }}>
                <div>
                  <h2 style={{ margin: 0, border: 0 }}>{detail.description || t('imaging.defaultTitle')}</h2>
                  <div className="small muted">
                    {detail.author && `${detail.author} · `}{(detail.created || '').slice(0, 16)}
                    {detail.pat_enc_csn && ` · CSN ${detail.pat_enc_csn}`}
                    {` · note id ${detail.note_id}`}
                  </div>
                </div>
                <button onClick={() => setSelected(null)}>×</button>
              </div>
              <div className="note-body" style={{ marginTop: 10 }}>
                {detail.full_text || <span className="muted">{t('imaging.noBody')}</span>}
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
