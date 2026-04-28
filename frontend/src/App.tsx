import { useEffect, useState } from 'react';
import type { Patient } from './api';
import { api } from './api';
import { ageFromDob } from './age';
import { useT, type TKey } from './i18n';
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
import Genome from './pages/Genome';
import Setup from './pages/Setup';

type Page =
  | 'summary' | 'problems' | 'allergies' | 'medications' | 'labs' | 'vitals'
  | 'encounters' | 'imaging' | 'notes' | 'messages' | 'immunizations'
  | 'history' | 'tables' | 'chat' | 'genome' | 'setup';

const nav: { key: Page; labelKey: TKey; sectionKey?: TKey }[] = [
  { key: 'summary', labelKey: 'nav.summary', sectionKey: 'nav.section.overview' },
  { key: 'chat', labelKey: 'nav.chat' },
  { key: 'problems', labelKey: 'nav.problems', sectionKey: 'nav.section.clinical' },
  { key: 'medications', labelKey: 'nav.medications' },
  { key: 'allergies', labelKey: 'nav.allergies' },
  { key: 'labs', labelKey: 'nav.labs' },
  { key: 'vitals', labelKey: 'nav.vitals' },
  { key: 'immunizations', labelKey: 'nav.immunizations' },
  { key: 'history', labelKey: 'nav.history' },
  { key: 'encounters', labelKey: 'nav.encounters', sectionKey: 'nav.section.records' },
  { key: 'imaging', labelKey: 'nav.imaging' },
  { key: 'notes', labelKey: 'nav.notes' },
  { key: 'messages', labelKey: 'nav.messages' },
  { key: 'genome', labelKey: 'nav.genome', sectionKey: 'nav.section.genomics' },
  { key: 'tables', labelKey: 'nav.tables', sectionKey: 'nav.section.advanced' },
  { key: 'setup', labelKey: 'nav.setup' },
];

export default function App() {
  const { t, lang, setLang } = useT();
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
      case 'genome': return <Genome />;
      case 'setup': return <Setup onDone={() => { setDbReady(true); loadPatient(); }} />;
    }
  })();

  return (
    <div className="app">
      <header className="topbar">
        <div>
          <span className="brand">{t('app.brand')}</span>
          {patient && (
            <span className="meta" style={{ marginLeft: 16 }}>
              <b>{patient.name}</b>
              {ageFromDob(patient.birthDate) !== null && ` · ${t('app.age', { age: ageFromDob(patient.birthDate) as number })}`}
              {patient.gender && ` · ${patient.gender}`}
              {patient.mrn && ` · ${t('app.mrn', { mrn: patient.mrn })}`}
            </span>
          )}
        </div>
        <div className="row small muted" style={{ gap: 12 }}>
          <label className="row" style={{ gap: 4, alignItems: 'center' }}>
            <span>{t('app.language')}:</span>
            <select
              value={lang}
              onChange={(e) => setLang(e.target.value as 'en' | 'zh')}
              style={{ fontSize: 12 }}
            >
              <option value="en">{t('app.lang.en')}</option>
              <option value="zh">{t('app.lang.zh')}</option>
            </select>
          </label>
          <span>
            {t('app.llm')}: <b style={{ color: 'var(--text)' }}>{provider}</b>
            {cloudActive && <span className="warn"> {t('app.phiWarn', { provider })}</span>}
          </span>
        </div>
      </header>

      <nav className="sidebar">
        {nav.map((n) => (
          <div key={n.key}>
            {n.sectionKey && <div className="section">{t(n.sectionKey)}</div>}
            <button
              className={page === n.key ? 'active' : ''}
              onClick={() => setPage(n.key)}
            >
              {t(n.labelKey)}
            </button>
          </div>
        ))}
      </nav>

      <main className="page">{body}</main>
    </div>
  );
}
