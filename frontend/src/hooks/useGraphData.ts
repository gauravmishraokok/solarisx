import { useQuery } from '@tanstack/react-query'
import { getGraphNodes, getGraphEdges } from '../api/graph'

export function useGraphData() {
  return useQuery({
    queryKey: ['graph'],
    queryFn: async () => {
      const [nodesRes, edgesRes] = await Promise.all([getGraphNodes(), getGraphEdges()])
      return {
        nodes: Array.isArray(nodesRes?.nodes) ? nodesRes.nodes : [],
        edges: Array.isArray(edgesRes?.edges) ? edgesRes.edges : [],
      }
    },
    refetchInterval: 5000,
    refetchOnWindowFocus: true,
    placeholderData: (prev) => prev,
  })
}
