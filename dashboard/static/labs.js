// Lab lineage graph: parents above children. Click = details + highlight lineage, dblclick = open.
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const panel = document.getElementById("panel");

const cy = cytoscape({
  container: document.getElementById("graph"),
  elements: [...GRAPH.nodes, ...GRAPH.edges],
  wheelSensitivity: 0.3, minZoom: 0.15, maxZoom: 2.5,
  style: [
    { selector: "node", style: {
      "shape": "round-rectangle", "width": 210, "height": 58, "label": "data(label)",
      "text-wrap": "wrap", "text-max-width": 195, "text-valign": "center", "font-size": 13,
      "color": css("--fg"), "background-color": css("--panel"),
      "border-width": 3, "border-color": e => css("--" + e.data("status")) || css("--planned") } },
    { selector: "node[status = 'abandoned']", style: { "border-style": "dashed", "opacity": 0.7 } },
    { selector: "edge", style: {
      "width": 2, "line-color": css("--line"), "target-arrow-color": css("--line"),
      "target-arrow-shape": "triangle", "curve-style": "bezier" } },
    { selector: ".faded", style: { "opacity": 0.18 } },
    { selector: "node:selected", style: { "background-color": css("--accent-soft"), "border-width": 4 } },
    { selector: "edge.lineage", style: { "line-color": css("--accent"), "target-arrow-color": css("--accent") } },
  ],
  layout: { name: "dagre", rankDir: "TB", nodeSep: 30, rankSep: 50, padding: 30 },
});
if (cy.zoom() > 1) { cy.zoom(1); cy.center(); }  // few labs: don't blow them up

function labLink(id) {
  const n = cy.getElementById(String(id));
  return `<a href="#" data-id="${id}">${esc(n.data("code") || "L" + id)}</a> <span class="muted small">${esc(n.data("title"))}</span>`;
}

function select(node) {
  cy.elements().removeClass("faded lineage");
  const lineage = node.predecessors().union(node.successors()).union(node);
  cy.elements().difference(lineage).addClass("faded");
  lineage.edges().addClass("lineage");
  const d = node.data();
  const metrics = Object.entries(d.metrics || {}).map(([k, v]) => `<dt>${esc(k)}</dt><dd class="mono">${esc(v)}</dd>`).join("");
  panel.innerHTML = `
    <p class="muted small">${esc(d.code)} · ${esc(d.created)}</p>
    <h2 style="margin:0 0 6px">${esc(d.title)}</h2>
    <p><span class="badge s-${esc(d.status)}">${esc(d.status)}</span> ${(d.tags || []).map(esc).join(", ")}</p>
    ${d.hypothesis ? `<p><b>Hypothesis</b><br>${esc(d.hypothesis)}</p>` : ""}
    ${d.conclusion ? `<p class="banner"><b>Conclusion</b><br>${esc(d.conclusion)}</p>` : ""}
    ${metrics ? `<dl class="meta small">${metrics}</dl>` : ""}
    <p class="small"><b>Parents</b><br>${d.parents.map(labLink).join("<br>") || '<span class="muted">root</span>'}</p>
    <p class="small"><b>Children</b><br>${d.children.map(labLink).join("<br>") || '<span class="muted">none yet</span>'}</p>
    <p><a class="btn" href="/labs/${d.id}">Open lab →</a></p>`;
  panel.querySelectorAll("a[data-id]").forEach(a => a.onclick = e => {
    e.preventDefault(); const n = cy.getElementById(a.dataset.id); cy.$(":selected").unselect(); n.select(); select(n);
    cy.animate({ center: { eles: n } }, { duration: 250 });
  });
}

cy.on("tap", "node", e => select(e.target));
cy.on("tap", e => { if (e.target === cy) cy.elements().removeClass("faded lineage"); });
cy.on("dbltap", "node", e => { location.href = "/labs/" + e.target.id(); });
if (FOCUS !== null) {
  const n = cy.getElementById(String(FOCUS));
  if (n.length) { n.select(); select(n); }
}
