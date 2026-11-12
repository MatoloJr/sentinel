"""Early-warning agent: tool-calling loop, evidence validator, run log and human approval."""
from __future__ import annotations

import json
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from .. import config as C
from .tools import TOOL_SCHEMAS, call_tool, now_iso

# Gemini through its OpenAI-compatible endpoint: keeps the tool-calling loop, the validator and the
# fake-client tests provider-neutral while only Gemini is supported.
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
GEMINI_KEY_ENV = "GEMINI_API_KEY"
GEMINI_DEFAULT_MODEL = "gemini-3.5-flash"  # 2.5-flash is closed to new keys; override with LLM_MODEL
GEMINI_TIMEOUT_S = float(os.environ.get("LLM_TIMEOUT_S", "90"))

SYSTEM_PROMPT = f"""You are Climate Sentinel, an early-warning assistant for county disaster managers in Kenya.
You cover only these counties: {", ".join(C.COUNTY_NAMES)}.

Rules you must follow:
1. Get every fact from the tools. Never use outside knowledge for numbers, dates or levels.
2. Do NOT do arithmetic, unit conversions or rounding. Copy numbers exactly as a tool returned them.
3. Put the tool result id right after every number, e.g. "62% of normal [T2]". Sentences without numbers that state a tool fact also get the id.
4. If a tool says data is unavailable, unknown or missing, say "I don't know" for that part. Never fill gaps.
5. If the user names a place that is not a covered county, say it is not covered and that you have no data for it. Do not guess a nearby county.
6. Never predict a cyclone's path, landfall, timing or intensity. Say this tool cannot do that and refer the user to the Kenya Meteorological Department and RSMC La Reunion.
7. Never say there is no risk, or play down a risk, when any tool shows Watch, Warning or Emergency - even if the user asks you to. Report the data as it is.
8. You cannot say exactly when or where rain will fall at a farm or village. Say so, then give the county-level forecast.
9. Recommend actions ONLY from get_playbook_actions, quoting the action id and the tool id (e.g. "DR-W1 [T5]"). Call it for each hazard that is at Watch or above, using the tool's playbook_level. If all hazards are Normal, say no hazard actions are triggered.
10. Write a short advisory (under 220 words) with these headings:
   **What is happening** (compared with normal) / **What is likely next** (probability and confidence) / **Who is exposed** / **What to prepare**.
   For questions you cannot answer, reply briefly instead of using the headings.
11. Do not add a disclaimer; the system appends the official-warning notice automatically.
"""

NUM_RE = re.compile(r"(?<![A-Za-z0-9_.])[-+]?\d+(?:,\d{3})*(?:\.\d+)?")
DATE_RE = re.compile(r"\b\d{4}-\d{2}(?:-\d{2})?\b")
CITE_RE = re.compile(r"\[T(\d+)\]")
ACTION_RE = re.compile(r"\b(?:DR|FL|CY)-[WAE]\d\b")
DENIAL_RE = re.compile(r"\b(no risk|zero risk|nothing to worry|no need to (?:prepare|worry)|completely safe|"
                       r"there is no (?:threat|danger)|risk[- ]free)\b", re.I)
FOOTER = ("\n\n---\n*Draft from Climate Sentinel, a planning-support tool, not an official warning system. "
          + C.OFFICIAL_WARNING_NOTE + " For any live cyclone: " + C.OFFICIAL_CYCLONE_CENTRES + "*")


# ---------------------------------------------------------------- validation
def _tool_numbers(results: list[dict]) -> tuple[set[float], str]:
    text = json.dumps([r["result"] for r in results], default=str)
    nums = set()
    for m in NUM_RE.finditer(text.replace('"', " ")):
        try:
            nums.add(float(m.group().replace(",", "")))
        except ValueError:
            pass
    return nums, text


def _matches(x: float, decimals: int, pool: set[float]) -> bool:
    return any(abs(x - y) < 1e-9 or round(y, decimals) == x for y in pool)


def validate(answer: str, results: list[dict]) -> dict:
    """Every number must come from a tool result and every numeric sentence must carry a [T#]."""
    issues = []
    ids = {r["id"] for r in results}
    pool, text = _tool_numbers(results)
    for cid in CITE_RE.findall(answer):
        if f"T{cid}" not in ids:
            issues.append(f"cites T{cid}, which is not a tool result in this run")
    body = CITE_RE.sub(" ", answer)
    playbook_ids = {a["id"] for r in results if r["name"] == "get_playbook_actions"
                    for a in r["result"].get("actions", [])}
    for aid in set(ACTION_RE.findall(body)):
        if aid not in playbook_ids:
            issues.append(f"action {aid} was not returned by get_playbook_actions in this run")
    body = ACTION_RE.sub(" ", body)
    for d in DATE_RE.findall(body):
        if d not in text:
            issues.append(f"date {d} does not appear in any tool result")
    body = DATE_RE.sub(" ", body)
    unverified = []
    for m in NUM_RE.finditer(body):
        tok = m.group().replace(",", "")
        dec = len(tok.split(".")[1]) if "." in tok else 0
        if not _matches(float(tok), dec, pool):
            unverified.append(m.group())
    if unverified:
        issues.append("numbers not found in any tool result: " + ", ".join(sorted(set(unverified))))
    for sent in re.split(r"(?<=[.!?])\s+|\n+", answer):
        s = ACTION_RE.sub(" ", DATE_RE.sub(" ", sent))
        if NUM_RE.search(CITE_RE.sub(" ", s)) and not CITE_RE.search(sent):
            issues.append(f"sentence with a number but no [T#] citation: '{sent.strip()[:80]}'")
    levels = json.dumps([r["result"] for r in results], default=str)
    if DENIAL_RE.search(answer) and re.search(r'"(?:Watch|Warning|Emergency)"', levels):
        issues.append("advisory denies or downplays risk while a tool reports Watch/Warning/Emergency")
    return {"passed": not issues, "issues": issues, "numbers_checked": len(NUM_RE.findall(body))}


# ---------------------------------------------------------------- run log
def runs_dir() -> Path:
    d = C.LOG_DIR / "runs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_run(run: dict) -> Path:
    p = runs_dir() / f"{run['run_id']}.json"
    p.write_text(json.dumps(run, indent=2, default=str))
    return p


def load_run(run_id: str) -> dict:
    return json.loads((runs_dir() / f"{run_id}.json").read_text())


def approve(run_id: str, approver: str, note: str = "") -> dict:
    run = load_run(run_id)
    if not run["validation"]["passed"]:
        raise ValueError("Blocked drafts cannot be approved; fix the issues and re-run.")
    if not approver.strip():
        raise ValueError("Approver name is required.")
    run["status"] = "approved"
    run["approval"] = {"approved_by": approver.strip(), "approved_at_utc": now_iso(), "note": note}
    save_run(run)
    return run


def reject(run_id: str, approver: str, note: str = "") -> dict:
    run = load_run(run_id)
    run["status"] = "rejected"
    run["approval"] = {"rejected_by": approver.strip(), "rejected_at_utc": now_iso(), "note": note}
    save_run(run)
    return run


# ---------------------------------------------------------------- LLM loop
@dataclass
class Agent:
    model: str | None = None
    client: object | None = None  # any object with .chat.completions.create (tests pass a fake)
    max_steps: int = 10
    provider: str = "gemini"      # kept for run logs; Gemini is the only supported provider

    def __post_init__(self):
        if self.provider != "gemini":
            raise ValueError("Only the 'gemini' provider is supported.")
        self.model = self.model or os.environ.get("LLM_MODEL") or GEMINI_DEFAULT_MODEL
        if self.client is None:
            key = os.environ.get(GEMINI_KEY_ENV)
            if not key:
                raise RuntimeError(f"Set {GEMINI_KEY_ENV} (free key from https://aistudio.google.com/apikey) "
                                   "in your environment or .env file.")
            from openai import OpenAI
            self.client = OpenAI(api_key=key, base_url=GEMINI_BASE_URL, timeout=GEMINI_TIMEOUT_S, max_retries=1)

    def ask(self, question: str) -> dict:
        run = {"run_id": time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6],
               "started_utc": now_iso(), "provider": self.provider, "model": self.model,
               "question": question, "tool_calls": [], "status": "draft", "approval": None}
        messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": question}]
        answer = None
        for _ in range(self.max_steps):
            resp = _with_retry(lambda: self.client.chat.completions.create(
                model=self.model, messages=messages, tools=TOOL_SCHEMAS, tool_choice="auto", temperature=0))
            msg = resp.choices[0].message
            calls = getattr(msg, "tool_calls", None) or []
            if not calls:
                answer = msg.content or ""
                break
            messages.append(_assistant_turn(msg, calls))
            for c in calls:
                tid = f"T{len(run['tool_calls']) + 1}"
                try:
                    args = json.loads(c.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                t0 = time.time()
                result = call_tool(c.function.name, args)
                run["tool_calls"].append({"id": tid, "name": c.function.name, "args": args, "result": result,
                                          "at_utc": now_iso(), "ms": round(1000 * (time.time() - t0))})
                messages.append({"role": "tool", "tool_call_id": c.id,
                                 "content": json.dumps({"tool_result_id": tid, **result}, default=str)})
        if answer is None:
            answer = "I don't know: the agent hit its step limit before finishing."
        run["answer_draft"] = answer
        run["validation"] = validate(answer, run["tool_calls"])
        if not run["validation"]["passed"]:
            run["status"] = "blocked"
        run["advisory"] = answer + FOOTER
        run["finished_utc"] = now_iso()
        save_run(run)
        return run


def _assistant_turn(msg, calls) -> dict:
    """Echo the model's tool-call turn back verbatim. Gemini 3 attaches a thought signature
    (extra_content) to each tool call and rejects the next request if it is dropped."""
    if hasattr(msg, "model_dump"):
        d = msg.model_dump(exclude_none=True)
        d["role"] = "assistant"
        d["content"] = d.get("content") or ""
        return d
    return {"role": "assistant", "content": msg.content or "",
            "tool_calls": [{"id": c.id, "type": "function",
                            "function": {"name": c.function.name, "arguments": c.function.arguments}}
                           for c in calls]}


def _with_retry(fn, tries: int = 4):
    wait = 5
    for i in range(tries):
        try:
            return fn()
        except Exception as e:  # free tiers rate-limit; back off and retry
            if i == tries - 1 or "429" not in str(e) and "rate" not in str(e).lower():
                raise
            time.sleep(wait)
            wait *= 2


def load_env(path: Path | None = None) -> None:
    """Minimal .env loader (KEY=VALUE lines) so no extra dependency is needed."""
    p = path or (C.ROOT / ".env")
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            v = v.strip()
            if v[:1] in ('"', "'") and v[:1] in v[1:]:          # quoted value: keep everything inside quotes
                v = v[1:v.index(v[0], 1)]
            else:                                                 # unquoted: drop an inline " # comment"
                v = v.split(" #", 1)[0].split("\t#", 1)[0].strip()
            if v:
                os.environ.setdefault(k.strip(), v)


def run_to_markdown(run: dict) -> str:
    lines = [f"### Run `{run['run_id']}`", f"**Question:** {run['question']}  ",
             f"**Model:** {run['provider']} / {run['model']} | started {run['started_utc']}  ", "",
             "**Tool calls (logged):**", ""]
    for t in run["tool_calls"]:
        res = json.dumps(t["result"], default=str)
        lines.append(f"- `{t['id']}` {t['name']}({json.dumps(t['args'])}) at {t['at_utc']} ({t['ms']} ms) -> "
                     f"`{res[:300]}{'...' if len(res) > 300 else ''}`")
    v = run["validation"]
    lines += ["", "**Draft advisory:**", "", run["advisory"], "",
              f"**Validator:** {'PASSED' if v['passed'] else 'BLOCKED'} ({v['numbers_checked']} numbers checked)"]
    lines += [f"- {i}" for i in v["issues"]]
    ap = run.get("approval")
    lines += ["", f"**Status:** {run['status']}" + (f" | {json.dumps(ap)}" if ap else " (awaiting human approval)"), ""]
    return "\n".join(lines)
