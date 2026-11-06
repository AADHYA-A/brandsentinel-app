import { useEffect, useState } from "react";
import { api } from "../api";
import type { Ctx } from "../App";
import type { AuditRow } from "../types";
import { Btn, Muted, Pane, errMsg, useToast, when } from "../ui";

export default function Audit({ ctx: _ }: { ctx: Ctx }) {
  const toast = useToast();
  const [rows, setRows] = useState<AuditRow[]>([]);
  const [ai, setAi] = useState<Record<string, any>[]>([]);
  const [chain, setChain] = useState<{ ok: boolean; events: number; broken_at: number | null } | null>(null);
  useEffect(() => {
    api.audit().then(setRows).catch(e => toast(errMsg(e), true));
    api.aiLog().then(setAi).catch(() => {});
    api.verify().then(setChain).catch(() => {});
  }, [toast]);
  const dl = (p: string, n: string) => api.download(p, n).catch(e => toast(errMsg(e), true));
  return (
    <div className="grid gap-4">
      <Pane>
        <div className="flex flex-wrap items-center gap-2 mb-1">
          <h2 className="text-[22px] mr-auto">Audit log</h2>
          <Btn v="s" onClick={() => dl("/audit/report?format=txt", "audit-report.txt")}>Export report (.txt)</Btn>
          <Btn v="s" onClick={() => dl("/audit/report?format=csv", "audit.csv")}>CSV</Btn>
          <Btn v="s" onClick={() => dl("/audit/report?format=json", "audit.json")}>JSON</Btn>
        </div>
        <Muted>Every decision, with the role that made it. The log is append-only and hash-chained.
          {chain && (chain.ok ? ` Chain verified: ${chain.events} events, none altered.` : ` WARNING: chain broken at event ${chain.broken_at}.`)}</Muted>
        <div className="overflow-x-auto"><table><thead><tr><th>#</th><th>Time</th><th>Who</th><th>Action</th><th>Detail</th></tr></thead>
          <tbody>{rows.map(r => <tr key={r.seq}><td className="text-mut">{r.seq}</td><td className="whitespace-nowrap">{when(r.at)}</td><td>{r.user}<div className="text-xs text-mut">{r.role}</div></td>
            <td className="font-semibold">{r.action}</td><td className="break-words max-w-md">{r.detail}</td></tr>)}
            {!rows.length && <tr><td colSpan={5} className="text-mut">No events yet.</td></tr>}</tbody></table></div>
      </Pane>
      <Pane>
        <div className="flex flex-wrap items-center gap-2 mb-1"><h2 className="text-[22px] mr-auto">AI-use log</h2><Btn v="s" onClick={() => dl("/ai-log?format=csv", "ai-use-log.csv")}>Export CSV</Btn></div>
        <Muted>One row per review: whether an external model was called, why not, and how many of its findings survived the verifier. Draft content is never stored here.</Muted>
        <div className="overflow-x-auto"><table><thead><tr><th>Time</th><th>Doc</th><th>Mode</th><th>Model</th><th>Returned</th><th>Kept</th><th>ms</th><th>Detail</th></tr></thead>
          <tbody>{ai.slice(0, 50).map((r, i) => <tr key={i}><td className="whitespace-nowrap">{when(r.at)}</td><td>{r.doc_id}</td><td>{r.mode}</td><td>{r.model || "none"}</td><td>{r.returned}</td><td>{r.kept}</td><td>{r.latency_ms}</td><td className="text-mut">{r.detail}</td></tr>)}</tbody></table></div>
      </Pane>
    </div>
  );
}
