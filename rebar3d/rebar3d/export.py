"""Export a reconstructed panel: model JSON, 2D projection PNGs, 3D HTML viewer."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

from .reconstruct import Panel

ASSETS = Path(__file__).parent

DIA_COLORS = {
    6: "#b0b0b0", 8: "#e15759", 10: "#f28e2b", 12: "#59a14f",
    16: "#af7aa1", 20: "#4e79a7", 25: "#9c755f", 32: "#e377c2",
}


def panel_to_dict(p: Panel) -> dict:
    return {
        "name": p.name,
        "width": round(p.width, 1),
        "height": round(p.height, 1),
        "thickness": round(p.thickness, 1),
        "openings": [[[round(x, 1), round(y, 1)] for x, y in lp] for lp in p.openings],
        "bars": [
            {
                "d": b.diameter,
                "kind": b.kind,
                "z_src": b.z_source,
                "pts": [[round(x, 1), round(y, 1), round(z, 1)] for x, y, z in b.points],
            }
            for b in p.bars
        ],
        "stats": p.stats,
        "families": p.families,
    }


def write_json(p: Panel, out: Path) -> None:
    out.write_text(json.dumps(panel_to_dict(p)))


def write_projections(p: Panel, out: Path) -> None:
    """Three orthographic projections: front (XY), top (XZ), side (ZY)."""
    fig, axes = plt.subplots(
        2, 2, figsize=(16, 12),
        gridspec_kw={"width_ratios": [4, 1], "height_ratios": [4, 1]},
    )
    ax_front, ax_side, ax_top, ax_off = axes[0][0], axes[0][1], axes[1][0], axes[1][1]
    ax_off.axis("off")

    def draw(ax, ix, iy, title, box):
        ax.add_patch(mpatches.Rectangle((0, 0), box[0], box[1], fill=False, color="#1f77b4", lw=1.2))
        for b in p.bars:
            xs = [pt[ix] for pt in b.points]
            ys = [pt[iy] for pt in b.points]
            ax.plot(xs, ys, color=DIA_COLORS.get(b.diameter, "#333"), lw=0.7)
        if ix == 0 and iy == 1:
            for lp in p.openings:
                ax.add_patch(mpatches.Polygon(lp, fill=False, color="#17becf", lw=1.0))
        ax.set_aspect("equal")
        ax.set_title(title, fontsize=9)
        ax.autoscale()

    draw(ax_front, 0, 1, f"{p.name} — front (X/Y)", (p.width, p.height))
    draw(ax_side, 2, 1, "side (Z/Y)", (p.thickness, p.height))
    draw(ax_top, 0, 2, "top (X/Z)", (p.width, p.thickness))
    handles = [
        plt.Line2D([0], [0], color=c, lw=2, label=f"T{d}")
        for d, c in DIA_COLORS.items()
        if any(b.diameter == d for b in p.bars)
    ]
    ax_off.legend(handles=handles, loc="center", fontsize=10, title="Bar dia")
    fig.savefig(out, dpi=180, bbox_inches="tight")
    plt.close(fig)


def write_viewer(panels: list[Panel], out: Path, title: str = "Rebar 3D") -> None:
    three_src = (ASSETS / "assets_three.js").read_text()
    models = json.dumps([panel_to_dict(p) for p in panels])
    html = (
        VIEWER_TEMPLATE
        .replace("__TITLE__", title)
        .replace("__THREE_JS__", three_src)
        .replace("__MODELS__", models)
    )
    out.write_text(html)


VIEWER_TEMPLATE = r"""<title>__TITLE__</title>
<style>
  html, body { margin:0; height:100%; overflow:hidden; background:#15181d; color:#dde1e6;
    font: 13px/1.45 -apple-system, "Segoe UI", sans-serif; }
  #c { display:block; width:100%; height:100%; }
  #panelbar { position:fixed; top:10px; left:10px; display:flex; gap:6px; flex-wrap:wrap; z-index:2; }
  #panelbar button { background:#262b33; color:#dde1e6; border:1px solid #3a414d; border-radius:6px;
    padding:5px 12px; cursor:pointer; }
  #panelbar button.on { background:#3d6fd0; border-color:#3d6fd0; color:#fff; }
  #hud { position:fixed; left:10px; bottom:10px; background:#1d2129cc; border:1px solid #3a414d;
    border-radius:8px; padding:10px 12px; max-width:270px; z-index:2; }
  #hud .sw { display:inline-block; width:11px; height:11px; border-radius:2px; margin-right:6px; vertical-align:-1px; }
  #hud label { display:block; cursor:pointer; margin:1px 0; }
  #hud .dim { color:#8a919d; }
  h1 { font-size:13px; margin:0 0 6px; }
</style>
<div id="panelbar"></div>
<div id="hud">
  <h1 id="hd"></h1>
  <div id="legend"></div>
  <div id="toggles"></div>
  <div id="families" style="margin-top:6px"></div>
  <div id="measure" style="margin-top:6px; color:#7ec8ff"></div>
  <div class="dim" style="margin-top:6px">drag: orbit · shift-drag: pan · wheel: zoom<br>click a bar, then a second bar: distance</div>
</div>
<canvas id="c"></canvas>
<script>__THREE_JS__</script>
<script>
"use strict";
const MODELS = __MODELS__;
const DIA_COLORS = {6:0xb0b0b0,8:0xe15759,10:0xf28e2b,12:0x59a14f,16:0xaf7aa1,20:0x4e79a7,25:0x9c755f,32:0xe377c2};

const canvas = document.getElementById("c");
const renderer = new THREE.WebGLRenderer({canvas, antialias:true});
renderer.setPixelRatio(window.devicePixelRatio);
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x15181d);
const camera = new THREE.PerspectiveCamera(45, 2, 1, 100000);
scene.add(new THREE.AmbientLight(0xffffff, 0.75));
const dl = new THREE.DirectionalLight(0xffffff, 1.2); dl.position.set(1, 2, 1.5); scene.add(dl);
const dl2 = new THREE.DirectionalLight(0xffffff, 0.5); dl2.position.set(-1.5, -1, -1); scene.add(dl2);

// ---- minimal orbit control
let target = new THREE.Vector3(), sph = {r: 6000, th: 0.9, ph: 1.15};
function applyCam() {
  camera.position.set(
    target.x + sph.r * Math.sin(sph.ph) * Math.cos(sph.th),
    target.y + sph.r * Math.cos(sph.ph),
    target.z + sph.r * Math.sin(sph.ph) * Math.sin(sph.th));
  camera.lookAt(target);
}
let drag = null;
canvas.addEventListener("pointerdown", e => { drag = {x:e.clientX, y:e.clientY, pan:e.shiftKey}; canvas.setPointerCapture(e.pointerId); });
canvas.addEventListener("pointermove", e => {
  if (!drag) return;
  const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
  drag.x = e.clientX; drag.y = e.clientY;
  if (drag.pan) {
    const s = sph.r / 900;
    const right = new THREE.Vector3().subVectors(camera.position, target).cross(camera.up).normalize();
    target.addScaledVector(right, dx * s);
    target.addScaledVector(camera.up, dy * s);
  } else {
    sph.th += dx * 0.006;
    sph.ph = Math.min(Math.PI - 0.05, Math.max(0.05, sph.ph - dy * 0.006));
  }
  applyCam();
});
canvas.addEventListener("pointerup", () => drag = null);
canvas.addEventListener("wheel", e => { e.preventDefault(); sph.r *= Math.exp(e.deltaY * 0.001); applyCam(); }, {passive:false});

// ---- model building
let group = null;
const kindGroups = {};
function buildPanel(m) {
  if (group) scene.remove(group);
  group = new THREE.Group();
  for (const k in kindGroups) delete kindGroups[k];

  // concrete volume (translucent) — with opening outlines
  const conc = new THREE.Mesh(
    new THREE.BoxGeometry(m.width, m.height, m.thickness),
    new THREE.MeshStandardMaterial({color:0x8a919d, transparent:true, opacity:0.13, depthWrite:false}));
  conc.position.set(m.width/2, m.height/2, m.thickness/2);
  group.add(conc);
  const eg = new THREE.LineSegments(
    new THREE.EdgesGeometry(new THREE.BoxGeometry(m.width, m.height, m.thickness)),
    new THREE.LineBasicMaterial({color:0x5c6470}));
  eg.position.copy(conc.position);
  group.add(eg);
  for (const lp of m.openings) {
    for (const z of [0, m.thickness]) {
      const pts = lp.map(p => new THREE.Vector3(p[0], p[1], z));
      pts.push(pts[0].clone());
      group.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts),
        new THREE.LineBasicMaterial({color:0x17becf})));
    }
  }

  // bars as cylinders between consecutive points
  barMeshes.length = 0;
  for (const b of m.bars) {
    const color = DIA_COLORS[b.d] || 0x999999;
    const kg = kindGroups[b.kind] || (kindGroups[b.kind] = new THREE.Group());
    const mat = new THREE.MeshStandardMaterial({color, roughness:0.45, metalness:0.25});
    for (let i = 0; i + 1 < b.pts.length; i++) {
      const a = new THREE.Vector3(...b.pts[i]), c = new THREE.Vector3(...b.pts[i+1]);
      const len = a.distanceTo(c);
      if (len < 1) continue;
      const cyl = new THREE.Mesh(new THREE.CylinderGeometry(b.d/2, b.d/2, len, 8, 1), mat);
      cyl.position.copy(a).lerp(c, 0.5);
      cyl.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0),
        new THREE.Vector3().subVectors(c, a).normalize());
      cyl.userData.bar = b; cyl.userData.mat = mat;
      kg.add(cyl);
      barMeshes.push(cyl);
    }
  }
  for (const k in kindGroups) group.add(kindGroups[k]);
  group.rotation.x = 0;  // panel modeled upright (Y up); Z is thickness
  scene.add(group);

  target.set(m.width/2, m.height/2, m.thickness/2);
  sph.r = Math.max(m.width, m.height) * 1.4;
  applyCam();

  document.getElementById("hd").textContent =
    `${m.name} — ${m.width}×${m.height}×${m.thickness} mm · ${m.bars.length} bars`;
  const dias = [...new Set(m.bars.map(b => b.d))].sort((a,b)=>a-b);
  document.getElementById("legend").innerHTML = dias.map(d =>
    `<span style="margin-right:10px"><span class="sw" style="background:#${(DIA_COLORS[d]||0x999999).toString(16).padStart(6,"0")}"></span>T${d}</span>`).join("");
  const kinds = Object.keys(kindGroups);
  document.getElementById("toggles").innerHTML = kinds.map(k =>
    `<label><input type="checkbox" checked data-kind="${k}"> ${k} <span class="dim">(${m.bars.filter(b=>b.kind===k).length})</span></label>`).join("");
  document.querySelectorAll("#toggles input").forEach(cb =>
    cb.addEventListener("change", () => { kindGroups[cb.dataset.kind].visible = cb.checked; }));
  document.getElementById("families").innerHTML = (m.families || [])
    .filter(f => f.spacing)
    .map(f => `<div class="dim">${f.kind === "v-mesh" ? "vert" : "horz"} T${f.d} @ <b style="color:#dde1e6">${f.spacing} mm</b> · ${f.count} bars · z=${f.z}</div>`)
    .join("");
  clearMeasure();
}

// ---- click-to-measure between two bars
const barMeshes = [];
const raycaster = new THREE.Raycaster();
let picked = [];   // [{bar, meshes}]
let measureLine = null;
function barSegs(b) {
  const s = [];
  for (let i = 0; i + 1 < b.pts.length; i++)
    s.push([new THREE.Vector3(...b.pts[i]), new THREE.Vector3(...b.pts[i+1])]);
  return s;
}
function closestSegSeg(p1, q1, p2, q2) {
  // returns [pointA, pointB] closest points between segments
  const d1 = q1.clone().sub(p1), d2 = q2.clone().sub(p2), r = p1.clone().sub(p2);
  const a = d1.dot(d1), e = d2.dot(d2), f = d2.dot(r);
  let s, t;
  const c = d1.dot(r), b = d1.dot(d2), denom = a*e - b*b;
  s = denom > 1e-9 ? Math.min(1, Math.max(0, (b*f - c*e) / denom)) : 0;
  t = (b*s + f) / e;
  if (t < 0) { t = 0; s = Math.min(1, Math.max(0, -c / a)); }
  else if (t > 1) { t = 1; s = Math.min(1, Math.max(0, (b - c) / a)); }
  return [p1.clone().addScaledVector(d1, s), p2.clone().addScaledVector(d2, t)];
}
function clearMeasure() {
  for (const p of picked) p.meshes.forEach(mh => mh.userData.mat.emissive && mh.userData.mat.emissive.setHex(0));
  picked = [];
  if (measureLine) { scene.remove(measureLine); measureLine = null; }
  document.getElementById("measure").textContent = "";
}
function pickBar(ev) {
  const r = canvas.getBoundingClientRect();
  const ndc = new THREE.Vector2(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1);
  raycaster.setFromCamera(ndc, camera);
  raycaster.params.Mesh = {threshold: 10};
  const hits = raycaster.intersectObjects(barMeshes.filter(mh => mh.parent.visible), false);
  if (!hits.length) { clearMeasure(); return; }
  const bar = hits[0].object.userData.bar;
  if (picked.length === 2) clearMeasure();
  if (picked.length === 1 && picked[0].bar === bar) return;
  const meshes = barMeshes.filter(mh => mh.userData.bar === bar);
  meshes.forEach(mh => mh.userData.mat.emissive.setHex(0x2255ff));
  picked.push({bar, meshes});
  if (picked.length === 2) {
    let best = null, bd = Infinity;
    for (const s1 of barSegs(picked[0].bar)) for (const s2 of barSegs(picked[1].bar)) {
      const [pa, pb] = closestSegSeg(s1[0], s1[1], s2[0], s2[1]);
      const d = pa.distanceTo(pb);
      if (d < bd) { bd = d; best = [pa, pb]; }
    }
    const clear = Math.max(0, bd - picked[0].bar.d/2 - picked[1].bar.d/2);
    document.getElementById("measure").textContent =
      `T${picked[0].bar.d} ↔ T${picked[1].bar.d}: ${bd.toFixed(0)} mm c/c (clear ${clear.toFixed(0)} mm)`;
    measureLine = new THREE.Line(
      new THREE.BufferGeometry().setFromPoints(best),
      new THREE.LineBasicMaterial({color: 0x7ec8ff}));
    scene.add(measureLine);
  }
}
let downAt = null;
canvas.addEventListener("pointerdown", e => { downAt = [e.clientX, e.clientY]; });
canvas.addEventListener("pointerup", e => {
  if (downAt && Math.hypot(e.clientX - downAt[0], e.clientY - downAt[1]) < 5) pickBar(e);
  downAt = null;
});

// ---- panel switcher
const bar = document.getElementById("panelbar");
MODELS.forEach((m, i) => {
  const b = document.createElement("button");
  b.textContent = m.name;
  b.onclick = () => { document.querySelectorAll("#panelbar button").forEach(x => x.classList.remove("on")); b.classList.add("on"); buildPanel(m); };
  bar.appendChild(b);
  const want = decodeURIComponent(location.hash.slice(1));
  if (want ? m.name === want : i === 0) { b.classList.add("on"); buildPanel(m); }
});

function resize() {
  const w = canvas.clientWidth, h = canvas.clientHeight;
  renderer.setSize(w, h, false);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
}
window.addEventListener("resize", resize);
resize(); applyCam();
renderer.setAnimationLoop(() => renderer.render(scene, camera));
</script>
"""
