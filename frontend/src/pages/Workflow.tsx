import { useEffect, useState } from "react";
import { api } from "../api";
import type { Ctx } from "../App";
import type { AuditRow, Doc } from "../types";
import { Area, Btn, Input, Muted, Pane, StatusPill, Tag, errMsg, useToast, when } from "../ui";

const STEPS = ["Draft", "Creator decides", "Reviewer (high-risk claims)", "Manager sign-off", "Approved", "Published"];
const AT: Record<string, number> = { draft: 1, changes_requested: 1, pending_reviewer: 2, pending_manager: 3, approved: 4, published: 5 };

export default function Workflow({ ctx }: { ctx: Ctx }) {
  const toast = useToast();
  const { doc, user } = ctx;
  const [note, setNote] = useState("");
  const [cm, setCm] = useState("");
  const [busy, setBusy] = useState(false);
  const [a, setA] = useState(1);
  const [b, setB] = useState<number | "working">("working");
  const [ops, setOps] = useState<{ op: string; text: string }[] | null>(null);
  const [trail, setTrail] = useState<AuditRow[]>([]);

  useEffect(() => { if (doc) api.docAudit(doc.id).then(setTrail).catch(() => {}); }, [doc?.id, doc?.status, doc?.comments.length]);  // eslint-disable-line
  useEffect(() => { setOps(null); setNote(""); setA(1); setB("working"); }, [doc?.id]);

  if (!doc) {
    const examples = ctx.docs.filter(d => d.title.startsWith("[Demo Workflow] "));
    return <Pane>
      <h2 className="text-[22px] mb-1">Approval and history</h2>
      <Muted>Select a document to see its approval status, comments, revision history, and audit trail.</Muted>
      <h3 className="text-[17px] mt-5">Demo workflow examples</h3>
      <Muted>Sample Lumora drafts show records at different approval stages. Open one to inspect its decisions and history.</Muted>
      {!examples.length && <Muted>Demo workflow examples will appear here when demo data is enabled.</Muted>}
      <div className="grid gap-2 mt-3">
        {examples.map(d => <div key={d.id} className="border border-ln rounded-md p-3 flex flex-wrap items-center justify-between gap-3">
          <div><b>{d.title.replace("[Demo Workflow] ", "")}</b><div className="mt-1"><StatusPill status={d.status} label={d.status_label} /></div></div>
          <Btn v="s" onClick={() => void ctx.open(d.id, "flow")}>Open approval history</Btn>
        </div>)}
      </div>
    </Pane>;
  }
  const act = async (action: string, n = "", ok = "") => {
    setBusy(true);
    try { const d: Doc = await api.act(doc.id, action, n); ctx.setDoc(d); await ctx.reload(); setNote(""); setCm(""); if (ok) toast(ok); }
    catch (e) { toast(errMsg(e), true); } finally { setBusy(false); }
  };
  const p = doc.perms;
  const hi = doc.findings.filter(f => f.risk === "high");
  const showDiff = async () => {
    try { setOps((await api.diff(doc.id, a, b === "working" ? undefined : b)).ops); } catch (e) { toast(errMsg(e), true); }
  };

  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <Pane>
        <h2 className="text-[22px] mb-1">Approval workflow</h2>
        <Muted>Creators run a review, resolve each finding, then submit. High-risk claims go to an Authorised Reviewer before the Brand Manager; other drafts go to the Brand Manager. Add a note when requesting changes. Comments, saved versions, and the audit trail record the decisions and edits.</Muted>
        <p className="font-semibold">{doc.title}</p>
        <div className="flex items-center gap-2 my-1"><StatusPill status={doc.status} label={doc.status_label} /><span className="text-mut">Version {doc.version}</span></div>
        <ol className="flex flex-wrap gap-1.5 my-3 list-none p-0" aria-label="Workflow steps">
          {STEPS.map((s, i) => <li key={s} aria-current={i === AT[doc.status] ? "step" : undefined}
            className={`px-2.5 py-0.5 text-[13px] rounded border ${i === AT[doc.status] ? "bg-ink text-bg border-ink" : "border-ln"}`}>{s}</li>)}
        </ol>
        <details className="mb-3">
          <summary className="cursor-pointer font-semibold">How approval works</summary>
          <ol className="list-decimal pl-5 mt-2 grid gap-1 text-sm">
            <li>The Creator runs a review, resolves all findings, and submits the draft.</li>
            <li>High-risk claims go to the Authorised Reviewer; other drafts go to the Brand Manager.</li>
            <li>The Reviewer checks the evidence and either clears the claims for the Manager or requests changes with a note.</li>
            <li>The Manager approves the draft or requests changes. Notes explain what needs to change.</li>
            <li>After approval, mark it published. Comments, revisions, and the audit trail record the decisions.</li>
          </ol>
        </details>

        {user.role === "Creator" && (
          <>
            {["draft", "changes_requested"].includes(doc.status) && (
              <>
                <Btn v="g" disabled={busy || !p.submit} onClick={() => act("submit", "", "Submitted.")}>Submit for approval</Btn>
                <Muted>{!doc.run ? "Run a review first." : !doc.fresh ? "The draft changed since the last review. Run it again." : doc.findings.some(f => !f.decision)
                  ? `Decide on ${doc.findings.filter(f => !f.decision).length} open finding(s) first.` : "All findings decided. If a high-risk item is still in the text it goes to an Authorised Reviewer, otherwise to the Brand Manager."}</Muted>
              </>
            )}
            {p.new_revision && <Btn disabled={busy} onClick={() => act("new-revision")}>Start a new revision</Btn>}
            {["pending_reviewer", "pending_manager"].includes(doc.status) && <Muted>Submitted. Waiting for review.</Muted>}
          </>
        )}

        {user.role === "Authorised Reviewer" && (p.reviewer ? (
          <>
            <h3 className="text-[17px]">High-risk items to check</h3>
            {hi.length === 0 && <Muted>None.</Muted>}
            {hi.map(f => (
              <div key={f.id} className="border border-ln rounded-md p-2.5 mt-2">
                <div className="flex gap-1.5 flex-wrap"><Tag sev={f.severity}>{f.severity}</Tag><Tag>{f.category}</Tag></div>
                <p className="font-serif text-base my-1">“{f.text}”</p>
                <p className="text-sm">Source: <b>{f.src}</b>. {f.src_text}</p>
                <p className="text-sm">{f.reason ? <>Creator’s reason: {f.reason}</> : "Fixed by creator."}</p>
              </div>
            ))}
            <Area rows={2} className="mt-3" aria-label="Note" placeholder="Note (required to request changes)" value={note} onChange={e => setNote(e.target.value)} />
            <div className="flex gap-2 mt-2"><Btn v="g" disabled={busy} onClick={() => act("reviewer-clear", note, "Cleared and sent to the Brand Manager.")}>Clear claims and send to manager</Btn>
              <Btn v="r" disabled={busy} onClick={() => act("request-changes", note, "Changes requested.")}>Request changes</Btn></div>
          </>
        ) : <Muted>Nothing is waiting for you on this document.</Muted>)}

        {user.role === "Brand Manager" && (p.manager ? (
          <>
            <p>{doc.findings.filter(f => f.decision).length} disputed finding(s) remain. {doc.versions.at(-1)?.note}.</p>
            <Area rows={2} aria-label="Note" placeholder="Note (required to request changes)" value={note} onChange={e => setNote(e.target.value)} />
            <div className="flex gap-2 mt-2"><Btn v="g" disabled={busy} onClick={() => act("approve", note, "Approved and locked.")}>Approve for publication</Btn>
              <Btn v="r" disabled={busy} onClick={() => act("request-changes", note, "Changes requested.")}>Request changes</Btn></div>
          </>
        ) : p.publish ? <Btn v="g" disabled={busy} onClick={() => act("publish", "", "Marked as published.")}>Mark as published</Btn>
          : <Muted>Nothing is waiting for you on this document.</Muted>)}

        {user.role === "Brand Admin" && <Muted>Admins manage the brand kit and insights. Approvals stay with the Brand Manager and the Authorised Reviewer.</Muted>}

        <h3 className="text-[17px] mt-5">Comments</h3>
        {doc.comments.map((c, i) => <p key={i} className="my-2"><b>{c.user}</b> <span className="text-mut text-sm">{c.role}, {when(c.at)}</span><br />{c.text}</p>)}
        {!doc.comments.length && <Muted>No comments yet.</Muted>}
        <div className="flex gap-2 mt-2"><Input aria-label="Comment" placeholder="Add a comment" value={cm} onChange={e => setCm(e.target.value)} />
          <Btn v="s" disabled={busy || !cm.trim()} onClick={() => act("comment", cm)}>Post</Btn></div>
      </Pane>

      <Pane>
        <h2 className="text-[22px] mb-1">Revision history</h2>
        <details className="mb-2">
          <summary className="cursor-pointer font-semibold">How to read revision history</summary>
          <ol className="list-decimal pl-5 mt-2 grid gap-1 text-sm">
            <li>Each saved version shows when it was created, who created it, and any note.</li>
            <li>Open View text to inspect the full saved draft.</li>
            <li>Choose a starting version under From.</li>
            <li>Choose another saved version or current text under to, then select Show changes.</li>
            <li>Use the audit trail below to see who took each action and when.</li>
          </ol>
        </details>
        {!doc.versions.length && <Muted>Submit a draft to create version 1.</Muted>}
        {doc.versions.map(v => (
          <div key={v.version} className="border border-ln rounded-md p-2.5 mt-2">
            <b>Version {v.version}</b> <span className="text-mut text-sm">{when(v.at)} by {v.by}</span><br />{v.note}
            <details><summary className="cursor-pointer text-sm">View text</summary><pre className="whitespace-pre-wrap text-[12.5px] bg-bg p-2 rounded overflow-auto">{v.text}</pre></details>
          </div>
        ))}
        {doc.versions.length > 0 && (
          <div className="mt-4">
            <h3 className="text-[17px]">Compare versions</h3>
            <div className="flex flex-wrap items-center gap-2 mt-1">
              <label className="text-sm">From <select value={a} onChange={e => setA(+e.target.value)} className="bg-bg border border-ln rounded px-1.5 py-1">{doc.versions.map(v => <option key={v.version} value={v.version}>v{v.version}</option>)}</select></label>
              <label className="text-sm">to <select value={b} onChange={e => setB(e.target.value === "working" ? "working" : +e.target.value)} className="bg-bg border border-ln rounded px-1.5 py-1">
                <option value="working">current text</option>{doc.versions.map(v => <option key={v.version} value={v.version}>v{v.version}</option>)}</select></label>
              <Btn v="s" onClick={showDiff}>Show changes</Btn>
            </div>
            {ops && <div className="mono whitespace-pre-wrap bg-bg border border-ln rounded-md p-2.5 mt-2 max-h-72 overflow-auto" aria-label="Differences">
              {ops.every(o => o.op === "equal") && <span className="text-mut">No differences.</span>}
              {ops.map((o, i) => o.op === "equal" ? <span key={i}>{o.text}</span> :
                o.op === "insert" ? <ins key={i} className="bg-okb text-ok no-underline">{o.text}</ins> : <del key={i} className="bg-hib text-hi">{o.text}</del>)}
            </div>}
          </div>
        )}
        <h3 className="text-[17px] mt-5">This document’s audit trail</h3>
        <div className="overflow-x-auto"><table><thead><tr><th>Time</th><th>Who</th><th>Action</th></tr></thead>
          <tbody>{trail.map(t => <tr key={t.seq}><td className="text-mut whitespace-nowrap">{when(t.at)}</td><td>{t.user}<div className="text-xs text-mut">{t.role}</div></td><td><b>{t.action}</b><div className="text-sm text-mut break-words">{t.detail}</div></td></tr>)}</tbody></table></div>
      </Pane>
    </div>
  );
}
