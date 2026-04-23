import { useEffect, useRef, useState } from 'react';
import { api } from '../api';
import { useT } from '../i18n';

interface SourceInfo {
  source: string;
  exists: boolean;
  has_ehi_tables?: boolean;
  has_ehi_schema?: boolean;
  has_fhir?: boolean;
  missing?: string[];
  tsv_count?: number;
  schema_htm_count?: number;
  fhir_file_count?: number;
}

interface Status {
  db_path: string;
  db_exists: boolean;
  db_size_bytes?: number;
  db_modified?: string;
  source_dir: string;
  source_env_override: boolean;
  ingested_table_count?: number;
  last_ingest?: string;
  source_info?: SourceInfo;
}

interface LogEvent {
  phase: string;
  status: string;
  message: string;
}

function fmtBytes(n: number | undefined): string {
  if (!n) return '';
  if (n > 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`;
  if (n > 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${n} B`;
}

export default function Setup({ onDone }: { onDone?: () => void }) {
  const { t } = useT();
  const [status, setStatus] = useState<Status | null>(null);
  const [path, setPath] = useState('');
  const [info, setInfo] = useState<SourceInfo | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [log, setLog] = useState<LogEvent[]>([]);
  const [running, setRunning] = useState(false);
  const logRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const refresh = () => {
    api<Status>('/api/admin/status')
      .then((s) => {
        setStatus(s);
        if (s.source_dir && !path) setPath(s.source_dir);
        if (s.source_info) setInfo(s.source_info);
      })
      .catch(() => { /* ignore */ });
  };

  useEffect(() => {
    refresh();
  }, []);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [log]);

  const validate = async (override?: string) => {
    const target = override ?? path;
    setError('');
    setBusy(true);
    try {
      const r = await api<SourceInfo>(
        `/api/admin/validate?path=${encodeURIComponent(target)}`,
      );
      setInfo(r);
    } catch (e: any) {
      setError(e.message || t('setup.err.validation'));
      setInfo(null);
    } finally {
      setBusy(false);
    }
  };

  const browse = async () => {
    setError('');
    setBusy(true);
    try {
      const r = await api<{ path: string }>('/api/admin/pick-folder', {
        method: 'POST',
      });
      if (r.path) {
        setPath(r.path);
        await validate(r.path);
      }
    } catch (e: any) {
      setError(e.message || t('setup.err.pickFolder'));
    } finally {
      setBusy(false);
    }
  };

  const saveSource = async () => {
    setError('');
    setBusy(true);
    try {
      const r = await api<{ source_info: SourceInfo }>('/api/admin/source', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path }),
      });
      setInfo(r.source_info);
      refresh();
    } catch (e: any) {
      setError(e.message || t('setup.err.save'));
    } finally {
      setBusy(false);
    }
  };

  const runIngest = async () => {
    setError('');
    setLog([]);
    setRunning(true);
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    try {
      const res = await fetch('/api/admin/ingest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source: path }),
        signal: ctrl.signal,
      });
      if (!res.ok || !res.body) {
        const txt = await res.text();
        throw new Error(txt || `HTTP ${res.status}`);
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = '';
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const chunks = buf.split('\n\n');
        buf = chunks.pop() || '';
        for (const chunk of chunks) {
          for (const line of chunk.split('\n')) {
            if (!line.startsWith('data:')) continue;
            try {
              const evt = JSON.parse(line.slice(5).trim()) as LogEvent;
              setLog((L) => [...L, evt]);
            } catch { /* ignore */ }
          }
        }
      }
    } catch (e: any) {
      if (e.name !== 'AbortError') setError(e.message || t('setup.err.ingest'));
    } finally {
      setRunning(false);
      abortRef.current = null;
      refresh();
      onDone?.();
    }
  };

  const ready = info && info.exists && (info.missing?.length ?? 1) === 0;

  return (
    <div style={{ maxWidth: 860 }}>
      <h1>{t('setup.title')}</h1>

      <div className="card">
        <h3>{t('setup.state.title')}</h3>
        {!status && <div className="muted">{t('setup.state.loading')}</div>}
        {status && (
          <div className="small">
            <div>
              <b>{t('setup.state.database')}</b>{' '}
              {status.db_exists ? (
                <>
                  <span className="pill active">{t('setup.state.ingested')}</span>{' '}
                  {t('setup.state.tableCount', { n: status.ingested_table_count ?? 0 })} ·{' '}
                  {fmtBytes(status.db_size_bytes)}
                  {status.db_modified && ` · ${t('setup.state.updated', { when: status.db_modified })}`}
                </>
              ) : (
                <span className="pill warn">{t('setup.state.notIngested')}</span>
              )}
            </div>
            <div style={{ marginTop: 4 }}>
              <b>{t('setup.state.sourceFolder')}</b>{' '}
              {status.source_dir ? (
                <code>{status.source_dir}</code>
              ) : (
                <span className="muted">{t('setup.state.notConfigured')}</span>
              )}
              {status.source_env_override && (
                <span className="pill" style={{ marginLeft: 8 }}>
                  {t('setup.state.envOverride')}
                </span>
              )}
            </div>
            {status.last_ingest && (
              <div style={{ marginTop: 4 }} className="muted">
                {t('setup.state.lastIngest', { when: status.last_ingest })}
              </div>
            )}
          </div>
        )}
      </div>

      <div className="card">
        <h3>{t('setup.step1.title')}</h3>
        <p className="small muted">
          {t('setup.step1.help', {
            ehi: 'EHITables/',
            schema: 'EHITables Schema/',
            fhir: 'FHIR/',
          })}
        </p>
        <div style={{ display: 'flex', gap: 8 }}>
          <input
            type="text"
            value={path}
            onChange={(e) => setPath(e.target.value)}
            placeholder={t('setup.path.placeholder')}
            style={{
              flex: 1,
              padding: 8,
              background: 'var(--bg-2)',
              color: 'var(--text)',
              border: '1px solid var(--border)',
              borderRadius: 6,
            }}
            disabled={busy || running}
          />
          <button
            className="btn"
            onClick={browse}
            disabled={busy || running}
            title={t('setup.btn.browseTitle')}
          >
            {t('setup.btn.browse')}
          </button>
          <button
            className="btn"
            onClick={() => validate()}
            disabled={!path || busy || running}
          >
            {t('setup.btn.validate')}
          </button>
          <button
            className="btn"
            onClick={saveSource}
            disabled={!path || !info?.exists || busy || running}
          >
            {t('setup.btn.save')}
          </button>
        </div>
        {info && (
          <div className="small" style={{ marginTop: 12 }}>
            {!info.exists && (
              <div>
                <span className="pill bad">{t('setup.err.notFound')}</span>
              </div>
            )}
            {info.exists && (
              <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
                <li>
                  {info.has_ehi_tables ? '✓' : '✗'} {t('setup.info.ehi', { n: info.tsv_count ?? 0 })}
                </li>
                <li>
                  {info.has_ehi_schema ? '✓' : '✗'} {t('setup.info.schema', { n: info.schema_htm_count ?? 0 })}
                </li>
                <li>
                  {info.has_fhir ? '✓' : '✗'} {t('setup.info.fhir', { n: info.fhir_file_count ?? 0 })}
                </li>
                {info.missing && info.missing.length > 0 && (
                  <li className="warn-text">
                    {t('setup.info.missing', { list: info.missing.join(', ') })}
                  </li>
                )}
              </ul>
            )}
          </div>
        )}
      </div>

      <div className="card">
        <h3>{t('setup.step2.title')}</h3>
        <p className="small muted">
          {t('setup.step2.help')}
        </p>
        <button
          className="btn"
          onClick={runIngest}
          disabled={!ready || running}
        >
          {running ? t('setup.btn.running') : status?.db_exists ? t('setup.btn.reingest') : t('setup.btn.start')}
        </button>
        {error && (
          <div className="warn-text" style={{ marginTop: 8 }}>
            {error}
          </div>
        )}
        {log.length > 0 && (
          <div
            ref={logRef}
            style={{
              marginTop: 12,
              maxHeight: 300,
              overflow: 'auto',
              background: 'var(--bg-2)',
              border: '1px solid var(--border)',
              borderRadius: 6,
              padding: 10,
              fontFamily: 'ui-monospace, monospace',
              fontSize: 12,
            }}
          >
            {log.map((e, i) => (
              <div key={i}>
                <span
                  className={
                    e.status === 'error'
                      ? 'warn-text'
                      : e.status === 'end' || e.status === 'ok'
                        ? ''
                        : 'muted'
                  }
                >
                  [{e.phase}] {e.status}
                </span>{' '}
                {e.message}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
