#!/usr/bin/env python3
"""Compare two versions of Data/Quests.lua and summarise the change per zone.

Usage:
    pip install lupa
    git show main:Data/Quests.lua > /tmp/Quests.old.lua
    python3 tools/diff_quests.py /tmp/Quests.old.lua Data/Quests.lua

Prints a Markdown report: quests added, removed and changed, per zone mapID.
The header comment is ignored; only the data is compared: ns.Quests and
ns.ZoneContinents. Changes to instance pages (ns.InstanceZones/InstanceInfo:
dungeon or raid, names) aren't reported.

With --check, it also fails (exit 1) if the new file looks broken:
  - it has more than 10% fewer quests than the old one,
  - a zone in the old file is missing from the new one.
A file that does not load as Lua fails either way.
"""

import argparse
import sys

from lupa import LuaRuntime

MAX_DROP = 0.10      # --check fails if the quest count falls by more than this
MAX_IDS = 40         # quest IDs listed per zone and kind before "and N more"
MAX_REPORT = 60000   # GitHub caps a PR body at 65536 characters


def load(path):
    """Data/Quests.lua -> (quests {id: {field: value}}, zones {mapID: continent})."""
    with open(path, encoding="utf-8") as f:
        source = f.read()
    lua = LuaRuntime(unpack_returned_tuples=True)
    ns = lua.table()
    run = lua.eval("function(src, name, ns) return assert(load(src, '@' .. name, 't', {}))('LorePath', ns) end")
    run(source, path, ns)
    if ns.Quests is None or ns.ZoneContinents is None:
        raise ValueError(f"{path} does not define ns.Quests and ns.ZoneContinents")

    def py(value):
        if hasattr(value, "values"):
            return tuple(py(v) for v in value.values())
        return value

    quests = {int(qid): {k: py(v) for k, v in rec.items()} for qid, rec in ns.Quests.items()}
    zones = {int(z): int(c) for z, c in ns.ZoneContinents.items()}
    return quests, zones


def id_list(ids):
    ids = sorted(ids)
    shown = ", ".join(str(i) for i in ids[:MAX_IDS])
    if len(ids) > MAX_IDS:
        shown += f", and {len(ids) - MAX_IDS} more"
    return shown


def report(old, new, old_zones, new_zones):
    added = {q for q in new if q not in old}
    removed = {q for q in old if q not in new}
    changed = {q: sorted(k for k in set(old[q]) | set(new[q]) if old[q].get(k) != new[q].get(k))
               for q in old.keys() & new.keys() if old[q] != new[q]}

    per_zone = {}
    def bucket(zone):
        return per_zone.setdefault(zone, {"added": [], "removed": [], "changed": []})
    for q in added:
        bucket(new[q]["z"])["added"].append(q)
    for q in removed:
        bucket(old[q]["z"])["removed"].append(q)
    for q in changed:
        bucket(new[q]["z"])["changed"].append(q)

    def count(quests, zone):
        return sum(1 for r in quests.values() if r["z"] == zone)

    lines = [
        f"**{len(old):,} → {len(new):,} quests** ({len(added)} added, {len(removed)} removed, "
        f"{len(changed)} changed) in {len(old_zones)} → {len(new_zones)} zones.",
        "",
    ]
    gone = sorted(old_zones.keys() - new_zones.keys())
    fresh = sorted(new_zones.keys() - old_zones.keys())
    if gone:
        lines += [f"Zones removed: {id_list(gone)}", ""]
    if fresh:
        lines += [f"Zones added: {id_list(fresh)}", ""]
    if not per_zone:
        lines.append("No quest changes.")
        return "\n".join(lines) + "\n"

    lines += ["| Zone (mapID) | Quests | Added | Removed | Changed |", "|---|---|---|---|---|"]
    for zone in sorted(per_zone):
        b = per_zone[zone]
        lines.append(f"| {zone} | {count(old, zone)} → {count(new, zone)} | {len(b['added'])} "
                     f"| {len(b['removed'])} | {len(b['changed'])} |")
    summary = list(lines)

    lines += ["", "<details><summary>Quest IDs per zone</summary>", ""]
    for zone in sorted(per_zone):
        b = per_zone[zone]
        lines.append(f"#### Zone {zone}")
        if b["added"]:
            lines.append(f"- Added: {id_list(b['added'])}")
        if b["removed"]:
            lines.append(f"- Removed: {id_list(b['removed'])}")
        if b["changed"]:
            ids = sorted(b["changed"])
            shown = ", ".join(f"{q} ({'/'.join(changed[q])})" for q in ids[:MAX_IDS])
            if len(ids) > MAX_IDS:
                shown += f", and {len(ids) - MAX_IDS} more"
            lines.append(f"- Changed: {shown}")
        lines.append("")
    lines.append("</details>")

    text = "\n".join(lines) + "\n"
    if len(text) > MAX_REPORT:
        text = "\n".join(summary) + "\n\n(Quest ID details omitted: too long for a PR body. "
        text += "Run tools/diff_quests.py locally for the full list.)\n"
    return text


def problems(old, new, old_zones, new_zones):
    found = []
    if len(new) < len(old) * (1 - MAX_DROP):
        found.append(f"quest count dropped by more than {MAX_DROP:.0%}: {len(old)} -> {len(new)}")
    gone = sorted(old_zones.keys() - new_zones.keys())
    if gone:
        found.append(f"zones disappeared: {', '.join(map(str, gone))}")
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("old", help="the previous Data/Quests.lua")
    parser.add_argument("new", help="the new Data/Quests.lua")
    parser.add_argument("--check", action="store_true", help="fail if the new file looks broken")
    args = parser.parse_args()

    old, old_zones = load(args.old)
    new, new_zones = load(args.new)
    print(report(old, new, old_zones, new_zones), end="")
    if args.check:
        found = problems(old, new, old_zones, new_zones)
        for p in found:
            print(f"Sanity check failed: {p}", file=sys.stderr)
        if found:
            sys.exit(1)


if __name__ == "__main__":
    main()
