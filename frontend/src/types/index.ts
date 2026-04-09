export interface MemoryCube {
  id: string
  content: string
  memory_type: 'episodic' | 'semantic' | 'kg_node'
  tier: 'hot' | 'warm' | 'cold'
  tags: string[]
  access_count: number
  created_at: string
  updated_at: string
  provenance: {
    origin: string
    session_id: string
    version: number
    parent_id: string | null
  } | null
  extra: Record<string, unknown>
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  text: string
  memories_used?: string[]
  timestamp: Date
}

export interface QuarantineItem {
  quarantine_id: string
  incoming_content: string
  incoming_cube_id: string
  conflicting_cube_id: string
  contradiction_score: number
  reasoning: string
  suggested_resolution: string | null
  created_at: string
}

export interface GraphNode {
  id: string
  label: string
  type: 'episodic' | 'semantic' | 'kg_node'
  tier: 'hot' | 'warm' | 'cold'
  content: string
  tags: string[]
  access_count: number
}

export interface GraphEdge {
  id: string
  source: string
  target: string
  label: string
  active: boolean
}

export interface TimelineEvent {
  id: string
  cube_id: string | null
  event_type: 'created' | 'updated' | 'quarantined' | 'resolved' | 'evicted'
  description: string | null
  session_id: string | null
  metadata: Record<string, unknown>
  created_at: string
}

export interface HealthData {
  status: string
  total_memories: number
  memories_by_tier: { hot: number; warm: number; cold: number }
  memories_by_type: { episodic: number; semantic: number; kg_node: number }
  retrieval_latency_p50_ms: number
  retrieval_latency_p99_ms: number
  quarantine_pending: number
  db_connected: boolean
  uptime_seconds: number
}
