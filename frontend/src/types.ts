export interface Message {
  id: string;
  role: "user" | "agent";
  text: string;
  memoriesUsed?: string[];
}

export interface QuarantineItemResponse {
  quarantine_id: string;
  incoming_content: string;
  conflicting_cube_id: string;
  contradiction_score: number;
  reasoning: string;
  suggested_resolution: string | null;
  created_at: string;
}

export interface GraphNode {
  id: string;
  label: string;
  type: "episodic" | "semantic" | "kg_node";
  tier: "hot" | "warm" | "cold";
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  label: string;
  active: boolean;
}
