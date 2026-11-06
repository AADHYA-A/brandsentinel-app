import type { Doc, DocSummary, KitRec, User, AuditRow } from "./types";

let token = "";
try { token = sessionStorage.getItem("bs_token") || ""; } catch { /* storage unavailable */ }
export const setToken = (t: string) => { token = t; try { t ? sessionStorage.setItem("bs_token", t) : sessionStorage.removeItem("bs_token"); } catch { /* ignore */ } };
export const hasToken = () => !!token;

export class ApiError extends Error { constructor(public status: number, msg: string) { super(msg); } }
let onUnauthorised: () => void = () => {};
export const setUnauthorisedHandler = (f: () => void) => { onUnauthorised = f; };

async function req<T>(method: string, path: string, body?: unknown, form?: FormData): Promise<T> {
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = "Bearer " + token;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const r = await fetch("/api" + path, { method, headers, body: form ?? (body !== undefined ? JSON.stringify(body) : undefined) });
  if (!r.ok) {
    let msg = r.statusText;
    try { const j = await r.json(); msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch { /* not json */ }
    if (r.status === 401 && token) onUnauthorised();
    throw new ApiError(r.status, msg);
  }
  const ct = r.headers.get("content-type") || "";
  return (ct.includes("json") ? r.json() : r.text()) as Promise<T>;
}
const get = <T,>(p: string) => req<T>("GET", p);
const post = <T,>(p: string, b: unknown = {}) => req<T>("POST", p, b);

export const api = {
  login: (email: string, password: string) => post<{ token: string; user: User }>("/auth/login", { email, password }),
  demoUsers: () => get<User[]>("/auth/demo-users"),
  me: () => get<User>("/auth/me"),
  disclosure: () => get<{ ai_configured: boolean; model: string | null; tenant_local_only: boolean; text: string; storage: string }>("/disclosure"),
  docs: () => get<DocSummary[]>("/documents"),
  doc: (id: number) => get<Doc>("/documents/" + id),
  createDoc: (b: { title: string; text: string; team?: string; local_only?: boolean }) => post<Doc>("/documents", b),
  upload: (f: File, o: { title?: string; local_only?: boolean; alt_text?: string; text_colour?: string; bg_colour?: string }) => {
    const fd = new FormData();
    fd.append("file", f);
    Object.entries(o).forEach(([k, v]) => v !== undefined && fd.append(k, String(v)));
    return req<Doc>("POST", "/documents/upload", undefined, fd);
  },
  saveText: (id: number, text: string, title?: string) => req<Doc>("PUT", `/documents/${id}`, { text, title }),
  localOnly: (id: number, local_only: boolean) => req<Doc>("PUT", `/documents/${id}/local-only`, { local_only }),
  review: (id: number) => post<Doc>(`/documents/${id}/review`),
  decide: (id: number, fid: number, b: { action: string; text?: string; reason?: string }) => post<Doc>(`/documents/${id}/findings/${fid}`, b),
  act: (id: number, action: string, note = "") => post<Doc>(`/documents/${id}/${action}`, { note }),
  diff: (id: number, a: number, b?: number) => get<{ ops: { op: string; text: string }[] }>(`/documents/${id}/diff?a=${a}` + (b ? `&b=${b}` : "")),
  docAudit: (id: number) => get<AuditRow[]>(`/documents/${id}/audit`),
  imageUrl: async (id: number) => {
    const r = await fetch(`/api/documents/${id}/image`, { headers: { Authorization: "Bearer " + token } });
    if (!r.ok) throw new ApiError(r.status, "Image unavailable");
    return URL.createObjectURL(await r.blob());
  },
  audit: () => get<AuditRow[]>("/audit"),
  verify: () => get<{ ok: boolean; events: number; broken_at: number | null }>("/audit/verify"),
  aiLog: () => get<Record<string, any>[]>("/ai-log"),
  download: async (path: string, name: string) => {
    const r = await fetch("/api" + path, { headers: { Authorization: "Bearer " + token } });
    if (!r.ok) throw new ApiError(r.status, "Download failed");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(await r.blob());
    a.download = name;
    a.click();
    URL.revokeObjectURL(a.href);
  },
  kit: () => get<{ records: KitRec[]; system: { rid: string; text: string }[] }>("/kit"),
  kitSave: (b: { kind: string; data: Record<string, any>; rid?: string; valid_to?: string | null; note?: string }) => post<KitRec>("/kit/records", b),
  kitRetire: (rid: string) => req<{ ok: boolean }>("DELETE", "/kit/records/" + encodeURIComponent(rid)),
  kitHistory: (rid: string) => get<KitRec[]>(`/kit/records/${encodeURIComponent(rid)}/history`),
  kitImport: (text: string, filename: string, commit: boolean) =>
    post<{ records: { kind: string; data: any; valid_to?: string | null }[]; warnings: string[]; committed?: number }>("/kit/import", { text, filename, commit }),
  kitImportFile: (f: File, commit: boolean) => {
    const fd = new FormData();
    fd.append("file", f);
    fd.append("commit", String(commit));
    return req<{ records: { kind: string; data: any; valid_to?: string | null }[]; warnings: string[]; committed?: number }>("POST", "/kit/import-file", undefined, fd);
  },
  insights: () => get<any>("/insights"),
  evaluate: () => get<any>("/eval"),
  demoActivity: () => post<{ decisions: number }>("/admin/demo-activity"),
};
