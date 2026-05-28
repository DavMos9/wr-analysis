import { useEffect, useState } from 'react'
import { listSchedules, createSchedule, deleteSchedule, toggleSchedule } from '../api/client'
import SourceSelector from './SourceSelector'

const FORM_DEFAULTS = {
  target:           '',
  topic:            '',
  frequency:        'weekly',
  hour:             8,
  day_of_week:      'mon',
  date_window_days: 7,
  sources:          [],
  max_results:      20,
  news_language:    'en',
  save_raw:         true,
}

const FREQ_LABELS = {
  hourly:  'Ogni ora',
  daily:   'Ogni giorno',
  weekly:  'Ogni settimana',
  monthly: 'Ogni mese',
}

const DAY_LABELS = {
  mon: 'Lunedì', tue: 'Martedì', wed: 'Mercoledì', thu: 'Giovedì',
  fri: 'Venerdì', sat: 'Sabato', sun: 'Domenica',
}

function formatNext(isoStr) {
  if (!isoStr) return '—'
  const d = new Date(isoStr)
  return d.toLocaleString('it-IT', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

function ScheduleRow({ sched, onToggle, onDelete, pendingDelete, onConfirmDelete, onCancelDelete }) {
  const enabled = !!sched.enabled

  return (
    <div className={`rounded-lg border p-4 transition-colors
      ${enabled ? 'bg-white border-gray-200' : 'bg-gray-50 border-gray-200 opacity-60'}`}>
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="font-semibold text-sm text-gray-900">
            {sched.target} / <span className="font-normal text-gray-600">{sched.topic}</span>
          </p>
          <div className="flex flex-wrap gap-2 mt-1 text-xs text-gray-500">
            <span className="bg-gray-100 px-2 py-0.5 rounded-full">
              {FREQ_LABELS[sched.frequency] || sched.frequency}
            </span>
            {sched.frequency === 'weekly' && (
              <span>{DAY_LABELS[sched.day_of_week] || sched.day_of_week}</span>
            )}
            {sched.frequency !== 'hourly' && (
              <span>ore {sched.hour ?? 8}:00</span>
            )}
            <span>finestra: {sched.date_window_days}g</span>
          </div>
          <p className="text-xs text-gray-400 mt-1">
            Prossimo run: <span className="text-gray-600">{formatNext(sched.next_run)}</span>
          </p>
          {sched.last_run && (
            <p className="text-xs text-gray-400">
              Ultimo run: {formatNext(sched.last_run)}
            </p>
          )}
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {pendingDelete === sched.id ? (
            /* Conferma inline — sostituisce window.confirm() */
            <div className="flex items-center gap-1.5 text-xs">
              <span className="text-gray-500">Eliminare?</span>
              <button
                onClick={() => onConfirmDelete(sched.id)}
                className="px-2 py-1 rounded bg-red-500 text-white hover:bg-red-600 transition-colors font-medium"
              >
                Sì
              </button>
              <button
                onClick={onCancelDelete}
                className="px-2 py-1 rounded bg-gray-100 text-gray-600 hover:bg-gray-200 transition-colors"
              >
                No
              </button>
            </div>
          ) : (
            <>
              <button
                onClick={() => onToggle(sched.id, !enabled)}
                title={enabled ? 'Disabilita' : 'Abilita'}
                className={`w-10 h-5 rounded-full transition-colors relative
                  ${enabled ? 'bg-blue-500' : 'bg-gray-300'}`}
              >
                <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-all
                  ${enabled ? 'left-5' : 'left-0.5'}`} />
              </button>
              <button
                onClick={() => onDelete(sched.id)}
                title="Elimina"
                className="text-gray-300 hover:text-red-500 transition-colors text-sm"
              >
                🗑
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

export default function SchedulePanel() {
  const [schedules, setSchedules] = useState([])
  const [loading, setLoading]       = useState(true)
  const [loadError, setLoadError]   = useState('')
  const [showForm, setShowForm]     = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError]           = useState('')
  const [actionError, setActionError] = useState('')
  const [pendingDelete, setPendingDelete] = useState(null)  // id schedule in attesa conferma

  const [form, setForm] = useState(FORM_DEFAULTS)

  const setField = (k, v) => setForm(f => ({ ...f, [k]: v }))

  const reload = () => {
    setLoading(true)
    setLoadError('')
    listSchedules()
      .then(setSchedules)
      .catch(err => setLoadError(err.message || 'Impossibile caricare gli schedule.'))
      .finally(() => setLoading(false))
  }

  useEffect(reload, [])

  const handleCreate = async (e) => {
    e.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      await createSchedule({
        ...form,
        hour:             Number(form.hour),
        date_window_days: Number(form.date_window_days),
        max_results:      Number(form.max_results),
      })
      setForm(FORM_DEFAULTS)
      setShowForm(false)
      reload()
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  const handleToggle = async (id, enabled) => {
    setActionError('')
    try {
      await toggleSchedule(id, enabled)
      reload()
    } catch (err) {
      setActionError(`Impossibile ${enabled ? 'abilitare' : 'disabilitare'} lo schedule: ${err.message}`)
    }
  }

  const handleDelete = (id) => setPendingDelete(id)

  const handleConfirmDelete = async (id) => {
    setPendingDelete(null)
    setActionError('')
    try {
      await deleteSchedule(id)
      reload()
    } catch (err) {
      setActionError(`Impossibile eliminare lo schedule: ${err.message}`)
    }
  }

  const handleCancelDelete = () => setPendingDelete(null)

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-900">Schedule periodici</h2>
        <div className="flex gap-2">
          <button onClick={reload}
                  className="text-sm text-gray-500 hover:text-gray-700 transition-colors">
            ↻ Aggiorna
          </button>
          <button
            onClick={() => { setShowForm(s => !s); setError('') }}
            className="text-sm px-4 py-2 rounded-lg bg-blue-600 text-white hover:bg-blue-700 transition-colors"
          >
            {showForm ? '✕ Annulla' : '+ Nuovo schedule'}
          </button>
        </div>
      </div>

      {/* Form creazione */}
      {showForm && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <h3 className="font-semibold text-gray-900 mb-5">Crea schedule</h3>
          <form onSubmit={handleCreate} className="space-y-5">

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Target *</label>
                <input required value={form.target}
                  onChange={e => setField('target', e.target.value)}
                  placeholder="es. Zendaya"
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 outline-none" />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Topic *</label>
                <input required value={form.topic}
                  onChange={e => setField('topic', e.target.value)}
                  placeholder="es. Euphoria"
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 outline-none" />
              </div>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Frequenza</label>
                <select value={form.frequency} onChange={e => setField('frequency', e.target.value)}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm bg-white focus:ring-2 focus:ring-blue-500 outline-none">
                  {Object.entries(FREQ_LABELS).map(([k, v]) => (
                    <option key={k} value={k}>{v}</option>
                  ))}
                </select>
              </div>

              {form.frequency !== 'hourly' && (
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">Ora (0-23)</label>
                  <input type="number" min={0} max={23} value={form.hour}
                    onChange={e => setField('hour', e.target.value)}
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 outline-none" />
                </div>
              )}

              {form.frequency === 'weekly' && (
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">Giorno</label>
                  <select value={form.day_of_week} onChange={e => setField('day_of_week', e.target.value)}
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm bg-white focus:ring-2 focus:ring-blue-500 outline-none">
                    {Object.entries(DAY_LABELS).map(([k, v]) => (
                      <option key={k} value={k}>{v}</option>
                    ))}
                  </select>
                </div>
              )}

              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Look-back (giorni)</label>
                <input type="number" min={1} max={365} value={form.date_window_days}
                  onChange={e => setField('date_window_days', e.target.value)}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 outline-none" />
              </div>

              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Max risultati</label>
                <input type="number" min={1} max={100} value={form.max_results}
                  onChange={e => setField('max_results', e.target.value)}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 outline-none" />
              </div>
            </div>

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

            <div className="flex gap-3">
              <button type="submit" disabled={submitting}
                className="flex-1 py-2.5 rounded-lg bg-blue-600 text-white text-sm font-semibold
                           hover:bg-blue-700 disabled:opacity-50 transition-colors">
                {submitting ? 'Creazione...' : 'Crea schedule'}
              </button>
              <button type="button" onClick={() => setShowForm(false)}
                className="px-4 py-2.5 rounded-lg border border-gray-300 text-sm text-gray-600
                           hover:bg-gray-50 transition-colors">
                Annulla
              </button>
            </div>
          </form>
        </div>
      )}

      {actionError && (
        <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{actionError}</p>
      )}

      {/* Lista schedule */}
      {loading ? (
        <div className="text-center text-gray-400 text-sm py-8">Caricamento...</div>
      ) : loadError ? (
        <div className="text-center text-red-500 text-sm py-8">{loadError}</div>
      ) : schedules.length === 0 ? (
        <div className="bg-white rounded-xl border border-dashed border-gray-300 p-10 text-center">
          <p className="text-gray-400 text-sm">Nessuno schedule configurato.</p>
          <p className="text-gray-300 text-xs mt-1">
            Crea uno schedule per avviare analisi periodiche automaticamente.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {schedules.map(s => (
            <ScheduleRow
              key={s.id}
              sched={s}
              onToggle={handleToggle}
              onDelete={handleDelete}
              pendingDelete={pendingDelete}
              onConfirmDelete={handleConfirmDelete}
              onCancelDelete={handleCancelDelete}
            />
          ))}
        </div>
      )}
    </div>
  )
}
