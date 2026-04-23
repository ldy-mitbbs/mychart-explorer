import { useEffect, useState } from 'react';
import { api } from '../api';

export default function Summary() {
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const [patient, problems, meds, allergies, encounters, imms] = await Promise.all([
          api<any>('/api/patient'),
          api<any[]>('/api/problems'),
          api<any[]>('/api/medications'),
          api<any[]>('/api/allergies'),
          api<any[]>('/api/encounters?limit=5'),
          api<any[]>('/api/immunizations'),
        ]);
        const activeProblems = problems.filter(
          (p) => (p.PROBLEM_STATUS_C_NAME || p.status) === 'Active' || !p.RESOLVED_DATE,
        );
        const activeMeds = meds.filter((m) => !m.discontinue_reason);
        setData({ patient, problems, activeProblems, meds, activeMeds, allergies, encounters, imms });
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
            {p?.birthDate && `DOB ${p.birthDate}`}
            {p?.gender && ` · ${p.gender}`}
          </div>
          {p?.address && <div className="small" style={{ marginTop: 4 }}>{p.address}</div>}
          {p?.phones?.[0] && <div className="small muted">{p.phones[0]}</div>}
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

        <div className="card">
          <div className="muted small">Recent encounters</div>
          <div style={{ fontSize: 28, marginTop: 4 }}>{data.encounters.length}</div>
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

      <h2>Most recent encounters</h2>
      <div className="card">
        <table className="dtable">
          <thead><tr><th>Date</th><th>Provider</th><th>Department</th><th>Status</th></tr></thead>
          <tbody>
            {data.encounters.map((e: any) => (
              <tr key={e.csn}>
                <td className="mono small">{(e.CONTACT_DATE || '').slice(0, 10)}</td>
                <td>{e.provider || <span className="muted">—</span>}</td>
                <td>{e.department || <span className="muted">—</span>}</td>
                <td>{e.status && <span className="pill">{e.status}</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
