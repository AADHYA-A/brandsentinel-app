import { api } from "../api";
import type { Ctx } from "../App";
import { Btn, Muted, Pane, StatusPill, Tag, errMsg, useToast, when } from "../ui";

export default function Documents({ ctx }: { ctx: Ctx }) {
  const toast = useToast();
  const { user, docs } = ctx;
  const waiting = docs.filter(d => d.mine_to_review);
  const newDraft = async () => {
    try { const d = await api.createDoc({ title: "Untitled draft", text: "", team: user.team }); ctx.setDoc(d); await ctx.reload(); ctx.go("review"); }
    catch (e) { toast(errMsg(e), true); }
  };
  const Row = ({ d }: { d: typeof docs[number] }) => (
    <tr>
      <td><button onClick={() => ctx.open(d.id)} className="underline text-left cursor-pointer font-semibold">{d.title}</button>
        <div className="text-mut text-xs">{d.source_type} · {d.creator} · {d.team || "no team"}{d.local_only ? " · local-only" : ""}</div></td>
      <td><StatusPill status={d.status} label={d.status_label} /></td>
      <td>{d.high_risk > 0 ? <Tag sev="High">{d.high_risk} high-risk</Tag> : <span className="text-mut">none</span>}</td>
      <td>{d.open > 0 ? `${d.open} open` : d.finding_count ? "all decided" : "not reviewed"}</td>
      <td className="text-mut">v{d.version}</td>
      <td className="text-mut">{when(d.updated_at)}</td>
    </tr>
  );
  const Table = ({ rows }: { rows: typeof docs }) => (
    <div className="overflow-x-auto"><table><thead><tr><th>Document</th><th>Status</th><th>Risk</th><th>Findings</th><th>Version</th><th>Updated</th></tr></thead>
      <tbody>{rows.map(d => <Row key={d.id} d={d} />)}</tbody></table></div>
  );
  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-[22px]">{user.role === "Creator" ? "My drafts" : "Review queue"}</h2>
        {user.role === "Creator" && <Btn v="g" onClick={newDraft}>New draft</Btn>}
      </div>
      {waiting.length > 0 && (
        <Pane><h3 className="text-[17px] mb-1">Waiting for you</h3><Muted>Highest risk first, then oldest.</Muted><Table rows={waiting} /></Pane>
      )}
      <Pane>
        <h3 className="text-[17px] mb-1">{waiting.length ? "Everything else" : "All documents"}</h3>
        {docs.filter(d => !d.mine_to_review).length ? <Table rows={docs.filter(d => !d.mine_to_review)} /> :
          <Muted>{user.role === "Creator" ? "No drafts yet. Start one, upload a file, or load the sample on the Review tab." : "Nothing here yet."}</Muted>}
      </Pane>
    </div>
  );
}
