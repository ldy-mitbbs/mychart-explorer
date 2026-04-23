import { useEffect, useMemo, useState } from 'react';
import { api } from '../api';
import { useT } from '../i18n';
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  ReferenceArea, CartesianGrid, ReferenceLine,
} from 'recharts';

interface Component { name: string; n: number; unit: string | null; }
interface Point {
  time: string; raw_value: string; value: string;
  ref_low: string; ref_high: string; unit: string; flag: string; in_range: string;
}

export default function Labs() {
  const { t } = useT();
  const [comps, setComps] = useState<Component[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [series, setSeries] = useState<Point[]>([]);
  const [filter, setFilter] = useState('');

  useEffect(() => { api<Component[]>('/api/labs/components').then(setComps); }, []);
  useEffect(() => {
    if (!selected) return setSeries([]);
    api<Point[]>(`/api/labs/series?component=${encodeURIComponent(selected)}`).then(setSeries);
  }, [selected]);

  const visibleComps = useMemo(() => {
    const f = filter.toLowerCase();
    return comps.filter((c) => c.name.toLowerCase().includes(f)).sort((a, b) => b.n - a.n);
  }, [comps, filter]);

  const chartData = series
    .map((p) => ({
      time: (p.time || '').slice(0, 10),
      value: parseFloat(p.value) || null,
      ref_low: parseFloat(p.ref_low) || null,
      ref_high: parseFloat(p.ref_high) || null,
      flag: p.flag,
      unit: p.unit,
    }))
    .filter((p) => p.value !== null);

  const refLow = chartData[chartData.length - 1]?.ref_low;
  const refHigh = chartData[chartData.length - 1]?.ref_high;
  const unit = chartData[chartData.length - 1]?.unit;

  return (
    <>
      <h1>{t('labs.title')}</h1>
      <div style={{ display: 'grid', gridTemplateColumns: '300px 1fr', gap: 16 }}>
        <div className="card" style={{ maxHeight: 'calc(100vh - 160px)', overflowY: 'auto' }}>
          <input
            placeholder={t('labs.filter.placeholder')}
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            style={{ width: '100%', marginBottom: 8 }}
          />
          <div className="small muted" style={{ marginBottom: 4 }}>
            {t('labs.components', { n: visibleComps.length })}
          </div>
          {visibleComps.map((c) => (
            <div
              key={c.name}
              onClick={() => setSelected(c.name)}
              style={{
                padding: '6px 8px',
                cursor: 'pointer',
                borderRadius: 4,
                background: selected === c.name ? 'var(--panel-2)' : 'transparent',
                fontSize: 12,
              }}
            >
              <div>{c.name}</div>
              <div className="muted small">n={c.n}{c.unit ? ` · ${c.unit}` : ''}</div>
            </div>
          ))}
        </div>

        <div>
          {!selected && <div className="card muted">{t('labs.selectPrompt')}</div>}
          {selected && (
            <>
              <div className="card">
                <h2 style={{ marginTop: 0, border: 0 }}>{selected} {unit && <span className="muted small">({unit})</span>}</h2>
                {chartData.length === 0 ? (
                  <div className="muted">{t('labs.noNumeric')}</div>
                ) : (
                  <div style={{ width: '100%', height: 280 }}>
                    <ResponsiveContainer>
                      <LineChart data={chartData}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#2a2f3a" />
                        <XAxis dataKey="time" stroke="#9ca3af" fontSize={11} />
                        <YAxis stroke="#9ca3af" fontSize={11} domain={['auto', 'auto']} />
                        <Tooltip
                          contentStyle={{ background: '#171a21', border: '1px solid #2a2f3a', fontSize: 12 }}
                          labelStyle={{ color: '#e5e7eb' }}
                        />
                        {refLow && refHigh && (
                          <ReferenceArea y1={refLow} y2={refHigh} fill="#34d399" fillOpacity={0.08} />
                        )}
                        {refLow && <ReferenceLine y={refLow} stroke="#34d399" strokeDasharray="3 3" strokeOpacity={0.5} />}
                        {refHigh && <ReferenceLine y={refHigh} stroke="#34d399" strokeDasharray="3 3" strokeOpacity={0.5} />}
                        <Line type="monotone" dataKey="value" stroke="#60a5fa" strokeWidth={2} dot={{ r: 4 }} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                )}
              </div>

              <div className="card">
                <table className="dtable">
                  <thead><tr><th>{t('labs.col.date')}</th><th>{t('labs.col.value')}</th><th>{t('labs.col.range')}</th><th>{t('labs.col.unit')}</th><th>{t('labs.col.flag')}</th></tr></thead>
                  <tbody>
                    {series.map((p, i) => (
                      <tr key={i}>
                        <td className="mono small">{(p.time || '').slice(0, 10)}</td>
                        <td className="num mono"><b>{p.raw_value}</b></td>
                        <td className="mono small muted">{p.ref_low}–{p.ref_high}</td>
                        <td className="small">{p.unit}</td>
                        <td>{p.flag && <span className="pill warn">{p.flag}</span>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      </div>
    </>
  );
}
