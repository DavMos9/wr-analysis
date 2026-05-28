import { useEffect, useRef } from 'react'

/**
 * Esegue `fn` ogni `intervalMs` ms finché `active` è true.
 * Pulisce automaticamente l'intervallo al unmount o quando active cambia.
 */
export function usePolling(fn, intervalMs, active) {
  const fnRef = useRef(fn)
  fnRef.current = fn

  useEffect(() => {
    if (!active) return
    fnRef.current()                                      // fire immediato al primo render
    const id = setInterval(() => fnRef.current(), intervalMs)
    return () => clearInterval(id)
  }, [active, intervalMs])
}
