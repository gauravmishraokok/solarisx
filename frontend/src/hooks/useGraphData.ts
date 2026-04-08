import { useQuery } from "@tanstack/react-query";
import type { GraphEdge, GraphNode } from "../types";

async function fetchGraph(): Promise<{ nodes: GraphNode[]; edges: GraphEdge[] }> {
  const [nodesResp, edgesResp] = await Promise.all([fetch("/api/graph/nodes"), fetch("/api/graph/edges")]);
  if (!nodesResp.ok || !edgesResp.ok) throw new Error("Failed to fetch graph data");
  const nodesJson = await nodesResp.json();
  const edgesJson = await edgesResp.json();
  const edges: GraphEdge[] = (edgesJson.edges ?? []).map((edge: any) => ({
    id: edge.id,
    source: edge.source ?? edge.from,
    target: edge.target ?? edge.to,
    label: edge.label,
    active: Boolean(edge.active),
  }));
  return { nodes: nodesJson.nodes ?? [], edges };
}

export function useGraphData() {
  const query = useQuery({ queryKey: ["graph"], queryFn: fetchGraph, refetchOnWindowFocus: true });
  return { nodes: query.data?.nodes ?? [], edges: query.data?.edges ?? [], isLoading: query.isLoading, error: query.error };
}
