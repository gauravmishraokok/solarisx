import { useQuery } from "@tanstack/react-query";

async function fetchTimeline(sessionId: string | null) {
  const params = new URLSearchParams();
  if (sessionId) params.set("session_id", sessionId);
  params.set("limit", "50");
  const resp = await fetch(`/api/timeline?${params.toString()}`);
  if (!resp.ok) throw new Error("Failed to fetch timeline");
  return resp.json();
}

export function useTimeline(sessionId: string | null) {
  return useQuery({
    queryKey: ["timeline", sessionId],
    queryFn: () => fetchTimeline(sessionId),
    refetchOnWindowFocus: true,
  });
}
