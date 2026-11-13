import { useQuery } from "@tanstack/react-query";
import { ArrowUpRight, CircleCheck, CircleX } from "lucide-react";
import { Disclaimer, Empty, ErrorState, PageSkeleton, RTable, Section, Stat } from "../components/ui";
import { api, num, pct } from "../lib/api";

const METRICS: [string, string, string][] = [
  ["Brier skill score (BSS) vs climatology", "Primary score for the 3-month outlook. 0 = no better than always saying 33%; > 0 = adds information. Reported with a 90% block-bootstrap interval over years.", "Seasonal outlook"],
  ["BSS vs persistence", "Does the model beat 'the next 3 months will be like the last 3'? A model must beat both baselines to be trusted.", "Seasonal outlook"],
  ["Reliability diagram & ECE", "Calibration: when the model says 60%, below-normal rain should happen about 60% of the time. ECE is the average gap.", "Seasonal outlook"],
  ["ROC AUC / PR AUC", "Discrimination: can it rank dry seasons above wet ones? PR AUC is more honest when the event is a 1-in-3.", "Seasonal outlook"],
  ["POD, FAR, CSI", "At the warning threshold: share of dry seasons warned (POD), share of warnings that were false (FAR), and the combined critical success index.", "Outlook & 7-day watch"],
  ["Peirce (Hanssen–Kuipers) & Heidke skill", "POD minus false-alarm rate, and accuracy beyond chance. Fair for uncommon events, unlike plain accuracy.", "Outlook & 7-day watch"],
  ["Relative economic value", "For a user whose preparation costs C and avoided loss is L: how much of a perfect forecast's savings does acting on this forecast capture? Turns skill into 'is it worth acting on?'.", "Decision value"],
  ["RPSS", "Ranked probability skill score; used if the outlook is extended to all three terciles (below / near / above normal).", "Future 3-category outlook"],
  ["Rain-after-drought hit rate & blind spot", "Did the compound alert fire during documented rain-after-drought disasters, and how often had the standard 3-month drought indicator already gone back to 'Normal' when the rain hit?", "Compound alert"],
  ["Event hit rate & lead time", "Do the drought and heavy-rain indicators reach Watch+ during documented disasters (ReliefWeb / IFRC), and how early?", "Hazard indicators"],
  ["Validator pass rate, citation coverage, approval rate", "Share of drafts passing the number/citation validator, share of numeric sentences that cite a tool, and share of reviewed drafts a human approved.", "Advisory agent"],
];

export function Evidence() {
  const val = useQuery({ queryKey: ["validation"], queryFn: api.validation });
  const model = useQuery({ queryKey: ["model"], queryFn: api.model });
  const agent = useQuery({ queryKey: ["agentMetrics"], queryFn: api.agentMetrics });
  const wl = useQuery({ queryKey: ["whiplash"], queryFn: api.whiplash });
  const nd = useQuery({ queryKey: ["ndma"], queryFn: api.ndma });
  if (val.isPending) return <PageSkeleton />;
  if (val.isError) return <div className="page"><ErrorState error={val.error} retry={() => val.refetch()} /></div>;
  const ev = val.data.events.filter((e) => e.hazard !== "whiplash"); // compound events have their own section
  const matched = ev.filter((e) => e.result === "matched").length;
  const card = model.data?.active;
  return (
    <div className="page grid gap-8">
      <header className="grid gap-2">
        <h1>Evidence & model card</h1>
        <p className="muted max-w-[70ch]">How we know the indicators and the outlook are worth listening to, and where they are not.</p>
      </header>

      <Section title="Do the indicators catch real disasters?">
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Stat label="County-events matched" value={`${matched}/${ev.length}`} hint={pct(ev.length ? matched / ev.length : null)} tone="var(--accent)" />
          <Stat label="Documented events" value={val.data.reference_events.length} hint="IFRC / ReliefWeb / NDMA" />
        </div>
        <RTable
          stack
          rows={ev}
          rowKey={(_, i) => String(i)}
          cols={[
            { key: "e", header: "Event", primary: true, cell: (e) => <span className="num">{String(e.event)} · {String(e.county)}</span> },
            { key: "c", header: "County", cell: (e) => String(e.county), hideOnMobile: true },
            { key: "w", header: "Window", className: "num text-sm", cell: (e) => String(e.window) },
            { key: "r", header: "Result", cell: (e) => <span className="chip">{e.result === "matched" ? <CircleCheck size={14} aria-hidden /> : <CircleX size={14} aria-hidden />} {String(e.result)}</span> },
            { key: "i", header: "Indicator", className: "text-sm", cell: (e) => String(e.indicator_detail) },
            { key: "s", header: "Source", className: "text-sm", cell: (e) => <a href={String(e.url)} target="_blank" rel="noreferrer">{String(e.source)} <ArrowUpRight size={12} className="inline" /></a> },
          ]}
        />
      </Section>

      <Section title="Rain after drought: the risk single-hazard indicators miss">
        <p className="muted max-w-[75ch]">
          Heavy rain on drought-hit land is more dangerous than the same rain after a normal year: hard, bare ground sheds
          water, weakened livestock are lost and water sources are contaminated. Drought indicators switch to "Normal" as
          soon as it rains, and flood indicators ignore what came before, so neither flags it. Rule (fixed before
          validation): 3-day rain at the county's own p95 / p99 / p99.9 when the previous 12 months had at most 75% of
          normal rain.
        </p>
        {wl.data ? (
          <>
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              <Stat
                label="Drought indicator said 'Normal'"
                value={wl.data.stats.blind_spot_drought_indicator_normal_pct != null ? `${wl.data.stats.blind_spot_drought_indicator_normal_pct}%` : "–"}
                hint="of rain-after-drought episodes since 1991, when the rain hit"
                tone="var(--lvl-warning)"
              />
              <Stat
                label="1-in-100-day rains on drought-hit land"
                value={wl.data.stats.p99_rain_days_on_drought_land_pct != null ? `${wl.data.stats.p99_rain_days_on_drought_land_pct}%` : "–"}
                hint={`${wl.data.stats.p99_rain_days ?? "–"} such rain days, 14 counties`}
              />
              <Stat
                label="Documented events caught"
                value={`${wl.data.validation.filter((e) => e.result === "matched").length}/${wl.data.validation.length}`}
                hint={`+${wl.data.validation.filter((e) => String(e.result).startsWith("partial")).length} at Watch only`}
                tone="var(--accent)"
              />
              <Stat
                label="Alerts per county per decade"
                value={wl.data.stats.warning_plus_per_county_decade ?? "–"}
                hint={`at Warning+ (${wl.data.stats.episodes_per_county_decade ?? "–"} incl. Watch)`}
              />
            </div>
            <RTable
              stack
              rows={wl.data.validation}
              rowKey={(_, i) => `wv${i}`}
              cols={[
                { key: "e", header: "Event", primary: true, cell: (e) => <span className="num">{String(e.event)} · {String(e.county)}</span> },
                { key: "r", header: "Result", cell: (e) => <span className="chip">{e.result === "matched" ? <CircleCheck size={14} aria-hidden /> : <CircleX size={14} aria-hidden />} {String(e.result)}</span> },
                { key: "i", header: "Indicator", className: "text-sm", cell: (e) => String(e.indicator_detail) },
                { key: "s", header: "Source", className: "text-sm", cell: (e) => <a href={String(e.url)} target="_blank" rel="noreferrer">{String(e.source)} <ArrowUpRight size={12} className="inline" /></a> },
              ]}
            />
            {wl.data.sensitivity.length > 0 && (
              <>
                <h3>Was the rule tuned to these events? Sensitivity of the two settings</h3>
                <RTable
                  rows={wl.data.sensitivity}
                  rowKey={(r) => `${r.antecedent_months}-${r.dry_pct}`}
                  cols={[
                    { key: "a", header: "Look-back", primary: true, cell: (r) => `${r.antecedent_months} months${r.published_rule ? " (published rule)" : ""}` },
                    { key: "d", header: "Dry if at most", className: "num", cell: (r) => `${r.dry_pct}% of normal` },
                    { key: "m", header: "Matched / partial", className: "num", cell: (r) => `${r.matched} / ${r.partial} of ${r.county_events}` },
                    { key: "f", header: "Episodes per county-decade", className: "num", cell: (r) => String(r.episodes_per_county_decade) },
                  ]}
                />
                <p className="subtle">Looser settings catch more events but alert far more often; the published rule sits in the middle and was chosen before validation.</p>
              </>
            )}
          </>
        ) : wl.isError ? (
          <Empty>Rain-after-drought outputs not built yet. Run <code>python run_all.py --offline</code>.</Empty>
        ) : null}
      </Section>

      <Section title="Independent check: NDMA official drought phases">
        <p className="muted max-w-[75ch]">
          Month by month, our rainfall-only drought level against the phase in NDMA's county Drought Early Warning
          bulletins (Watch ~ Alert, Warning ~ Alarm, Emergency ~ Emergency). NDMA also weighs vegetation, livestock,
          water access and nutrition, so it often stays in Alert or Alarm after the rain has returned. Months with no
          readable bulletin, NDMA "Recovery" months and our dry-season months are left out.
        </p>
        {nd.data && nd.data.agreement.length > 0 ? (
          <>
            <RTable
              rows={nd.data.agreement}
              rowKey={(r) => String(r.county)}
              cols={[
                { key: "c", header: "County", primary: true, cell: (r) => <span className={r.county === "ALL" ? "font-semibold" : undefined}>{String(r.county)}</span> },
                { key: "n", header: "Months compared", className: "num", cell: (r) => String(r.months_compared) },
                { key: "e", header: "Exact", className: "num", cell: (r) => (r.exact_agreement_pct == null ? "–" : `${r.exact_agreement_pct}%`) },
                { key: "w", header: "Within one level", className: "num", cell: (r) => (r.within_one_level_pct == null ? "–" : `${r.within_one_level_pct}%`) },
                { key: "b", header: "If always 'Normal'", className: "num", hideOnMobile: true, cell: (r) => (r.always_normal_baseline_pct == null ? "–" : `${r.always_normal_baseline_pct}%`) },
                { key: "t", header: "NDMA escalations: we earlier / same / later / missed", className: "num", cell: (r) => `${r.we_earlier} / ${r.same_month} / ${r.we_later} / ${r.not_matched}` },
              ]}
            />
            <p className="subtle">
              Source: {String(nd.data.overall.source ?? "NDMA bulletins")}, {String(nd.data.overall.period ?? "")}. "If always 'Normal'"
              is the agreement a forecaster would get by never warning; "earlier / later" compares the month NDMA raised the
              phase with the first month (within 3 either side) that our indicator reached the same level.
            </p>
          </>
        ) : nd.isPending ? null : (
          <Empty>NDMA comparison not built yet. Run <code>python scripts/ndma_compare.py</code>.</Empty>
        )}
      </Section>

      <Section title="Seasonal outlook model card">
        {model.isPending ? null : card ? (
          <div className="card grid gap-3">
            <div className="flex flex-wrap gap-2">
              <span className="chip">Active: {card.version}</span>
              <span className="chip">{card.model.kind} · {card.model.feature_set} · calibration {String(card.model.calibration ?? "none")}</span>
              <span className="chip">threshold {card.model.threshold}</span>
              {card.git_sha && <span className="chip num">git {card.git_sha}</span>}
            </div>
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              <Stat label="Test BSS" value={num(card.test.bss_vs_climatology, 3)} hint={`90% CI [${num(card.test.bss_90ci?.[0], 3)}, ${num(card.test.bss_90ci?.[1], 3)}]`} />
              <Stat label="ROC AUC" value={num(card.test.roc_auc, 2)} />
              <Stat label="ECE" value={num(card.test.ece, 3)} />
              <Stat label="Peirce skill" value={num(card.test.cat_pss, 2)} hint={`POD ${pct(card.test.cat_pod)} · FAR ${pct(card.test.cat_far)}`} />
            </div>
            <p className="subtle">
              Trained {card.saved_utc} on {card.data.n_train} issue-months (CV folds {card.cv.folds.join(", ")}; {card.cv.n_trials} Optuna trials), tested once on {card.data.n_test} from {card.data.test_start}. Promotion: {card.promotion?.reason ?? "–"}.
            </p>
          </div>
        ) : (
          <Empty>
            No trained model promoted yet; the pipeline picks between logistic regression and gradient boosting inline
            ({model.data?.pipeline_model_source ?? "inline selection"}). Train one locally with <code>python -m sentinel.train</code> or in Google Colab.
          </Empty>
        )}
      </Section>

      <Section title="Advisory agent quality">
        {agent.data && agent.data.n_runs ? (
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat label="Validator pass rate" value={pct(agent.data.validator_pass_rate)} hint={`${agent.data.n_runs} drafts`} />
            <Stat label="Citation coverage" value={pct(agent.data.citation_coverage)} hint="numeric sentences citing a tool" />
            <Stat label="Approval rate" value={pct(agent.data.approval_rate)} hint={`${agent.data.reviewed} reviewed`} />
            <Stat label="Median latency" value={agent.data.median_latency_s == null ? "–" : `${num(agent.data.median_latency_s, 1)} s`} />
          </div>
        ) : (
          <Empty>No advisory drafts logged yet.</Empty>
        )}
      </Section>

      <Section title="Which metrics, and why">
        <RTable
          stack
          rows={METRICS}
          rowKey={([m]) => m}
          cols={[
            { key: "m", header: "Metric", primary: true, className: "font-semibold", cell: ([m]) => m },
            { key: "d", header: "What it tells a county manager", className: "text-sm", cell: ([, d]) => <span className="block text-left">{d}</span> },
            { key: "u", header: "Used for", className: "text-sm muted", cell: ([, , u]) => u },
          ]}
        />
        <p className="subtle">Every metric is also broken down by county and by season (Mar–May long rains vs Oct–Dec short rains), because ENSO and the Indian Ocean Dipole mostly drive the short rains.</p>
      </Section>
      <Disclaimer text="Planning-support tool, not an official warning system." />
    </div>
  );
}
