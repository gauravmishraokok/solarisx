import { useQuery } from '@tanstack/react-query'
import { getTimeline } from '../api/timeline'
import { useChatStore } from '../store'

export function useTimeline() {
  const sessionId = useChatStore((s) => s.sessionId)
  return useQuery({
    queryKey: ['timeline', sessionId],
    queryFn: () => getTimeline(sessionId),
    refetchInterval: 5000,
    placeholderData: (prev) => prev,
  })
}
