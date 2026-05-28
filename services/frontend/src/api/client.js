/**
 * client.js — Wrapper attorno alle chiamate REST ai microservizi.
 *
 * Tutti gli URL passano per /api/{service}/ che nginx instrada
 * al servizio corretto. In sviluppo Vite fa da proxy (vite.config.js).
 */

const BASE = {
  pipeline:  '/api/pipeline',
  results:   '/api/results',
  scheduler: '/api/scheduler',
}

async function _fetch(url, options = {}) {
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  })
  if (!res.ok) {
    const text = await res.text()
    // FastAPI restituisce {"detail": "..."} — estrai il messaggio leggibile
    let msg = text
    try {
      const detail = JSON.parse(text)?.detail
      if (typeof detail === 'string')  msg = detail
      else if (Array.isArray(detail))  msg = detail.map(e => e.msg).join(', ')
    } catch {}
    throw new Error(`[${res.status}] ${msg}`)
  }
  // 204 No Content
  if (res.status === 204) return null
  return res.json()
}

// ── Pipeline Service ──────────────────────────────────────────────────────────

export const getSources = () =>
  _fetch(`${BASE.pipeline}/sources`)

export const startRun = (body) =>
  _fetch(`${BASE.pipeline}/run`, { method: 'POST', body: JSON.stringify(body) })

export const getRunStatus = (runId) =>
  _fetch(`${BASE.pipeline}/run/${runId}`)

export const listRuns = () =>
  _fetch(`${BASE.pipeline}/runs`)

// ── Results Service ───────────────────────────────────────────────────────────

export const listResults = () =>
  _fetch(`${BASE.results}/results`)

export const getResultRecords = (filename) =>
  _fetch(`${BASE.results}/results/${filename}`)

export const getResultSummary = (filename) =>
  _fetch(`${BASE.results}/results/${filename}/summary`)

export const downloadUrl = (filename, format) =>
  `${BASE.results}/download/${filename}/${format}`

// ── Scheduler Service ─────────────────────────────────────────────────────────

export const listSchedules = () =>
  _fetch(`${BASE.scheduler}/schedules`)

export const createSchedule = (body) =>
  _fetch(`${BASE.scheduler}/schedules`, { method: 'POST', body: JSON.stringify(body) })

export const deleteSchedule = (id) =>
  _fetch(`${BASE.scheduler}/schedules/${id}`, { method: 'DELETE' })

export const toggleSchedule = (id, enabled) =>
  _fetch(`${BASE.scheduler}/schedules/${id}`, {
    method: 'PATCH',
    body: JSON.stringify({ enabled }),
  })
