import { useState, useCallback } from 'react'
import RunPanel      from './components/RunPanel'
import ResultsPanel  from './components/ResultsPanel'
import SchedulePanel from './components/SchedulePanel'

const TABS = [
  { id: 'run',       label: '▶ Run',        icon: '⚡' },
  { id: 'results',   label: '📊 Risultati', icon: '📊' },
  { id: 'schedules', label: '🕐 Schedule',  icon: '🕐' },
]

export default function App() {
  const [tab, setTab] = useState('run')
  // Traccia i tab già visitati: i pannelli vengono montati al primo accesso
  // e poi mantenuti vivi (hidden) per preservare stato e polling attivi.
  const [visited, setVisited] = useState(() => new Set(['run']))

  const switchTab = useCallback((id) => {
    setTab(id)
    setVisited(prev => { const s = new Set(prev); s.add(id); return s })
  }, [])

  return (
    <div className="min-h-screen bg-gray-50">

      {/* ── Navbar ── */}
      <nav className="bg-white border-b border-gray-200 sticky top-0 z-10 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-14">
            {/* Logo */}
            <div className="flex items-center gap-2">
              <span className="text-lg">🔍</span>
              <span className="font-bold text-gray-900 text-sm tracking-tight">
                WR Analysis
              </span>
              <span className="text-xs text-gray-400 font-normal hidden sm:inline">
                Web Reputational Analysis
              </span>
            </div>

            {/* Tabs + switch to dashboard */}
            <div className="flex items-center gap-1">
              {TABS.map(t => (
                <button
                  key={t.id}
                  onClick={() => switchTab(t.id)}
                  className={`px-4 py-2 text-sm font-medium rounded-lg transition-colors
                    ${tab === t.id
                      ? 'bg-blue-50 text-blue-700'
                      : 'text-gray-500 hover:text-gray-700 hover:bg-gray-100'}`}
                >
                  {t.label}
                </button>
              ))}

              <div className="w-px h-5 bg-gray-200 mx-1" />

              <a
                href="/dashboard/"
                className="px-4 py-2 text-sm font-medium rounded-lg transition-colors
                           text-violet-600 hover:text-violet-700 hover:bg-violet-50
                           flex items-center gap-1.5"
              >
                <span>📊</span>
                <span>Sentiment</span>
              </a>
            </div>
          </div>
        </div>
      </nav>

      {/* ── Content ──
           I pannelli vengono montati al primo accesso e poi tenuti vivi con
           display:none — così lo stato (job list, polling attivo) non si perde
           quando l'utente cambia tab. */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {visited.has('run')       && <div style={{ display: tab === 'run'       ? undefined : 'none' }}><RunPanel /></div>}
        {visited.has('results')   && <div style={{ display: tab === 'results'   ? undefined : 'none' }}><ResultsPanel /></div>}
        {visited.has('schedules') && <div style={{ display: tab === 'schedules' ? undefined : 'none' }}><SchedulePanel /></div>}
      </main>

      {/* ── Footer ── */}
      <footer className="mt-10 pb-6 text-center text-xs text-gray-300">
        wr-analysis · microservices edition
      </footer>
    </div>
  )
}
