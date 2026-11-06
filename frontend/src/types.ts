export type Role = "Creator" | "Authorised Reviewer" | "Brand Manager" | "Brand Admin";
export interface User { id: number; name: string; email: string; role: Role; team: string; tenant: string; password?: string }
export interface Finding {
  id: number; key: string; category: string; severity: "High" | "Medium" | "Low" | "Cannot verify"; risk: "high" | "low";
  method: "Rule" | "Heuristic" | "AI"; src: string; src_text: string; text: string; start: number; end: number; why: string;
  tip: string | null; rep: string | null; confidence: number | null; block: number | null; decision: string | null; reason: string | null;
}
export interface DocSummary {
  id: number; title: string; team: string; status: string; status_label: string; version: number; source_type: string; creator: string;
  local_only: boolean; high_risk: number; finding_count: number; open: number; submitted_at: string | null; updated_at: string; mine_to_review?: boolean;
}
export interface Doc extends DocSummary {
  text: string; filename: string; alt_text: string; blocks: { i: number; start: number; end: number; kind: string; page: number }[];
  image_stats: { width: number; height: number; dominant: { hex: string; share: number }[]; clearspace_pct?: number } | null;
  notes: string[]; reviewed: boolean; fresh: boolean;
  run: { id: number; at: string; raw: number; kept: number; dropped: { src: string; text: string; method: string; reason: string }[]; ms: number; ai_status: string } | null;
  findings: Finding[];
  perms: { edit: boolean; decide: boolean; submit: boolean; reviewer: boolean; manager: boolean; publish: boolean; new_revision: boolean };
  comments: { user: string; role: string; text: string; at: string }[];
  versions: { version: number; at: string; by: string; role: string; note: string; text: string }[];
}
export interface KitRec {
  rid: string; kind: string; version: number; active: boolean; data: Record<string, any>; valid_to: string | null; text: string;
  created_by: string; created_at: string; note: string;
}
export interface AuditRow { seq: number; at: string; user: string; role: string; action: string; detail: string; doc_id: number | null; hash: string }
