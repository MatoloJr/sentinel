import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Ban, CheckCircle2, KeyRound, Printer, Send, ShieldAlert, ShieldCheck, Wrench, XCircle } from "lucide-react";
import { Fragment, useEffect, useState, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";
import { CopyButton } from "../components/InsightPanel";
import { Empty, ErrorState, Section, Skeleton } from "../components/ui";
import { api, type AgentRun, type ToolCall } from "../lib/api";
import { store, useApp } from "../lib/state";

const STATUS: Record<AgentRun["status"], { label: string; icon: typeof CheckCircle2 }> = {
  draft: { label: "Draft · awaiting human approval", icon: ShieldCheck },
  blocked: { label: "Blocked by validator", icon: ShieldAlert },
  approved: { label: "Approved", icon: CheckCircle2 },
  rejected: { label: "Rejected", icon: XCircle },
};

/** Minimal, safe markdown: headings, bold/italic, bullets, rules and clickable [T#] citations. */
function renderInline(text: string, onCite: (id: string) => void): ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*|\*[^*]+\*|\[T\d+\])/g);
  return parts.map((p, i) => {
    if (/^\*\*[^*]+\*\*$/.test(p)) return <strong key={i}>{p.slice(2, -2)}</strong>;
    if (/^\*[^*]+\*$/.test(p)) return <em key={i}>{p.slice(1, -1)}</em>;
    const m = p.match(/^\[(T\d+)\]$/);
    if (m)
      return (
        <button key={i} onClick={() => onCite(m[1])} className="chip num mx-0.5 align-baseline" style={{ padding: "0 7px", background: "var(--accent-soft)", color: "var(--accent)" }} title="Show the tool result behind this number">
          {m[1]}
        </button>
      );
    return <Fragment key={i}>{p}</Fragment>;
  });
}

function Markdown({ text, onCite }: { text: string; onCite: (id: string) => void }) {
  const lines = text.split("\n");
  const out: ReactNode[] = [];
  let list: ReactNode[] = [];
  const flush = () => {
    if (list.length) out.push(<ul key={`u${out.length}`} className="ml-5 list-disc grid gap-1">{list}</ul>);
    list = [];
  };
  lines.forEach((raw, i) => {
    const l = raw.trim();
    if (/^[-*] /.test(l)) return list.push(<li key={i}>{renderInline(l.slice(2), onCite)}</li>);
    flush();
    if (!l) return;
    if (l === "---") return out.push(<hr key={i} style={{ borderColor: "var(--surface-3)" }} />);
    if (/^#{1,4} /.test(l)) return out.push(<h3 key={i} className="mt-2">{renderInline(l.replace(/^#+ /, ""), onCite)}</h3>);
    if (/^\*\*[^*]+\*\*:?$/.test(l)) return out.push(<h3 key={i} className="mt-2">{l.replace(/\*\*/g, "").replace(/:$/, "")}</h3>);
    out.push(<p key={i}>{renderInline(l, onCite)}</p>);
  });
  flush();
  return <div className="grid gap-2 leading-relaxed">{out}</div>;
}

const plain = (s: string) => s.replace(/\s?\[T\d+\]/g, "").replace(/\*\*/g, "").replace(/\n---[\s\S]*$/, "").trim();

export function Advisory() {
  const [params] = useSearchParams();
  const qc = useQueryClient();
  const { setAgentBusy } = useApp();
  const [question, setQuestion] = useState(params.get("q") ?? "");
  const [run, setRun] = useState<AgentRun | null>(null);
  const [openTool, setOpenTool] = useState<string | null>(null);
  const health = useQuery({ queryKey: ["health"], queryFn: api.health });
  const ins = useQuery({ queryKey: ["insights"], queryFn: api.insights });
  const runs = useQuery({ queryKey: ["runs"], queryFn: api.runs });

  const ask = useMutation({
    mutationFn: api.ask,
    onMutate: () => setAgentBusy(true),
    onSettled: () => setAgentBusy(false),
    onSuccess: (r) => {
      setRun(r);
      qc.invalidateQueries({ queryKey: ["runs"] });
    },
  });
  useEffect(() => {
    const q = params.get("q");
    if (q) setQuestion(q);
    const id = params.get("run");
    if (id) api.run(id).then(setRun).catch(() => undefined);
  }, [params]);

  const top = ins.data?.region.top_priorities ?? [];
  const suggestions = [
    ...top.slice(0, 2).map((c) => `Prepare an advisory for ${c} county.`),
    "Will the short rains fail in Wajir?",
    "Where will the next cyclone make landfall near Lamu?",
    "Is there any risk in Kisumu this week?",
  ];

  const onCite = (id: string) => {
    setOpenTool(id);
    setTimeout(() => document.getElementById(`tool-${id}`)?.scrollIntoView({ behavior: "smooth", block: "center" }), 30);
  };

  return (
    <div className="page grid gap-6">
      <header className="grid gap-2">
        <h1>Draft an advisory</h1>
        <p className="muted max-w-[70ch]">
          Gemini answers only from the system's own tools. Every number must cite a tool result, a validator blocks
          invented numbers or downplayed risk, actions come only from the playbook, and a person approves before release.
        </p>
      </header>

      {health.data && !health.data.gemini_configured && (
        <div className="card flex items-start gap-3" role="status">
          <KeyRound size={18} className="mt-0.5 shrink-0" aria-hidden />
          <p className="text-sm">
            No Gemini key on the server. Add <code>GEMINI_API_KEY=…</code> to <code>.env</code> (free key at aistudio.google.com/apikey) and restart the API.
          </p>
        </div>
      )}

      <form
        className="card grid gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (question.trim().length >= 3) ask.mutate(question.trim());
        }}
      >
        <label htmlFor="q" className="subtle font-semibold">Question</label>
        <textarea
          id="q"
          className="input py-3"
          rows={3}
          maxLength={1000}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="e.g. Prepare an advisory for Turkana county."
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) (e.currentTarget.form as HTMLFormElement).requestSubmit();
          }}
        />
        <div className="flex flex-wrap gap-2">
          {suggestions.map((s) => (
            <button type="button" key={s} className="chip" style={{ minHeight: 36 }} onClick={() => setQuestion(s)}>
              {s}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-3">
          <button className="btn btn-accent" disabled={ask.isPending || question.trim().length < 3}>
            <Send size={16} /> {ask.isPending ? "Drafting…" : "Draft advisory"}
          </button>
          <span className="subtle">Ctrl + Enter</span>
        </div>
      </form>

      {ask.isPending && (
        <div className="card grid gap-3" aria-busy="true">
          <Skeleton h={20} w="50%" />
          <Skeleton h={14} />
          <Skeleton h={14} w="90%" />
          <Skeleton h={14} w="70%" />
        </div>
      )}
      {ask.isError && <ErrorState error={ask.error} retry={() => ask.mutate(question.trim())} />}
      {run && !ask.isPending && <RunView run={run} setRun={setRun} openTool={openTool} setOpenTool={setOpenTool} onCite={onCite} />}

      <Section title="History">
        {runs.isPending ? (
          <Skeleton h={80} />
        ) : !runs.data?.length ? (
          <Empty>No advisories yet.</Empty>
        ) : (
          <ul className="grid gap-2">
            {runs.data.slice(0, 20).map((r) => {
              const S = STATUS[r.status] ?? STATUS.draft;
              return (
                <li key={r.run_id}>
                  <button
                    className="card flex w-full items-center justify-between gap-3 text-left"
                    style={{ padding: 12 }}
                    onClick={async () => setRun(await api.run(r.run_id))}
                  >
                    <span className="min-w-0">
                      <span className="block truncate font-medium">{r.question}</span>
                      <span className="subtle">{new Date(r.started_utc).toLocaleString()} · {r.n_tool_calls} tool calls</span>
                    </span>
                    <span className="chip shrink-0"><S.icon size={14} aria-hidden /> {r.status}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </Section>
    </div>
  );
}

function RunView({
  run, setRun, openTool, setOpenTool, onCite,
}: {
  run: AgentRun;
  setRun: (r: AgentRun) => void;
  openTool: string | null;
  setOpenTool: (id: string | null) => void;
  onCite: (id: string) => void;
}) {
  const qc = useQueryClient();
  const [approver, setApprover] = useState(() => store.get("cs.approver", ""));
  const [note, setNote] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const S = STATUS[run.status];
  const review = async (kind: "approve" | "reject") => {
    setErr(null);
    store.set("cs.approver", approver);
    try {
      const r = kind === "approve" ? await api.approve(run.run_id, approver, note) : await api.reject(run.run_id, approver, note);
      setRun(r);
      qc.invalidateQueries({ queryKey: ["runs"] });
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  };
  const blocked = run.status === "blocked";
  return (
    <div className="grid gap-4 rise">
      <div className="card grid gap-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="chip" style={{ background: blocked ? "var(--lvl-warning)" : "var(--accent-soft)", color: blocked ? "#fff" : "var(--accent)" }}>
            <S.icon size={14} aria-hidden /> {S.label}
          </span>
          <span className="subtle">{run.model} · {run.tool_calls.length} tool calls · {run.validation.numbers_checked} numbers checked</span>
        </div>
        <p className="subtle">Q: {run.question}</p>
        <Markdown text={run.advisory} onCite={onCite} />
        {run.validation.issues.length > 0 && (
          <div className="rounded-xl p-3 text-sm" style={{ background: "color-mix(in oklab, var(--lvl-warning) 14%, transparent)" }}>
            <b>Validator issues</b>
            <ul className="ml-5 list-disc">
              {run.validation.issues.map((i) => <li key={i}>{i}</li>)}
            </ul>
          </div>
        )}
        <div className="no-print flex flex-wrap gap-2">
          <CopyButton text={plain(run.answer_draft)} label="Copy for radio / SMS" />
          <button className="btn" onClick={() => window.print()}><Printer size={16} /> Print</button>
        </div>
      </div>

      <Section title="Evidence: logged tool calls">
        <div className="grid gap-2">
          {run.tool_calls.map((t) => <ToolRow key={t.id} t={t} open={openTool === t.id} toggle={() => setOpenTool(openTool === t.id ? null : t.id)} />)}
        </div>
      </Section>

      <div className="card no-print grid gap-3">
        <h3>Human review</h3>
        {run.approval ? (
          <p className="text-sm">{Object.entries(run.approval).map(([k, v]) => `${k.replaceAll("_", " ")}: ${v}`).join(" · ")}</p>
        ) : (
          <>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="grid gap-1">
                <span className="subtle font-semibold">Your name</span>
                <input className="input" value={approver} onChange={(e) => setApprover(e.target.value)} placeholder="County DRM officer" />
              </label>
              <label className="grid gap-1">
                <span className="subtle font-semibold">Note (optional)</span>
                <input className="input" value={note} onChange={(e) => setNote(e.target.value)} />
              </label>
            </div>
            <div className="flex flex-wrap gap-2">
              <button className="btn btn-accent" disabled={blocked || !approver.trim()} onClick={() => review("approve")}>
                <CheckCircle2 size={16} /> Approve for release
              </button>
              <button className="btn" disabled={!approver.trim()} onClick={() => review("reject")}>
                <Ban size={16} /> Reject
              </button>
            </div>
            {blocked && <p className="subtle">Blocked drafts cannot be approved. Rephrase the question and draft again.</p>}
            {err && <p role="alert" className="text-sm" style={{ color: "var(--lvl-emergency)" }}>{err}</p>}
          </>
        )}
      </div>
    </div>
  );
}

function ToolRow({ t, open, toggle }: { t: ToolCall; open: boolean; toggle: () => void }) {
  return (
    <div id={`tool-${t.id}`} className="card" style={{ padding: 0, outline: open ? "2px solid var(--accent)" : undefined }}>
      <button onClick={toggle} aria-expanded={open} className="flex w-full items-center justify-between gap-3 p-3 text-left" style={{ minHeight: 44 }}>
        <span className="flex min-w-0 items-center gap-2">
          <Wrench size={14} aria-hidden />
          <b className="num">{t.id}</b>
          <span className="truncate">{t.name}({Object.values(t.args).map(String).join(", ")})</span>
        </span>
        <span className="subtle num shrink-0">{t.ms} ms</span>
      </button>
      {open && (
        <pre className="scroll-x m-0 max-h-80 overflow-y-auto rounded-b-[18px] p-3 text-xs" style={{ background: "var(--surface)" }}>
          {JSON.stringify(t.result, null, 2)}
        </pre>
      )}
    </div>
  );
}
