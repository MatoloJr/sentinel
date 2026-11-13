"""Render sentinel/playbook.json (what the agent is allowed to recommend) to PLAYBOOK.md."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
pb = json.loads((ROOT / "sentinel" / "playbook.json").read_text())
L = [f"# {pb['title']}", "", f"> {pb['note']}", ""]
for hz in ("drought", "flood", "cyclone"):
    L += [f"## {hz.capitalize()}", ""]
    for lvl in ("Watch", "Warning", "Emergency"):
        L += [f"**{lvl}** - {pb['levels'][hz][lvl]}", ""]
        for a in [a for a in pb["actions"] if a["hazard"] == hz and a["level"] == lvl]:
            rural = " *(rural / pastoral settings only)*" if "rural" in a.get("settings", []) else ""
            L.append(f"- `{a['id']}` {a['action']} [{a['source']}, {a['loc']}]{rural}")
        L.append("")
wl = pb.get("compound", {}).get("whiplash")
if wl:
    by_id = {a["id"]: a for a in pb["actions"]}
    L += ["## Rain after drought (compound: drought-to-flood whiplash)", "", wl["note"], ""]
    for lvl in ("Watch", "Warning", "Emergency"):
        L += [f"**{lvl}** - {pb['levels']['whiplash'][lvl]}", ""]
        for i in wl[lvl]:
            L.append(f"- `{i}` {by_id[i]['action']} [{by_id[i]['source']}, {by_id[i]['loc']}]")
        L.append("")
L += ["## Sources", ""]
for k, s in pb["sources"].items():
    L.append(f"- **{k}** {s['org']} ({s['year']}). *{s['title']}*. {s['url']}")
(ROOT / "PLAYBOOK.md").write_text("\n".join(L) + "\n")
print("wrote PLAYBOOK.md")
