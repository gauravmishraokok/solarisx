import { useQuery } from '@tanstack/react-query'
import { useEffect, useRef } from 'react'
import { getCourtQueue } from '../api/court'
import { useCourtStore } from '../store'

export function useCourtQueue() {
  const { setPendingCount, setAlert } = useCourtStore()
  const prevCountRef = useRef(0)

  const query = useQuery({
    queryKey: ['court-queue'],
    queryFn: getCourtQueue,
    refetchInterval: 4000,
    placeholderData: (prev) => prev,
  })

  useEffect(() => {
    const items: unknown[] = Array.isArray(query.data) ? query.data : (query.data?.items ?? [])
    const count = items.length
    setPendingCount(count)

    if (count > prevCountRef.current) {
      setAlert(true)
      document.title = `⚠ MEMORA — ${count} Contradiction${count > 1 ? 's' : ''} Pending`
      setTimeout(() => setAlert(false), 4000)
    } else if (count === 0) {
      document.title = 'MEMORA'
    }
    prevCountRef.current = count
  }, [query.data, setPendingCount, setAlert])

  return query
}
