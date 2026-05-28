import { useEffect, useState } from 'react'
import { getSources } from '../api/client'

/**
 * Multi-select per le sorgenti disponibili.
 * Mostra le sorgenti in gruppi (default / opt-in) con checkbox individuali
 * e bottoni "Seleziona tutti" / "Deseleziona tutti".
 */
export default function SourceSelector({ selected, onChange }) {
  const [allSources, setAllSources]     = useState([])
  const [defaults, setDefaults]         = useState([])
  const [optIn, setOptIn]               = useState([])
  const [loading, setLoading]           = useState(true)
  const [loadError, setLoadError]       = useState('')

  useEffect(() => {
    getSources()
      .then(data => {
        setAllSources(data.all || [])
        setDefaults(data.defaults || [])
        setOptIn(data.opt_in || [])
        if (selected.length === 0) onChange(data.defaults || [])
      })
      .catch(err => setLoadError(err.message || 'Impossibile caricare le sorgenti.'))
      .finally(() => setLoading(false))
  }, []) // eslint-disable-line

  const toggle = (src) => {
    if (selected.includes(src)) {
      onChange(selected.filter(s => s !== src))
    } else {
      onChange([...selected, src])
    }
  }

  const selectAll  = () => onChange([...allSources])
  const selectNone = () => onChange([])
  const selectDefault = () => onChange([...defaults])

  if (loading)   return <p className="text-sm text-gray-400">Caricamento sorgenti...</p>
  if (loadError) return <p className="text-sm text-red-500">{loadError}</p>

  const groups = [
    { label: 'Sorgenti predefinite', items: defaults },
    { label: 'Opt-in (quota limitata)', items: optIn },
  ]

  return (
    <div className="space-y-3">
      <div className="flex gap-2 text-xs">
        <button onClick={selectAll}     className="text-blue-600 hover:underline">Tutte</button>
        <span className="text-gray-300">|</span>
        <button onClick={selectDefault} className="text-blue-600 hover:underline">Default</button>
        <span className="text-gray-300">|</span>
        <button onClick={selectNone}    className="text-blue-600 hover:underline">Nessuna</button>
        <span className="ml-auto text-gray-400">{selected.length} / {allSources.length} selezionate</span>
      </div>

      {groups.map(({ label, items }) => (
        <div key={label}>
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">{label}</p>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-1">
            {items.map(src => (
              <label key={src} className="flex items-center gap-2 cursor-pointer group">
                <input
                  type="checkbox"
                  checked={selected.includes(src)}
                  onChange={() => toggle(src)}
                  className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                />
                <span className="text-sm text-gray-700 group-hover:text-gray-900 truncate">{src}</span>
              </label>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}
