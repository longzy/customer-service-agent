#!/usr/bin/env python3
"""生成项目驾驶舱：Roadmap / Board / Table 三视图。

数据源（只读）：
- `docs/tasks/<spec>/F-XX.md` 的 frontmatter：任务、状态、AC、里程碑
- `docs/ROADMAP.md` 的阶段表与 M1 切片表
- `docs/STATUS.md` 的更新日期、进行中、阻塞、下一步

产物：
- `docs/status.json`：中立数据层，可导出给 GitHub Projects / Linear
- `docs/dashboard.html`：单文件看板，无外部依赖

用法：
    python3 scripts/gen_board.py
    python3 scripts/gen_board.py --check   # 比较生成物，有差异退出 1
"""

# ruff: noqa: E501

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
CARDS = DOCS / "tasks"
ROADMAP = DOCS / "ROADMAP.md"
STATUS = DOCS / "STATUS.md"

FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n", re.S)
STAGE_ROW = re.compile(r"^\| ([A-Z]\d[\w-]*) \| (.+?) \| (done|doing|todo) \|", re.M)
SLICE_ROW = re.compile(r"^\| (\d{3}) \| (.+?) \| (done|doing|todo) \|", re.M)

HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>项目驾驶舱</title>
<style>
:root{--ink:#111827;--canvas:#F4F8F7;--line:#E3E8E6;--muted:#6B7280;--ok:#16794F;--doing:#B45309;--review:#6D28D9;--card:#fff;--radius:16px}
*{box-sizing:border-box}
body{margin:0;background:var(--canvas);color:var(--ink);font:14px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif}
header{display:flex;align-items:flex-end;justify-content:space-between;gap:16px;padding:28px 32px 18px}
h1{margin:0;font-size:24px;letter-spacing:-.02em}
.sub{color:var(--muted);font-size:13px;margin-top:4px}
.tabs{display:flex;gap:6px;padding:0 32px}
.tab{border:1px solid var(--line);background:#fff;border-radius:999px;padding:7px 16px;cursor:pointer;font-size:13px;color:var(--muted)}
.tab.on{background:var(--ink);color:#fff;border-color:var(--ink)}
main{padding:18px 32px 40px}
.panel{display:none}
.panel.on{display:block}
.roadmap{display:grid;grid-template-columns:repeat(8,minmax(120px,1fr));gap:0;margin:8px 0 24px}
.stage{position:relative;padding:18px 12px 0;border-top:2px solid var(--line)}
.stage.done{border-top-color:var(--ok)}
.stage.doing{border-top-color:var(--ink)}
.stage .dot{position:absolute;top:-7px;left:12px;width:12px;height:12px;border-radius:50%;background:#94A3B8;border:2px solid var(--canvas)}
.stage.done .dot{background:var(--ok)}
.stage.doing .dot{background:var(--ink)}
.stage .id{font-weight:650;font-size:13px}
.stage .name{color:var(--muted);font-size:12px}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);padding:16px 18px}
.card h3{margin:0 0 6px;font-size:14px}
.meta{color:var(--muted);font-size:12px}
.bar{height:6px;background:#EEF2F0;border-radius:99px;overflow:hidden;margin-top:10px}
.bar>i{display:block;height:100%;background:var(--ink)}
.board{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}
.col{background:#EDF2F0;border-radius:var(--radius);padding:12px;min-height:220px}
.col h3{margin:2px 4px 10px;font-size:13px;display:flex;justify-content:space-between}
.col h3 span{color:var(--muted);font-weight:400}
.task{background:#fff;border:1px solid var(--line);border-radius:12px;padding:10px 12px;margin-bottom:8px;cursor:pointer}
.task:hover{border-color:#B9C4C0}
.task .id{font-size:11px;color:var(--muted);font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
.task .t{font-size:13px;margin-top:2px}
.pill{display:inline-block;font-size:11px;border-radius:99px;padding:2px 8px;border:1px solid var(--line);color:var(--muted)}
.pill.done{color:var(--ok);border-color:#BFE3D0;background:#F0FAF4}
.pill.doing{color:var(--doing);border-color:#F3D9B8;background:#FEF7EC}
.pill.review{color:var(--review);border-color:#DDD3F7;background:#F6F2FF}
.pill.todo{color:#64748B;background:#F8FAFC}
table{width:100%;border-collapse:collapse;background:#fff;border:1px solid var(--line);border-radius:var(--radius);overflow:hidden}
th,td{text-align:left;padding:10px 14px;border-bottom:1px solid var(--line);font-size:13px}
th{font-size:12px;color:var(--muted);font-weight:600;background:#FAFCFB}
tr:last-child td{border-bottom:none}
tbody tr{cursor:pointer}
tbody tr:hover{background:#FAFCFB}
.filters{display:flex;gap:8px;margin-bottom:12px}
select{border:1px solid var(--line);border-radius:10px;padding:6px 10px;background:#fff;color:var(--ink)}
.check{display:flex;align-items:center;gap:6px;font-size:12px;color:var(--muted);border:1px solid var(--line);background:#fff;border-radius:10px;padding:6px 10px}
.drawer{position:fixed;right:0;top:0;height:100%;width:380px;background:#fff;border-left:1px solid var(--line);box-shadow:-12px 0 32px rgba(17,24,39,.08);transform:translateX(100%);transition:.2s;padding:24px;overflow:auto;z-index:9}
.drawer.on{transform:none}
.drawer h2{margin:6px 0 4px;font-size:18px}
.drawer .close{float:right;border:0;background:none;font-size:20px;cursor:pointer;color:var(--muted)}
.kv{display:grid;grid-template-columns:88px 1fr;gap:8px 10px;margin-top:16px;font-size:13px}
.kv b{color:var(--muted);font-weight:500}
.empty{color:var(--muted);padding:40px;text-align:center}
.more{color:var(--muted);font-size:12px;padding:8px 4px 2px}
@media(max-width:900px){.board{grid-template-columns:1fr 1fr}.roadmap{grid-template-columns:repeat(4,1fr);row-gap:18px}}
</style>
</head>
<body>
<header>
  <div><h1>项目驾驶舱</h1><div class="sub" id="sub"></div></div>
  <div class="pill" id="now"></div>
</header>
<div class="tabs">
  <button class="tab on" data-p="roadmap">Roadmap</button>
  <button class="tab" data-p="board">Board</button>
  <button class="tab" data-p="table">Table</button>
</div>
<main>
  <section class="panel on" id="roadmap">
    <div class="roadmap" id="stages"></div>
    <div class="cards" id="speccards"></div>
    <div class="cards" id="statuscards" style="margin-top:18px"></div>
  </section>
  <section class="panel" id="board">
    <div class="filters"><select id="specFilter"></select>
      <label class="check"><input type="checkbox" id="showDone"> 显示全部已完成</label></div>
    <div class="board" id="board-list"></div>
  </section>
  <section class="panel" id="table">
    <table><thead><tr><th>ID</th><th>任务</th><th>AC</th><th>状态</th><th>spec</th></tr></thead><tbody id="tbody"></tbody></table>
  </section>
</main>
<aside class="drawer" id="drawer"></aside>
<script>
const DATA = __DATA__;
const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const LABEL = {done:"已完成",doing:"进行中",review:"待评审",todo:"未开始",blocked:"阻塞"};

$("#sub").textContent = `更新 ${DATA.updated} · 当前 ${DATA.current_milestone} · ${DATA.features.length} 个任务`;
$("#now").textContent = `${DATA.current_milestone} ${LABEL[DATA.milestones.find(m => m.id === DATA.current_milestone)?.status] || ""}`;

$("#stages").innerHTML = DATA.milestones.map(m =>
  `<div class="stage ${m.status}"><span class="dot"></span><div class="id">${m.id}</div><div class="name">${esc(m.name)}</div></div>`).join("");

$("#speccards").innerHTML = DATA.specs.map(s => {
  const pct = s.total ? Math.round(s.done / s.total * 100) : 0;
  const progress = s.total ? `${s.done}/${s.total}` : "待规划";
  return `<div class="card"><h3>${s.id} ${esc(s.name)}</h3>
    <div class="meta">${progress} · ${LABEL[s.status] || s.status}</div>
    <div class="bar"><i style="width:${pct}%"></i></div></div>`;
}).join("");

$("#statuscards").innerHTML = [
  ["进行中", DATA.status.doing || "无"],
  ["阻塞", DATA.status.blocked || "无"],
  ["下一步", DATA.status.next || "无"],
  ["已完成", `${DATA.done_count} 个任务`]
].map(([h, b]) => `<div class="card"><h3>${h}</h3><div class="meta">${esc(b)}</div></div>`).join("");

const specSel = $("#specFilter");
specSel.innerHTML = `<option value="">全部 spec</option>` + DATA.specs.map(s => `<option value="${s.id}">${s.id} ${esc(s.name)}</option>`).join("");

function renderBoard() {
  const pick = specSel.value;
  const allDone = $("#showDone").checked;
  const cols = ["todo","doing","review","done"];
  $("#board-list").innerHTML = cols.map(c => {
    const all = DATA.features.filter(f => f.status === c && (!pick || f.spec === pick));
    const items = (c === "done" && !allDone) ? all.slice(0, 5) : all;
    const more = all.length - items.length;
    return `<div class="col"><h3>${LABEL[c]} <span>${all.length}</span></h3>` +
      (items.length ? items.map(f => `<div class="task" data-id="${f.id}">
        <div class="id">${f.id} · ${f.spec}</div><div class="t">${esc(f.title)}</div></div>`).join("")
        : `<div class="empty">—</div>`) +
      (more > 0 ? `<div class="more">还有 ${more} 个已完成 · 勾选上方查看</div>` : "") + `</div>`;
  }).join("");
}
specSel.onchange = renderBoard;
$("#showDone").onchange = renderBoard;

$("#tbody").innerHTML = DATA.features.map(f =>
  `<tr data-id="${f.id}"><td>${f.id}</td><td>${esc(f.title)}</td><td>${f.ac.join("、")}</td>
   <td><span class="pill ${f.status}">${LABEL[f.status]}</span></td><td>${f.spec}</td></tr>`).join("");

document.querySelectorAll(".tab").forEach(t => t.onclick = () => {
  document.querySelectorAll(".tab").forEach(x => x.classList.toggle("on", x === t));
  document.querySelectorAll(".panel").forEach(p => p.classList.toggle("on", p.id === t.dataset.p));
});

function showDetail(id) {
  const f = DATA.features.find(x => x.id === id);
  if (!f) return;
  $("#drawer").innerHTML = `<button class="close" onclick="document.getElementById('drawer').classList.remove('on')">×</button>
    <div class="meta">${f.id} · ${f.spec} · ${f.milestone}</div><h2>${esc(f.title)}</h2>
    <span class="pill ${f.status}">${LABEL[f.status]}</span>
    <div class="kv"><b>AC</b><span>${f.ac.join("、") || "—"}</span>
    <b>卡片</b><span>${esc(f.card)}</span></div>`;
  $("#drawer").classList.add("on");
}
document.addEventListener("click", e => {
  const el = e.target.closest("[data-id]");
  if (el) showDetail(el.dataset.id);
});

renderBoard();
const initView = new URLSearchParams(location.search).get("view");
if (initView) document.querySelector(`.tab[data-p="${initView}"]`)?.click();
</script>
</body>
</html>
"""


def section(text: str, title: str) -> str:
    match = re.search(rf"^## {re.escape(title)}\s*$", text, re.M)
    if not match:
        return ""
    rest = text[match.end() :]
    end = re.search(r"^## ", rest, re.M)
    block = rest[: end.start()] if end else rest
    text = " ".join(line.strip("- ").strip() for line in block.splitlines() if line.strip())
    return text[:140]


def read_cards() -> list[dict]:
    features = []
    for path in sorted(CARDS.glob("*/F-*.md")):
        text = path.read_text(encoding="utf-8")
        match = FRONTMATTER.match(text)
        if not match:
            continue
        meta: dict[str, str] = {}
        for line in match.group(1).splitlines():
            key, sep, value = line.partition(":")
            if sep:
                meta[key.strip()] = value.strip()
        if not meta.get("id"):
            continue
        features.append(
            {
                "id": meta["id"],
                "title": meta.get("title", ""),
                "spec": path.parent.name.split("-", 1)[0],
                "spec_dir": path.parent.name,
                "milestone": meta.get("milestone", "M1"),
                "status": meta.get("status", "todo"),
                "category": meta.get("category", ""),
                "ac": re.findall(r"AC-\d+", meta.get("ac", "")),
                "card": f"docs/tasks/{path.parent.name}/{path.name}",
            }
        )
    return features


def read_roadmap() -> tuple[list[dict], dict[str, dict[str, str]]]:
    text = ROADMAP.read_text(encoding="utf-8")
    stages = [
        {"id": m.group(1), "name": m.group(2), "status": m.group(3)}
        for m in STAGE_ROW.finditer(text)
    ]
    spec_meta = {
        m.group(1): {"name": m.group(2), "status": m.group(3)} for m in SLICE_ROW.finditer(text)
    }
    return stages, spec_meta


def read_status() -> dict[str, str]:
    text = STATUS.read_text(encoding="utf-8")
    updated = re.search(r"^- 更新日期：(.+)$", text, re.M)
    milestone = re.search(r"^- 当前 Milestone：([A-Z]\d[\w-]*)", text, re.M)
    return {
        "updated": updated.group(1).strip() if updated else "",
        "milestone": milestone.group(1) if milestone else "M1",
        "doing": section(text, "进行中"),
        "blocked": section(text, "阻塞"),
        "next": section(text, "下一步"),
    }


def build() -> dict:
    features = read_cards()
    stages, spec_meta = read_roadmap()
    status = read_status()
    specs = []
    for sid, meta in sorted(spec_meta.items()):
        rows = [f for f in features if f["spec"] == sid]
        done = sum(1 for f in rows if f["status"] == "done")
        declared = meta["status"]
        state = "doing" if rows and done < len(rows) else declared
        specs.append(
            {
                "id": sid,
                "folder": rows[0]["spec_dir"] if rows else "",
                "name": meta["name"],
                "status": state,
                "done": done,
                "total": len(rows),
            }
        )
    doing = [f for f in features if f["status"] in {"doing", "review", "blocked"}]
    return {
        "updated": status["updated"],
        "current_milestone": status["milestone"],
        "milestones": stages,
        "specs": specs,
        "features": features,
        "status": {"doing": status["doing"], "blocked": status["blocked"], "next": status["next"]},
        "done_count": sum(1 for f in features if f["status"] == "done"),
        "open_count": len(doing),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成项目驾驶舱")
    parser.add_argument("--check", action="store_true", help="只比较，不写")
    args = parser.parse_args(argv)

    data = build()
    payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    page = HTML.replace("__DATA__", json.dumps(data, ensure_ascii=False))

    targets = {
        DOCS / "status.json": payload,
        DOCS / "dashboard.html": page,
    }
    ok = True
    for path, content in targets.items():
        current = path.read_text(encoding="utf-8") if path.exists() else ""
        if current == content:
            continue
        if args.check:
            print(f"{path}：与源数据不一致，请运行 make dashboard", file=sys.stderr)
            ok = False
            continue
        path.write_text(content, encoding="utf-8")
        print(f"更新 {path}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
