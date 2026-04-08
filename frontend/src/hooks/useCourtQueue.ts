import { useQuery } from "@tanstack/react-query";
import type { QuarantineItemResponse } from "../types";

async function fetchQueue(): Promise<QuarantineItemResponse[]> {
  const resp = await fetch("/api/court/queue");
  if (!resp.ok) throw new Error("Failed to fetch court queue");
  return resp.json();
}

export function useCourtQueue() {
  const query = useQuery({ queryKey: ["court-queue"], queryFn: fetchQueue, refetchInterval: 3000 });
  return { queue: query.data ?? [], isLoading: query.isLoading, error: query.error };
}
