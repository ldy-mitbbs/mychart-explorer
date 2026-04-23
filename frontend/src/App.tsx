import { useEffect, useState } from 'react';
import type { Patient } from './api';
import { api } from './api';
import { ageFromDob } from './age';
import Summary from './pages/Summary';
import Problems from './pages/Problems';
import Allergies from './pages/Allergies';
import Medications from './pages/Medications';
import Labs from './pages/Labs';
import Vitals from './pages/Vitals';
import Encounters from './pages/Encounters';
import Imaging from './pages/Imaging';
import Notes from './pages/Notes';
import Messages from './pages/Messages';
import Immunizations from './pages/Immunizations';
import History from './pages/History';
import Tables from './pages/Tables';
import Chat from './pages/Chat';
import Setup from './pages/Setup';

type Page =
  | 'summary' | 'problems' | 'allergies' | 'medications' | 'labs' | 'vitals'
  | 'encounters' | 'imaging' | 'notes' | 'messages' | 'immunizations'
  | 'history' | 'tables' | 'chat' | 'setup';

const nav: { key: Page; label: string; section?: string }[] = [
  { key: 'summary', label: 'Summary', section: 'Overview' },
  { key: 'chat', label: 'Ask AI' },
  { key: 'problems', label: 'Problems', section: 'Clinical' },
  { key: 'medications', label: 'Medications' },
  { key: 'allergies', label: 'Allergies' },
  { key: 'labs', label: 'Labs' },
  { key: 'vitals', label: 'Vitals' },
  { key: 'immunizations', label: 'Immunizations' },
  { key: 'history', label: 'History' },
  { key: 'encounters', label: 'Encounters', section: 'Records' },
  { key: 'imaging', label: 'Imaging' },
  { key: 'notes', label: 'Notes' },
  { key: 'messages', label: 'Messages' },
  { key: 'tables', label: 'Tables browser', section: 'Advanced' },
  { key: 'setup', label: 'Setup' },
];

export default function App() {
  const [page, setPage] = useState<Page>('summary');
  const [patient, setPatient] = useState<Patient | null>(null);
  const [provider, setProvider] = useState<string>('ollama');
  const [dbReady, setDbReady] = useState<boolean | null>(null);

  const loadPatient = () => {
    api<Patient>('/api/patient').then(setPatient).catch(() => setPatient(null));
  };

  useEffect(() => {
    // Check ingestion status first; if DB isn't ready, send the user to Setup.
    api<{ db_exists: boolean }>('/api/admin/status')
      .then((s) => {
        setDbReady(s.db_exists);
        if (!s.db_exists) setPage('setup');
        else loadPatient();
      })
      .catch(() => setDbReady(false));
    api<{ llm_provider: string }>('/api/settings')
      .then((s) => setProvider(s.llm_provider))
      .catch(() => { /* ignore */ });
  }, []);

  const cloudActive = provider === 'openai' || provider === 'anthropic';

  const body = (() => {
    if (dbReady === false && page !== 'setup') {
      return <Setup onDone={() => { setDbReady(true); loadPatient(); }} />;
    }
    switch (page) {
      case 'summary': return <Summary />;
      case 'problems': return <Problems />;
      case 'allergies': return <Allergies />;
      case 'medications': return <Medications />;
      case 'labs': return <Labs />;
      case 'vitals': return <Vitals />;
      case 'encounters': return <Encounters />;
      case 'imaging': return <Imaging />;
      case 'notes': return <Notes />;
      case 'messages': return <Messages />;
      case 'immunizations': return <Immunizations />;
      case 'history': return <History />;
      case 'tables': return <Tables />;
      case 'chat': return <Chat onProviderChange={setProvider} />;
      case 'setup': return <Setup onDone={() => { setDbReady(true); loadPatient(); }} />;
    }
  })();

  return (
    <div className="app">
      <header className="topbar">
        <div>
          <span className="brand">MyChart Explorer</span>
          {patient && (
            <span className="meta" style={{ marginLeft: 16 }}>
              <b>{patient.name}</b>
              {ageFromDob(patient.birthDate) !== null && ` · Age ${ageFromDob(patient.birthDate)}`}
              {patient.gender && ` · ${patient.gender}`}
              {patient.mrn && ` · MRN ${patient.mrn}`}
            </span>
          )}
        </div>
        <div className="small muted">
          LLM: <b style={{ color: 'var(--text)' }}>{provider}</b>
          {cloudActive && <span className="warn">PHI sent to {provider}</span>}
        </div>
      </header>

      <nav className="sidebar">
        {nav.map((n) => (
          <div key={n.key}>
            {n.section && <div className="section">{n.section}</div>}
            <button
              className={page === n.key ? 'active' : ''}
              onClick={() => setPage(n.key)}
            >
              {n.label}
            </button>
          </div>
        ))}
      </nav>

      <main className="page">{body}</main>
    </div>
  );
}
