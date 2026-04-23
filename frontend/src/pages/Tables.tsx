import { useEffect, useMemo, useState } from 'react';
import { api } from '../api';

interface TableMeta {
  name: string;
  description: string;
  primary_key: string[];
  column_count: number;
  ingested: boolean;
}

interface TableData {
  name: string;
  columns: string[];
  rows: Record<string, any>[];
  total: number | null;
  limit: number;
  offset: number;
  description: string;
  column_meta?: { name: string; type?: string; description?: string }[];
  source: string;
}

export default function Tables() {
  const [tables, setTables] = useState<TableMeta[]>([]);
  const [filter, setFilter] = useState('');
  const [onlyIngested, setOnlyIngested] = useState(true);
  const [selected, setSelected] = useState<string | null>(null);
  const [data, setData] = useState<TableData | null>(null);
  const [search, setSearch] = useState('');
  const [offset, setOffset] = useState(0);
  const [sql, setSql] = useState('');
  const [sqlResult, setSqlResult] = useState<any>(null);
  const [sqlErr, setSqlErr] = useState<string | null>(null);

  useEffect(() => {
    api<{ tables: TableMeta[] }>('/api/tables').then((r) => setTables(r.tables));
  }, []);

  useEffect(() => {
    if (!selected) return setData(null);
    setOffset(0);
  }, [selected]);

  useEffect(() => {
    if (!selected) return;
    const params = new URLSearchParams({ limit: '100', offset: String(offset) });
    if (search) params.set('q', search);
    api<TableData>(`/api/tables/${selected}?${params}`).then(setData);
  }, [selected, offset, search]);

  const visible = useMemo(() => {
    const f = filter.toLowerCase();
    return tables
      .filter((t) => (!onlyIngested || t.ingested))
      .filter((t) => t.name.toLowerCase().includes(f) || t.description.toLowerCase().includes(f));
  }, [tables, filter, onlyIngested]);

  async function runSql() {
    setSqlErr(null);
    setSqlResult(null);
    try {
      const r = await api<any>('/api/sql', { method: 'POST', body: JSON.stringify({ sql, max_rows: 500 }) });
      setSqlResult(r);
    } catch (e) {
      setSqlErr((e as Error).message);
    }
  }

  return (
    <>
      <h1>Tables browser</h1>
      <div style={{ display: 'grid', gridTemplateColumns: '320px 1fr', gap: 16 }}>
        <div className="card" style={{ maxHeight: 'calc(100vh - 160px)', overflowY: 'auto' }}>
          <input
            placeholder="filter tables…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            style={{ width: '100%', marginBottom: 8 }}
          />
          <label className="small row" style={{ gap: 6, marginBottom: 8 }}>
            <input type="checkbox" checked={onlyIngested} onChange={(e) => setOnlyIngested(e.target.checked)} />
            only ingested ({tables.filter((t) => t.ingested).length})
          </label>
          <div className="small muted">{visible.length} tables</div>
          {visible.map((t) => (
            <div
              key={t.name}
              onClick={() => setSelected(t.name)}
              style={{
                padding: '6px 8px', cursor: 'pointer', borderRadius: 4,
                background: selected === t.name ? 'var(--panel-2)' : 'transparent',
                fontSize: 12,
              }}
            >
              <div>
                <span className="mono">{t.name}</span>{' '}
                {t.ingested && <span className="pill active" style={{ fontSize: 9 }}>ingested</span>}
              </div>
              {t.description && <div className="muted small">{t.description.slice(0, 80)}</div>}
            </div>
          ))}
        </div>

        <div>
          <div className="card">
            <h2 style={{ marginTop: 0 }}>SQL (SELECT only)</h2>
            <textarea
              rows={3}
              value={sql}
              onChange={(e) => setSql(e.target.value)}
              placeholder='e.g. SELECT MEDICATION_ID_MEDICATION_NAME, COUNT(*) n FROM ORDER_MED GROUP BY 1 ORDER BY n DESC'
              style={{ width: '100%' }}
            />
            <div className="row" style={{ marginTop: 8, justifyContent: 'space-between' }}>
              <span className="small muted">Auto-LIMITed to 500 rows. Read-only.</span>
              <button className="primary" onClick={runSql}>Run</button>
            </div>
            {sqlErr && <div className="small" style={{ color: 'var(--danger)', marginTop: 8 }}>{sqlErr}</div>}
            {sqlResult && (
              <div style={{ marginTop: 10, overflow: 'auto', maxHeight: 280 }}>
                <div className="small muted">{sqlResult.count} rows · <span className="mono">{sqlResult.sql}</span></div>
                {sqlResult.rows.length > 0 && (
                  <table className="dtable">
                    <thead><tr>{sqlResult.columns.map((c: string) => <th key={c}>{c}</th>)}</tr></thead>
                    <tbody>
                      {sqlResult.rows.map((r: any, i: number) => (
                        <tr key={i}>{sqlResult.columns.map((c: string) => <td key={c} className="small">{String(r[c] ?? '')}</td>)}</tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            )}
          </div>

          {data && (
            <div className="card">
              <h2 style={{ marginTop: 0 }}>
                {data.name}{' '}
                <span className="pill small">{data.source}</span>
              </h2>
              {data.description && <div className="small muted">{data.description}</div>}

              <div className="row" style={{ marginTop: 8, marginBottom: 8 }}>
                <input
                  placeholder="row filter (substring match across all columns)"
                  value={search}
                  onChange={(e) => { setSearch(e.target.value); setOffset(0); }}
                  style={{ width: 320 }}
                />
                <span className="grow" />
                <span className="small muted">
                  {data.total !== null && `${data.total} total · `}rows {data.offset + 1}–{data.offset + data.rows.length}
                </span>
                <button onClick={() => setOffset(Math.max(0, offset - 100))} disabled={offset === 0}>Prev</button>
                <button onClick={() => setOffset(offset + 100)} disabled={data.rows.length < 100}>Next</button>
              </div>

              <div style={{ overflow: 'auto', maxHeight: 460 }}>
                <table className="dtable">
                  <thead>
                    <tr>
                      {data.columns.map((c) => {
                        const meta = data.column_meta?.find((m) => m.name === c);
                        return (
                          <th key={c} title={meta?.description || ''}>
                            {c}
                            {meta?.type && <div className="muted" style={{ fontSize: 9 }}>{meta.type}</div>}
                          </th>
                        );
                      })}
                    </tr>
                  </thead>
                  <tbody>
                    {data.rows.map((r, i) => (
                      <tr key={i}>
                        {data.columns.map((c) => (
                          <td key={c} className="small">{String(r[c] ?? '')}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
