import { useQuery } from "@tanstack/react-query";

async function fetchMemories(sessionId: string | null) {
  const params = new URLSearchParams();
  if (sessionId) params.set("session_id", sessionId);
  const resp = await fetch(`/api/memories?${params.toString()}`);
  if (!resp.ok) throw new Error("Failed to fetch memories");
  return resp.json();
}

export function useMemories(sessionId: string | null) {
  const query = useQuery({ queryKey: ["memories", sessionId], queryFn: () => fetchMemories(sessionId) });

  const searchMemories = async (queryValue: string) => {
    const resp = await fetch(`/api/memories/search?q=${encodeURIComponent(queryValue)}&top_k=5`);
    if (!resp.ok) throw new Error("Failed to search memories");
    return resp.json();
  };

  const deleteMemory = async (id: string) => {
    const resp = await fetch(`/api/memories/${id}`, { method: "DELETE" });
    if (!resp.ok) throw new Error("Failed to delete memory");
    return resp.json();
  };

  return { memories: query.data?.memories ?? [], searchMemories, deleteMemory, isLoading: query.isLoading, error: query.error };
}
