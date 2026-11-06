import { useEffect, useState } from "react";
import { api } from "../api";
import type { Ctx } from "../App";
import { Btn, Muted, Pane, Tag, errMsg, useToast } from "../ui";

export default function Insights({ ctx }: { ctx: Ctx }) {
  const toast = useToast();
  const [d, setD] = useState<any>(null);
  const [ev, setEv] = useState<any>(null);
  const load = () => api.insights().then(setD).catch(e => toast(errMsg(e), true));
  useEffect(() => { load(); }, []);  // eslint-disable-line
  const runEval = async () => { try { setEv(await api.evaluate()); } catch (e) { toast(errMsg(e), true); } };
  if (!d) return <Muted>Loading…</Muted>;
  const k = d.kpis;
  const Met = ({ label, v, target, ok }: { label: string; v: string; target: string; ok?: boolean }) => (
    <tr><td>{label}</td><td>{v}</td><td className="text-mut">{target}</td><td>{ok === undefined ? "" : ok ? <Tag sev="Low">Met</Tag> : <Tag sev="High">Not met</Tag>}</td></tr>);
  return (
    <div className="grid gap-4">
      <Pane>
        <div className="flex flex-wrap items-center gap-2"><h2 className="text-[22px] mr-auto">Governance insights</h2>
          {ctx.user.role === "Brand Admin" && d.decisions === 0 && <Btn v="s" onClick={async () => { try { await api.demoActivity(); await load(); toast("Demo activity added."); } catch (e) { toast(errMsg(e), true); } }}>Add demo activity</Btn>}</div>
        <Muted>Guideline-clarity score: a rule that creators often dispute may be unclear or wrong. Counts come from creator decisions ({d.decisions} so far).</Muted>
        <div className="overflow-x-auto"><table><thead><tr><th>Source</th><th>Category</th><th>Accepted or edited</th><th>Disputed</th><th>Dispute rate</th><th>Clarity score</th><th>Hint</th></tr></thead>
          <tbody>{d.clarity.map((c: any) => <tr key={c.src}><td className="font-semibold">{c.src}</td><td>{c.category}</td><td>{c.accepted}</td><td>{c.disputed}</td><td>{c.dispute_rate}%</td>
            <td>{c.clarity_score}/100</td><td>{c.flag && <Tag sev="Medium">{c.hint}</Tag>}</td></tr>)}
            {!d.clarity.length && <tr><td colSpan={7} className="text-mut">Make decisions on findings to see patterns.</td></tr>}</tbody></table></div>
      </Pane>
      <Pane>
        <h2 className="text-[22px]">Recurring mistakes by team</h2>
        <div className="overflow-x-auto"><table><thead><tr><th>Team</th><th>Rule</th><th>Category</th><th>Times</th></tr></thead>
          <tbody>{d.recurring.map((r: any, i: number) => <tr key={i}><td>{r.team}</td><td>{r.src}</td><td>{r.category}</td><td>{r.count}</td></tr>)}
            {!d.recurring.length && <tr><td colSpan={4} className="text-mut">Nothing yet.</td></tr>}</tbody></table></div>
      </Pane>
      <Pane>
        <h2 className="text-[22px]">Stale-fact alerts</h2>
        <div className="overflow-x-auto"><table><thead><tr><th>Fact</th><th>Valid to</th><th>Alert</th></tr></thead>
          <tbody>{d.stale.map((s: any) => <tr key={s.rid}><td>{s.rid}: {s.text}</td><td>{s.valid_to}</td>
            <td>{s.state === "expired" ? `Expired ${-s.days} days ago. ` : s.state === "expiring" ? `Expires in ${s.days} days. ` : "Current"}{s.action}</td></tr>)}</tbody></table></div>
      </Pane>
      <Pane>
        <h2 className="text-[22px]">Review time and rounds</h2>
        <Muted>{k.approved_documents} approved document(s) in this workspace. Median time from submission to approval: {k.median_days_to_approve === null ? "n/a" : `${k.median_days_to_approve} days`}
          (baseline {k.baseline_days} days). Average rounds: {k.avg_rounds ?? "n/a"} (baseline {k.baseline_rounds}). {k.note}</Muted>
      </Pane>
      <Pane>
        <div className="flex items-center gap-2"><h2 className="text-[22px] mr-auto">Evaluation on the labelled test set</h2><Btn v="s" onClick={runEval}>Run evaluation</Btn></div>
        {ev ? (
          <>
            <Muted>{ev.snippets} labelled snippets written by the author. {ev.scope} The set was written alongside the rules, so treat these numbers as a regression check, not as a measure of accuracy on real content.</Muted>
            <table><thead><tr><th>Metric</th><th>Result</th><th>Target</th><th></th></tr></thead><tbody>
              <Met label="Issue recall" v={`${ev.recall}%`} target="85% or more" ok={ev.recall >= 85} />
              <Met label="Precision" v={`${ev.precision}%`} target="80% or more" ok={ev.precision >= 80} />
              <Met label="Citation validity" v={`${ev.citation_validity}%`} target="95% or more" ok={ev.citation_validity >= 95} />
              <Met label="Hallucinated claims" v={String(ev.hallucinated_claims)} target="0" ok={ev.hallucinated_claims === 0} />
              <Met label="Time to findings" v={`${ev.ms_per_snippet} ms per snippet`} target={`Manual baseline: ${ev.manual_baseline_days} days`} />
            </tbody></table>
            {[...ev.misses.map((m: any) => `Missed ${m.missing}: ${m.text}`), ...ev.unexpected.map((m: any) => `Unexpected ${m.unexpected}: ${m.text}`)].map(s => <p key={s} className="text-sm text-mut">{s}</p>)}
          </>
        ) : <Muted>Runs the rule engine over 60 labelled snippets against the current brand kit.</Muted>}
      </Pane>
    </div>
  );
}
