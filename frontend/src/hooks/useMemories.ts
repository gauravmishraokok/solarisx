import { useQuery } from '@tanstack/react-query'
import { getMemories } from '../api/memories'
import { useChatStore } from '../store'

export function useMemories() {
  const sessionId = useChatStore((s) => s.sessionId)
  return useQuery({
    queryKey: ['memories', sessionId],
    queryFn: () => getMemories(sessionId),
    refetchInterval: 5000,
    placeholderData: (prev) => prev,
  })
}
