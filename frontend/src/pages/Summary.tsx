import { useEffect, useState } from 'react';
import { api } from '../api';
import { ageFromDob } from '../age';
import { toDisplay, prettyName } from '../vitals_format';

export default function Summary() {
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const [patient, problems, meds, allergies, imms, vitals, labs] = await Promise.all([
          api<any>('/api/patient'),
          api<any[]>('/api/problems'),
          api<any[]>('/api/medications'),
          api<any[]>('/api/allergies'),
          api<any[]>('/api/immunizations'),
          api<any[]>('/api/vitals/recent'),
          api<any[]>('/api/labs/recent?limit=12'),
        ]);
        const activeProblems = problems.filter(
          (p) => (p.PROBLEM_STATUS_C_NAME || p.status) === 'Active' || !p.RESOLVED_DATE,
        );
        const activeMeds = meds.filter((m) => !m.discontinue_reason);
        setData({ patient, problems, activeProblems, meds, activeMeds, allergies, imms, vitals, labs });
      } catch (e) {
        setError((e as Error).message);
      }
    })();
  }, []);

  if (error) return <div className="card" style={{ color: 'var(--danger)' }}>{error}</div>;
  if (!data) return <div>Loading…</div>;

  const p = data.patient;
  return (
    <>
      <h1>Summary</h1>
      <div className="cards">
        <div className="card">
          <div className="muted small">Patient</div>
          <div style={{ fontSize: 18, marginTop: 4 }}><b>{p?.name}</b></div>
          <div className="small muted" style={{ marginTop: 6 }}>
            {ageFromDob(p?.birthDate) !== null && `Age ${ageFromDob(p?.birthDate)}`}
            {p?.gender && ` · ${p.gender}`}
          </div>

        </div>

        <div className="card">
          <div className="muted small">Active problems</div>
          <div style={{ fontSize: 28, marginTop: 4 }}>{data.activeProblems.length}</div>
          <div className="small muted">{data.problems.length} total</div>
        </div>

        <div className="card">
          <div className="muted small">Active medications</div>
          <div style={{ fontSize: 28, marginTop: 4 }}>{data.activeMeds.length}</div>
          <div className="small muted">{data.meds.length} total orders</div>
        </div>

        <div className="card">
          <div className="muted small">Allergies</div>
          <div style={{ fontSize: 28, marginTop: 4 }}>{data.allergies.length}</div>
        </div>

        <div className="card">
          <div className="muted small">Immunizations</div>
          <div style={{ fontSize: 28, marginTop: 4 }}>{data.imms.length}</div>
        </div>
      </div>

      <h2>Active problems</h2>
      <div className="card">
        {data.activeProblems.length === 0 ? (
          <div className="muted">No active problems.</div>
        ) : (
          <table className="dtable">
            <thead><tr><th>Problem</th><th>Noted</th><th>Priority</th><th>Chronic</th></tr></thead>
            <tbody>
              {data.activeProblems.map((p: any) => (
                <tr key={p.PROBLEM_LIST_ID || p.id}>
                  <td>{p.DX_ID_DX_NAME || p.description}</td>
                  <td className="mono small">{(p.NOTED_DATE || p.onsetDateTime || '').slice(0, 10)}</td>
                  <td>{p.PRIORITY_C_NAME || ''}</td>
                  <td>{p.CHRONIC_YN === 'Y' ? 'Yes' : ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <h2>Latest vitals</h2>
      <div className="card">
        {(() => {
          const priority = [
            'BP', 'Blood Pressure',
            'Pulse', 'Heart Rate',
            'Temp', 'Temperature',
            'Resp', 'Respirations',
            'SpO2', 'Pulse Ox',
            'Weight', 'Height', 'BMI',
          ];
          const score = (name: string) => {
            const n = prettyName(name || '').toLowerCase();
            const idx = priority.findIndex((k) => n.includes(k.toLowerCase()));
            return idx === -1 ? 999 : idx;
          };
          const rows: any[] = [...data.vitals]
            .sort((a, b) => score(a.name) - score(b.name))
            .slice(0, 8);
          if (rows.length === 0) return <div className="muted">No vitals recorded.</div>;
          return (
            <table className="dtable">
              <thead><tr><th>Measurement</th><th>Value</th><th>Recorded</th></tr></thead>
              <tbody>
                {rows.map((v: any, i: number) => {
                  const d = toDisplay(v.value, v.unit);
                  return (
                    <tr key={i} title={v.name}>
                      <td>{prettyName(v.name)}</td>
                      <td className="mono">{d.value}{d.unit ? ` ${d.unit}` : ''}</td>
                      <td className="mono small">{(v.time || '').slice(0, 16).replace('T', ' ')}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          );
        })()}
      </div>

      <h2>Recent lab results</h2>
      <div className="card">
        {data.labs.length === 0 ? (
          <div className="muted">No lab results.</div>
        ) : (
          <table className="dtable">
            <thead><tr><th>Component</th><th>Value</th><th>Ref range</th><th>Flag</th><th>Date</th></tr></thead>
            <tbody>
              {data.labs.map((l: any, i: number) => {
                const abnormal = l.in_range === 'N' || (l.flag && l.flag !== 'Normal');
                const range = l.ref_low || l.ref_high
                  ? `${l.ref_low || ''}${(l.ref_low && l.ref_high) ? '–' : ''}${l.ref_high || ''}`
                  : '';
                return (
                  <tr key={i}>
                    <td>{l.name}</td>
                    <td className="mono" style={abnormal ? { color: 'var(--danger)' } : undefined}>
                      {l.value}{l.unit ? ` ${l.unit}` : ''}
                    </td>
                    <td className="mono small muted">{range}{range && l.unit ? ` ${l.unit}` : ''}</td>
                    <td className="small">{l.flag || ''}</td>
                    <td className="mono small">{(l.time || '').slice(0, 10)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
