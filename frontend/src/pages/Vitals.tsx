import { useEffect, useMemo, useState } from 'react';
import { api } from '../api';
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from 'recharts';

interface M { name: string; n: number; unit: string | null; }
interface P { time: string; value: string; unit: string; value_type: string; }

export default function Vitals() {
  const [meas, setMeas] = useState<M[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [series, setSeries] = useState<P[]>([]);
  const [filter, setFilter] = useState('');

  useEffect(() => { api<M[]>('/api/vitals/measurements').then(setMeas); }, []);
  useEffect(() => {
    if (!selected) return setSeries([]);
    api<P[]>(`/api/vitals/series?name=${encodeURIComponent(selected)}`).then(setSeries);
  }, [selected]);

  const visible = useMemo(() => {
    const f = filter.toLowerCase();
    return meas.filter((m) => (m.name || '').toLowerCase().includes(f)).sort((a, b) => b.n - a.n);
  }, [meas, filter]);

  const chart = series
    .map((p) => ({ time: (p.time || '').slice(0, 10), value: parseFloat(p.value) }))
    .filter((p) => !isNaN(p.value));

  return (
    <>
      <h1>Vitals / Flowsheet</h1>
      <div style={{ display: 'grid', gridTemplateColumns: '300px 1fr', gap: 16 }}>
        <div className="card" style={{ maxHeight: 'calc(100vh - 160px)', overflowY: 'auto' }}>
          <input
            placeholder="filter…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            style={{ width: '100%', marginBottom: 8 }}
          />
          <div className="small muted" style={{ marginBottom: 4 }}>{visible.length} measurements</div>
          {visible.map((c) => (
            <div key={c.name}
              onClick={() => setSelected(c.name)}
              style={{
                padding: '6px 8px', cursor: 'pointer', borderRadius: 4,
                background: selected === c.name ? 'var(--panel-2)' : 'transparent',
                fontSize: 12,
              }}>
              <div>{c.name}</div>
              <div className="muted small">n={c.n}{c.unit ? ` · ${c.unit}` : ''}</div>
            </div>
          ))}
        </div>

        <div>
          {!selected && <div className="card muted">Select a measurement.</div>}
          {selected && (
            <>
              <div className="card">
                <h2 style={{ marginTop: 0, border: 0 }}>{selected}</h2>
                {chart.length > 0 ? (
                  <div style={{ width: '100%', height: 260 }}>
                    <ResponsiveContainer>
                      <LineChart data={chart}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#2a2f3a" />
                        <XAxis dataKey="time" stroke="#9ca3af" fontSize={11} />
                        <YAxis stroke="#9ca3af" fontSize={11} domain={['auto', 'auto']} />
                        <Tooltip contentStyle={{ background: '#171a21', border: '1px solid #2a2f3a', fontSize: 12 }} />
                        <Line type="monotone" dataKey="value" stroke="#34d399" strokeWidth={2} dot={{ r: 3 }} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                ) : (
                  <div className="muted small">(Non-numeric values — see table below.)</div>
                )}
              </div>
              <div className="card">
                <table className="dtable">
                  <thead><tr><th>Time</th><th>Value</th><th>Unit</th><th>Type</th></tr></thead>
                  <tbody>
                    {series.map((p, i) => (
                      <tr key={i}>
                        <td className="mono small">{p.time}</td>
                        <td className="mono">{p.value}</td>
                        <td className="small">{p.unit}</td>
                        <td className="small muted">{p.value_type}</td>
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
