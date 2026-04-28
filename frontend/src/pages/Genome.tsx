import { useEffect, useState } from 'react';
import { api } from '../api';
import { useT } from '../i18n';

interface Annotation {
  gene_symbol: string | null;
  clinical_significance: string | null;
  phenotype: string | null;
  review_status: string | null;
  variation_id: string | null;
  variant_type?: string | null;
}

interface SnpResult {
  rsid: string;
  found: boolean;
  genotype?: string;
  chromosome?: string;
  position?: number;
  annotations?: Annotation[];
  note?: string;
}

interface NotableVariant {
  rsid: string;
  genotype: string;
  gene_symbol: string | null;
  clinical_significance: string | null;
  phenotype: string | null;
  review_status: string | null;
  variation_id: string | null;
}

interface AncestryPop {
  ancestry: string;
  length_bp: number;
  percent: number;
}

interface GenomeStatus {
  has_genome: boolean;
  has_clinvar: boolean;
  meta: Record<string, string>;
  counts: Record<string, number>;
}

function fmtNum(n: number | undefined): string {
  if (n === undefined || n === null) return '';
  return n.toLocaleString();
}

function severityClass(sig: string | null | undefined): string {
  if (!sig) return '';
  const s = sig.toLowerCase();
  if (s.includes('pathogenic') && !s.includes('likely') && !s.includes('conflict')) return 'bad';
  if (s.includes('likely pathogenic')) return 'warn';
  if (s.includes('drug response')) return 'active';
  if (s.includes('risk factor')) return 'warn';
  if (s.includes('protective')) return 'active';
  return '';
}

export default function Genome() {
  const { t } = useT();
  const [status, setStatus] = useState<GenomeStatus | null>(null);
  const [tab, setTab] = useState<'notable' | 'ancestry' | 'lookup' | 'gene'>('notable');

  const [notable, setNotable] = useState<NotableVariant[]>([]);
  const [notableLoading, setNotableLoading] = useState(false);
  const [notableErr, setNotableErr] = useState('');

  const [pops, setPops] = useState<AncestryPop[]>([]);
  const [ancErr, setAncErr] = useState('');

  const [rsidInput, setRsidInput] = useState('');
  const [snp, setSnp] = useState<SnpResult | null>(null);
  const [snpErr, setSnpErr] = useState('');
  const [snpLoading, setSnpLoading] = useState(false);

  const [geneInput, setGeneInput] = useState('');
  const [geneRows, setGeneRows] = useState<NotableVariant[]>([]);
  const [geneErr, setGeneErr] = useState('');
  const [geneNote, setGeneNote] = useState('');
  const [geneLoading, setGeneLoading] = useState(false);

  useEffect(() => {
    api<GenomeStatus>('/api/genome/status')
      .then(setStatus)
      .catch(() => setStatus(null));
  }, []);

  useEffect(() => {
    if (tab === 'notable' && status?.has_clinvar && notable.length === 0 && !notableLoading) {
      setNotableLoading(true);
      api<{ variants: NotableVariant[] }>('/api/genome/notable?limit=200')
        .then((r) => setNotable(r.variants || []))
        .catch((e: any) => setNotableErr(e.message || 'failed'))
        .finally(() => setNotableLoading(false));
    }
    if (tab === 'ancestry' && status?.has_genome && pops.length === 0) {
      api<{ populations: AncestryPop[] }>('/api/genome/ancestry')
        .then((r) => setPops(r.populations || []))
        .catch((e: any) => setAncErr(e.message || 'failed'));
    }
  }, [tab, status]);

  const lookupSnp = async () => {
    setSnpErr('');
    setSnp(null);
    if (!rsidInput.trim()) return;
    setSnpLoading(true);
    try {
      const r = await api<SnpResult>(
        `/api/genome/snp/${encodeURIComponent(rsidInput.trim())}`,
      );
      setSnp(r);
    } catch (e: any) {
      setSnpErr(e.message || 'lookup failed');
    } finally {
      setSnpLoading(false);
    }
  };

  const lookupGene = async () => {
    setGeneErr('');
    setGeneNote('');
    setGeneRows([]);
    if (!geneInput.trim()) return;
    setGeneLoading(true);
    try {
      const r = await api<{ variants: NotableVariant[]; note?: string }>(
        `/api/genome/gene/${encodeURIComponent(geneInput.trim())}?limit=200`,
      );
      setGeneRows(r.variants || []);
      if (r.note) setGeneNote(r.note);
    } catch (e: any) {
      setGeneErr(e.message || 'lookup failed');
    } finally {
      setGeneLoading(false);
    }
  };

  if (!status) {
    return (
      <div>
        <h1>{t('genome.title')}</h1>
        <div className="muted">{t('common.loading')}</div>
      </div>
    );
  }

  if (!status.has_genome) {
    return (
      <div>
        <h1>{t('genome.title')}</h1>
        <div className="card">
          <p>{t('genome.notIngested')}</p>
        </div>
      </div>
    );
  }

  return (
    <div>
      <h1>{t('genome.title')}</h1>

      <div className="card small">
        <div className="row" style={{ gap: 16, flexWrap: 'wrap' }}>
          <div>
            <b>{t('genome.meta.variants')}:</b>{' '}
            {fmtNum(status.counts.variants)}
          </div>
          {status.counts.ancestry_segments !== undefined && (
            <div>
              <b>{t('genome.meta.ancestry')}:</b>{' '}
              {fmtNum(status.counts.ancestry_segments)} {t('genome.meta.segments')}
            </div>
          )}
          <div>
            <b>{t('genome.meta.clinvar')}:</b>{' '}
            {status.has_clinvar ? fmtNum(status.counts.clinvar) : (
              <span className="muted">{t('genome.meta.notLoaded')}</span>
            )}
          </div>
          {status.meta.genome_build && (
            <div>
              <b>{t('genome.meta.build')}:</b> {status.meta.genome_build}
            </div>
          )}
          {status.meta.ingested_at && (
            <div className="muted">
              {t('genome.meta.ingested', { when: status.meta.ingested_at })}
            </div>
          )}
        </div>
        <div className="small muted" style={{ marginTop: 8 }}>
          {t('genome.disclaimer')}
        </div>
      </div>

      <div className="row" style={{ gap: 8, marginBottom: 12, marginTop: 12 }}>
        <button className={tab === 'notable' ? 'btn active' : 'btn'} onClick={() => setTab('notable')}>
          {t('genome.tab.notable')}
        </button>
        <button className={tab === 'lookup' ? 'btn active' : 'btn'} onClick={() => setTab('lookup')}>
          {t('genome.tab.lookup')}
        </button>
        <button className={tab === 'gene' ? 'btn active' : 'btn'} onClick={() => setTab('gene')}>
          {t('genome.tab.gene')}
        </button>
        <button className={tab === 'ancestry' ? 'btn active' : 'btn'} onClick={() => setTab('ancestry')}>
          {t('genome.tab.ancestry')}
        </button>
      </div>

      {tab === 'notable' && (
        <div className="card">
          <h3>{t('genome.notable.title')}</h3>
          {!status.has_clinvar && (
            <div className="warn-text small">{t('genome.notable.noClinvar')}</div>
          )}
          {notableErr && <div className="warn-text">{notableErr}</div>}
          {notableLoading && <div className="muted">{t('common.loading')}</div>}
          {!notableLoading && notable.length === 0 && status.has_clinvar && (
            <div className="muted">{t('genome.notable.empty')}</div>
          )}
          {notable.length > 0 && (
            <table>
              <thead>
                <tr>
                  <th>{t('genome.col.rsid')}</th>
                  <th>{t('genome.col.gene')}</th>
                  <th>{t('genome.col.genotype')}</th>
                  <th>{t('genome.col.significance')}</th>
                  <th>{t('genome.col.phenotype')}</th>
                  <th>{t('genome.col.reviewStatus')}</th>
                </tr>
              </thead>
              <tbody>
                {notable.map((v, i) => (
                  <tr key={i}>
                    <td><code>{v.rsid}</code></td>
                    <td>{v.gene_symbol || ''}</td>
                    <td><code>{v.genotype}</code></td>
                    <td>
                      <span className={`pill ${severityClass(v.clinical_significance)}`}>
                        {v.clinical_significance}
                      </span>
                    </td>
                    <td className="small">{v.phenotype}</td>
                    <td className="small muted">{v.review_status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {tab === 'lookup' && (
        <div className="card">
          <h3>{t('genome.lookup.title')}</h3>
          <div className="row" style={{ gap: 8 }}>
            <input
              type="text"
              value={rsidInput}
              onChange={(e) => setRsidInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') lookupSnp(); }}
              placeholder={t('genome.lookup.placeholder')}
              style={{
                flex: 1, padding: 8,
                background: 'var(--bg-2)', color: 'var(--text)',
                border: '1px solid var(--border)', borderRadius: 6,
              }}
            />
            <button className="btn" onClick={lookupSnp} disabled={snpLoading}>
              {t('genome.lookup.btn')}
            </button>
          </div>
          {snpErr && <div className="warn-text" style={{ marginTop: 8 }}>{snpErr}</div>}
          {snp && (
            <div style={{ marginTop: 12 }}>
              {!snp.found ? (
                <div className="muted">
                  {snp.note || t('genome.lookup.notFound', { rsid: snp.rsid })}
                </div>
              ) : (
                <div>
                  <div className="small">
                    <b>{snp.rsid}</b> · chr{snp.chromosome}:{snp.position} ·{' '}
                    {t('genome.col.genotype')}: <code>{snp.genotype}</code>
                  </div>
                  {snp.annotations && snp.annotations.length > 0 ? (
                    <table style={{ marginTop: 8 }}>
                      <thead>
                        <tr>
                          <th>{t('genome.col.gene')}</th>
                          <th>{t('genome.col.significance')}</th>
                          <th>{t('genome.col.phenotype')}</th>
                          <th>{t('genome.col.reviewStatus')}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {snp.annotations.map((a, i) => (
                          <tr key={i}>
                            <td>{a.gene_symbol}</td>
                            <td>
                              <span className={`pill ${severityClass(a.clinical_significance)}`}>
                                {a.clinical_significance}
                              </span>
                            </td>
                            <td className="small">{a.phenotype}</td>
                            <td className="small muted">{a.review_status}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  ) : (
                    <div className="muted small" style={{ marginTop: 8 }}>
                      {t('genome.lookup.noAnnotations')}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {tab === 'gene' && (
        <div className="card">
          <h3>{t('genome.gene.title')}</h3>
          <div className="row" style={{ gap: 8 }}>
            <input
              type="text"
              value={geneInput}
              onChange={(e) => setGeneInput(e.target.value.toUpperCase())}
              onKeyDown={(e) => { if (e.key === 'Enter') lookupGene(); }}
              placeholder={t('genome.gene.placeholder')}
              style={{
                flex: 1, padding: 8,
                background: 'var(--bg-2)', color: 'var(--text)',
                border: '1px solid var(--border)', borderRadius: 6,
              }}
            />
            <button className="btn" onClick={lookupGene} disabled={geneLoading}>
              {t('genome.gene.btn')}
            </button>
          </div>
          {geneErr && <div className="warn-text" style={{ marginTop: 8 }}>{geneErr}</div>}
          {geneNote && <div className="muted small" style={{ marginTop: 8 }}>{geneNote}</div>}
          {geneRows.length > 0 && (
            <table style={{ marginTop: 12 }}>
              <thead>
                <tr>
                  <th>{t('genome.col.rsid')}</th>
                  <th>{t('genome.col.genotype')}</th>
                  <th>{t('genome.col.significance')}</th>
                  <th>{t('genome.col.phenotype')}</th>
                  <th>{t('genome.col.reviewStatus')}</th>
                </tr>
              </thead>
              <tbody>
                {geneRows.map((v, i) => (
                  <tr key={i}>
                    <td><code>{v.rsid}</code></td>
                    <td><code>{v.genotype}</code></td>
                    <td>
                      <span className={`pill ${severityClass(v.clinical_significance)}`}>
                        {v.clinical_significance}
                      </span>
                    </td>
                    <td className="small">{v.phenotype}</td>
                    <td className="small muted">{v.review_status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {tab === 'ancestry' && (
        <div className="card">
          <h3>{t('genome.ancestry.title')}</h3>
          {ancErr && <div className="warn-text">{ancErr}</div>}
          {pops.length === 0 && !ancErr && (
            <div className="muted">{t('genome.ancestry.empty')}</div>
          )}
          {pops.length > 0 && (
            <table>
              <thead>
                <tr>
                  <th>{t('genome.col.population')}</th>
                  <th>{t('genome.col.percent')}</th>
                  <th>{t('genome.col.lengthBp')}</th>
                </tr>
              </thead>
              <tbody>
                {pops.map((p, i) => (
                  <tr key={i}>
                    <td>{p.ancestry}</td>
                    <td>
                      <div className="row" style={{ gap: 8, alignItems: 'center' }}>
                        <div
                          style={{
                            background: 'var(--accent)',
                            height: 10,
                            width: `${Math.min(100, p.percent * 2)}%`,
                            minWidth: 2,
                            borderRadius: 4,
                          }}
                        />
                        <span>{p.percent.toFixed(2)}%</span>
                      </div>
                    </td>
                    <td className="small muted">{fmtNum(p.length_bp)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}
