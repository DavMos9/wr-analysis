import { useState } from 'react'
import { startRun, getRunStatus } from '../api/client'
import { usePolling } from '../hooks/usePolling'
import SourceSelector from './SourceSelector'

const today = () => new Date().toISOString().slice(0, 10)
const daysAgo = (n) => {
  const d = new Date()
  d.setDate(d.getDate() - n)
  return d.toISOString().slice(0, 10)
}

const STATUS_STYLES = {
  queued:  'bg-yellow-100 text-yellow-800 border-yellow-200',
  running: 'bg-blue-100 text-blue-800 border-blue-200',
  done:    'bg-green-100 text-green-800 border-green-200',
  failed:  'bg-red-100 text-red-800 border-red-200',
}

const STATUS_ICONS = {
  queued:  '⏳',
  running: '⚙️',
  done:    '✅',
  failed:  '❌',
}

function JobCard({ job }) {
  const style = STATUS_STYLES[job.status] || STATUS_STYLES.queued
  const icon  = STATUS_ICONS[job.status]  || '⏳'

  return (
    <div className={`rounded-lg border p-4 ${style}`}>
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="font-semibold text-sm">
            {icon} {job.target} / {job.topic}
          </p>
          <p className="text-xs mt-0.5 opacity-75">{job.progress}</p>
        </div>
        <span className="text-xs font-mono opacity-60 shrink-0">{job.status}</span>
      </div>

      {job.status === 'done' && (
        <div className="mt-2 pt-2 border-t border-current border-opacity-20 text-xs flex gap-4">
          <span>+{job.n_added} nuovi</span>
          <span>Totale: {job.n_total}</span>
          <span className="font-mono opacity-60">{job.filename}</span>
        </div>
      )}

      {job.status === 'failed' && job.error && (
        <p className="mt-2 pt-2 border-t border-current border-opacity-20 text-xs font-mono">
          {job.error}
        </p>
      )}

      {job.status === 'running' && (
        <div className="mt-2 h-1 bg-blue-200 rounded-full overflow-hidden">
          <div className="h-full bg-blue-500 rounded-full animate-pulse w-2/3" />
        </div>
      )}
    </div>
  )
}

export default function RunPanel() {
  const [form, setForm] = useState({
    target:        '',
    topic:         '',
    date_from:     '',
    date_to:       today(),
    sources:       [],
    max_results:   20,
    news_language: 'en',
    save_raw:      true,
    dry_run:       false,
  })

  const [jobs, setJobs]       = useState([])   // lista job di questa sessione
  const [activeRun, setActive] = useState(null) // run_id in polling
  const [loading, setLoading]  = useState(false)
  const [error, setError]      = useState('')

  // Polling sullo stato del job attivo
  usePolling(async () => {
    if (!activeRun) return
    try {
      const status = await getRunStatus(activeRun)
      setJobs(prev => prev.map(j => j.run_id === activeRun ? status : j))
      if (status.status === 'done' || status.status === 'failed') {
        setActive(null)
      }
    } catch {
      setActive(null)
    }
  }, 3000, !!activeRun)

  const setField = (key, val) => setForm(f => ({ ...f, [key]: val }))

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const body = {
        ...form,
        max_results: Number(form.max_results),
        date_from: form.date_from || null,
        date_to:   form.date_to   || null,
      }
      const res = await startRun(body)
      const newJob = {
        run_id:     res.run_id,
        status:     'queued',
        progress:   'In coda...',
        target:     form.target,
        topic:      form.topic,
        created_at: res.created_at,
        n_added: null, n_total: null, filename: null, error: null,
      }
      setJobs(prev => [newJob, ...prev])
      setActive(res.run_id)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

      {/* ── Form ── */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-5">Nuova analisi</h2>

        <form onSubmit={handleSubmit} className="space-y-5">

          {/* Target + Topic */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Target *</label>
              <input
                required
                value={form.target}
                onChange={e => setField('target', e.target.value)}
                placeholder="es. Zendaya"
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Topic *</label>
              <input
                required
                value={form.topic}
                onChange={e => setField('topic', e.target.value)}
                placeholder="es. Euphoria"
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
              />
            </div>
          </div>

          {/* Date range */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Data inizio</label>
              <input
                type="date"
                value={form.date_from}
                onChange={e => setField('date_from', e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Data fine</label>
              <input
                type="date"
                value={form.date_to}
                onChange={e => setField('date_to', e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
              />
            </div>
          </div>

          {/* Parametri aggiuntivi */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">
                Max risultati per fonte
              </label>
              <input
                type="number" min={1} max={100}
                value={form.max_results}
                onChange={e => setField('max_results', e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Lingua news</label>
              <select
                value={form.news_language}
                onChange={e => setField('news_language', e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none bg-white"
              >
                {['en','it','fr','de','es','pt'].map(l => (
                  <option key={l} value={l}>{l.toUpperCase()}</option>
                ))}
              </select>
            </div>
          </div>

          {/* Opzioni */}
          <div className="flex gap-4">
            <label className="flex items-center gap-2 cursor-pointer text-sm text-gray-700">
              <input
                type="checkbox"
                checked={form.save_raw}
                onChange={e => setField('save_raw', e.target.checked)}
                className="rounded border-gray-300 text-blue-600"
              />
              Salva raw
            </label>
            <label className="flex items-center gap-2 cursor-pointer text-sm text-gray-700">
              <input
                type="checkbox"
                checked={form.dry_run}
                onChange={e => setField('dry_run', e.target.checked)}
                className="rounded border-gray-300 text-blue-600"
              />
              Dry run
            </label>
          </div>

          {/* Sorgenti */}
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-2">Sorgenti</label>
            <div className="rounded-lg border border-gray-200 bg-gray-50 p-3">
              <SourceSelector
                selected={form.sources}
                onChange={s => setField('sources', s)}
              />
            </div>
          </div>

          {error && (
            <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>
          )}

          <button
            type="submit"
            disabled={loading || !!activeRun}
            className="w-full py-2.5 rounded-lg bg-blue-600 text-white text-sm font-semibold
                       hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed
                       transition-colors"
          >
            {loading ? 'Avvio...' : activeRun ? 'Pipeline in esecuzione...' : '▶ Avvia analisi'}
          </button>
        </form>
      </div>

      {/* ── Job list ── */}
      <div className="space-y-3">
        <h2 className="text-lg font-semibold text-gray-900">Job di questa sessione</h2>
        {jobs.length === 0 ? (
          <div className="bg-white rounded-xl border border-dashed border-gray-300 p-8 text-center">
            <p className="text-gray-400 text-sm">Nessun job avviato.</p>
            <p className="text-gray-300 text-xs mt-1">Compila il form e avvia un'analisi.</p>
          </div>
        ) : (
          jobs.map(j => <JobCard key={j.run_id} job={j} />)
        )}
      </div>

    </div>
  )
}
