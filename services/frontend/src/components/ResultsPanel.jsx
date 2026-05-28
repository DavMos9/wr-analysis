import { useEffect, useState } from 'react'
import { listResults, getResultRecords, getResultSummary, downloadUrl } from '../api/client'

function Badge({ children, color = 'gray' }) {
  const colors = {
    gray:  'bg-gray-100 text-gray-700',
    blue:  'bg-blue-100 text-blue-700',
    green: 'bg-green-100 text-green-700',
  }
  return (
    <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${colors[color]}`}>
      {children}
    </span>
  )
}

function sentimentInfo(value) {
  // sentiment è un float -1.0 → +1.0, non una stringa
  if (value === null || value === undefined) return null
  if (value >  0.1) return { label: 'positivo', color: 'text-green-600' }
  if (value < -0.1) return { label: 'negativo',  color: 'text-red-500'  }
  return              { label: 'neutro',    color: 'text-yellow-500' }
}

function RecordRow({ record }) {
  const [open, setOpen] = useState(false)
  const sent = sentimentInfo(record.sentiment)

  return (
    <div className="border-b border-gray-100 last:border-0">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full text-left px-4 py-3 hover:bg-gray-50 transition-colors"
      >
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="text-sm font-medium text-gray-800 truncate">
              {record.title || '(senza titolo)'}
            </p>
            <div className="flex items-center gap-2 mt-0.5 flex-wrap">
              <Badge>{record.source}</Badge>
              {record.date && <span className="text-xs text-gray-400">{record.date}</span>}
              {sent && (
                <span className={`text-xs font-medium ${sent.color}`}>
                  {sent.label} ({record.sentiment > 0 ? '+' : ''}{record.sentiment.toFixed(3)})
                </span>
              )}
            </div>
          </div>
          <span className="text-gray-300 text-xs shrink-0">{open ? '▲' : '▼'}</span>
        </div>
      </button>

      {open && (
        <div className="px-4 pb-3 space-y-2">
          {record.text && (
            <p className="text-sm text-gray-600 leading-relaxed line-clamp-4">{record.text}</p>
          )}
          {record.url && (
            <a
              href={record.url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-blue-600 hover:underline break-all"
            >
              {record.url}
            </a>
          )}
        </div>
      )}
    </div>
  )
}

function ResultDetail({ filename, onClose }) {
  const [records, setRecords]       = useState([])
  const [summary, setSummary]       = useState(null)
  const [loading, setLoading]       = useState(true)
  const [fetchError, setFetchError] = useState(null)
  const [search, setSearch]         = useState('')
  const [srcFilter, setSrcFilter]   = useState('all')

  useEffect(() => {
    setRecords([])
    setSummary(null)
    setFetchError(null)
    setLoading(true)
    Promise.all([
      getResultRecords(filename),
      getResultSummary(filename).catch(() => null),
    ]).then(([recs, sum]) => {
      setRecords(recs)
      setSummary(sum)
    }).catch(err => {
      setFetchError(err.message || 'Errore nel caricamento dei record.')
    }).finally(() => setLoading(false))
  }, [filename])

  const sources = [...new Set(records.map(r => r.source))].sort()
  const filtered = records.filter(r => {
    const matchSrc  = srcFilter === 'all' || r.source === srcFilter
    const matchText = !search ||
      (r.title || '').toLowerCase().includes(search.toLowerCase()) ||
      (r.text  || '').toLowerCase().includes(search.toLowerCase())
    return matchSrc && matchText
  })

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-gray-100">
        <div>
          <h3 className="font-semibold text-gray-900">{filename}</h3>
          {summary && (
            <p className="text-xs text-gray-400">
              {summary.target} · {summary.topic} · {records.length} record
            </p>
          )}
        </div>
        <div className="flex items-center gap-2">
          <a href={downloadUrl(filename, 'csv')} download
             className="text-xs px-3 py-1.5 rounded-lg bg-gray-100 hover:bg-gray-200 text-gray-700 transition-colors">
            ↓ CSV
          </a>
          <a href={downloadUrl(filename, 'json')} download
             className="text-xs px-3 py-1.5 rounded-lg bg-gray-100 hover:bg-gray-200 text-gray-700 transition-colors">
            ↓ JSON
          </a>
          <button onClick={onClose}
                  className="text-gray-400 hover:text-gray-600 transition-colors ml-1">
            ✕
          </button>
        </div>
      </div>

      {/* Filtri */}
      <div className="flex gap-2 px-4 py-2 border-b border-gray-100">
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Cerca nel testo..."
          className="flex-1 text-sm border border-gray-200 rounded-lg px-3 py-1.5 focus:ring-2 focus:ring-blue-500 outline-none"
        />
        <select
          value={srcFilter}
          onChange={e => setSrcFilter(e.target.value)}
          className="text-sm border border-gray-200 rounded-lg px-3 py-1.5 bg-white focus:ring-2 focus:ring-blue-500 outline-none"
        >
          <option value="all">Tutte le fonti</option>
          {sources.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>
      <p className="text-xs text-gray-400 px-4 py-1">{filtered.length} record</p>

      {/* Record list */}
      <div className="overflow-y-auto flex-1">
        {loading ? (
          <div className="p-8 text-center text-gray-400 text-sm">Caricamento...</div>
        ) : fetchError ? (
          <div className="p-8 text-center text-red-500 text-sm">{fetchError}</div>
        ) : filtered.length === 0 ? (
          <div className="p-8 text-center text-gray-400 text-sm">Nessun risultato.</div>
        ) : (
          // key stabile su url (unico per record) — evita che React perda lo stato "aperto"
          filtered.map((r, i) => <RecordRow key={r.url || r.title || i} record={r} />)
        )}
      </div>
    </div>
  )
}

export default function ResultsPanel() {
  const [results, setResults]     = useState([])
  const [loading, setLoading]     = useState(true)
  const [loadError, setLoadError] = useState('')
  const [selected, setSelected]   = useState(null)

  const reload = () => {
    setLoading(true)
    setLoadError('')
    listResults()
      .then(setResults)
      .catch(err => setLoadError(err.message || 'Impossibile caricare i risultati.'))
      .finally(() => setLoading(false))
  }

  useEffect(reload, [])

  return (
    <div className={`grid gap-6 ${selected ? 'grid-cols-1 lg:grid-cols-2' : 'grid-cols-1'}`}
         style={{ minHeight: '60vh' }}>

      {/* ── Lista risultati ── */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200">
        <div className="flex items-center justify-between p-4 border-b border-gray-100">
          <h2 className="text-lg font-semibold text-gray-900">Analisi salvate</h2>
          <button onClick={reload}
                  className="text-sm text-blue-600 hover:text-blue-700 transition-colors">
            ↻ Aggiorna
          </button>
        </div>

        {loading ? (
          <div className="p-8 text-center text-gray-400 text-sm">Caricamento...</div>
        ) : loadError ? (
          <div className="p-8 text-center text-red-500 text-sm">{loadError}</div>
        ) : results.length === 0 ? (
          <div className="p-8 text-center">
            <p className="text-gray-400 text-sm">Nessuna analisi trovata.</p>
            <p className="text-gray-300 text-xs mt-1">
              Avvia una pipeline dalla scheda "Run".
            </p>
          </div>
        ) : (
          <div className="divide-y divide-gray-100">
            {results.map(r => (
              <button
                key={r.filename}
                onClick={() => setSelected(selected === r.filename ? null : r.filename)}
                className={`w-full text-left px-4 py-3 transition-colors
                  ${selected === r.filename
                    ? 'bg-blue-50 border-l-2 border-blue-500'
                    : 'hover:bg-gray-50'}`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className="text-sm font-semibold text-gray-800">
                      {r.target} · <span className="font-normal text-gray-600">{r.topic}</span>
                    </p>
                    <div className="flex flex-wrap gap-1 mt-1">
                      <Badge color="blue">{r.n_records} record</Badge>
                      {r.last_run && (
                        <span className="text-xs text-gray-400">{r.last_run}</span>
                      )}
                    </div>
                  </div>
                  <div className="flex gap-1 shrink-0">
                    <a href={downloadUrl(r.filename, 'csv')} download
                       onClick={e => e.stopPropagation()}
                       className="text-xs px-2 py-1 rounded bg-gray-100 hover:bg-gray-200 text-gray-600">
                      CSV
                    </a>
                    <a href={downloadUrl(r.filename, 'json')} download
                       onClick={e => e.stopPropagation()}
                       className="text-xs px-2 py-1 rounded bg-gray-100 hover:bg-gray-200 text-gray-600">
                      JSON
                    </a>
                  </div>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* ── Dettaglio ── */}
      {selected && (
        <ResultDetail
          filename={selected}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  )
}
