import { useQuery } from "@tanstack/react-query";

async function fetchHealth() {
  const resp = await fetch("/api/health");
  if (!resp.ok) throw new Error("Failed to fetch health");
  return resp.json();
}

export function useHealth() {
  return useQuery({ queryKey: ["health"], queryFn: fetchHealth, refetchInterval: 5000 });
}
