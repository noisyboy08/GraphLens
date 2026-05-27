const graphEl = document.querySelector("#graph");
const tooltip = document.querySelector("#tooltip");
const details = document.querySelector("#details");
const search = document.querySelector("#search");
const communitySelect = document.querySelector("#community");
const nodeTypeSelect = document.querySelector("#nodeType");
const edgeTypeSelect = document.querySelector("#edgeType");
const hideExternal = document.querySelector("#hideExternal");
const fitButton = document.querySelector("#fit");
const summary = document.querySelector("#summary");
const width = window.innerWidth;
const height = window.innerHeight;
const palette = ["#4cc9f0", "#f72585", "#90be6d", "#f9c74f", "#b5179e", "#43aa8b", "#f3722c", "#577590", "#f94144", "#277da1"];

let state = { scale: 1, x: 0, y: 0, dragging: null, panning: false, panStart: null };

fetch("/api/graph")
  .then((response) => response.json())
  .then((data) => render(data));

function render(data) {
  const nodes = data.nodes.map((node, i) => ({
    ...node,
    x: width / 2 + Math.cos(i) * 180,
    y: height / 2 + Math.sin(i) * 180,
    vx: 0,
    vy: 0,
  }));
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const links = data.links
    .map((link) => ({ ...link, source: byId.get(link.source), target: byId.get(link.target) }))
    .filter((link) => link.source && link.target);
  const degree = new Map(nodes.map((node) => [node.id, 0]));
  links.forEach((link) => {
    degree.set(link.source.id, degree.get(link.source.id) + 1);
    degree.set(link.target.id, degree.get(link.target.id) + 1);
  });

  const svg = makeSvg(nodes, links, degree);
  graphEl.append(svg);
  populateControls(nodes);
  populateSummary(nodes, links);
  bindFilters(svg, nodes, links);
  bindPan(svg);
  fitButton.addEventListener("click", () => fitToScreen(nodes));
  runLayout(svg, nodes, links);
}

function makeSvg(nodes, links, degree) {
  const svg = el("svg", { viewBox: `0 0 ${width} ${height}` });
  const layer = el("g", { id: "viewport" });
  svg.append(layer);
  links.forEach((link) => {
    const line = el("line", { class: "link", "data-source": link.source.id, "data-target": link.target.id });
    link.el = line;
    layer.append(line);
  });
  nodes.forEach((node) => {
    const group = el("g", { class: "node", "data-id": node.id, "data-community": node.community, "data-type": node.node_type });
    const circle = el("circle", { r: 5 + Math.min(14, degree.get(node.id)), fill: color(node.community) });
    const label = el("text", { x: 9, y: 4 });
    label.textContent = node.node_type === "module" ? "" : node.name;
    group.append(circle, label);
    group.addEventListener("pointerdown", (event) => startDrag(event, node));
    group.addEventListener("click", () => showDetails(node, links));
    group.addEventListener("pointermove", (event) => showTip(event, node, degree.get(node.id)));
    group.addEventListener("pointerleave", () => (tooltip.style.opacity = 0));
    node.el = group;
    layer.append(group);
  });
  return svg;
}

function runLayout(svg, nodes, links) {
  let ticks = 0;
  const timer = setInterval(() => {
    step(nodes, links, ticks);
    draw(nodes, links);
    ticks += 1;
    if (ticks > 420) clearInterval(timer);
  }, 16);
  svg.addEventListener("pointermove", (event) => {
    if (!state.dragging) return;
    const point = screenToGraph(event);
    state.dragging.x = point.x;
    state.dragging.y = point.y;
    state.dragging.vx = 0;
    state.dragging.vy = 0;
    draw(nodes, links);
  });
  svg.addEventListener("pointerup", () => (state.dragging = null));
}

function step(nodes, links, tick) {
  const alpha = Math.max(0.02, 0.18 * (1 - tick / 420));
  for (let i = 0; i < nodes.length; i += 1) {
    for (let j = i + 1; j < nodes.length; j += 1) {
      repel(nodes[i], nodes[j], alpha);
    }
  }
  links.forEach((link) => attract(link.source, link.target, alpha));
  nodes.forEach((node) => {
    node.vx += (width / 2 - node.x) * 0.0008;
    node.vy += (height / 2 - node.y) * 0.0008;
    node.vx *= 0.86;
    node.vy *= 0.86;
    node.x += node.vx;
    node.y += node.vy;
  });
}

function repel(a, b, alpha) {
  const dx = b.x - a.x || 0.01;
  const dy = b.y - a.y || 0.01;
  const dist2 = Math.max(80, dx * dx + dy * dy);
  const force = (900 * alpha) / dist2;
  a.vx -= dx * force;
  a.vy -= dy * force;
  b.vx += dx * force;
  b.vy += dy * force;
}

function attract(a, b, alpha) {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const dist = Math.sqrt(dx * dx + dy * dy) || 1;
  const force = (dist - 110) * 0.008 * alpha;
  a.vx += dx * force;
  a.vy += dy * force;
  b.vx -= dx * force;
  b.vy -= dy * force;
}

function draw(nodes, links) {
  links.forEach((link) => {
    link.el.setAttribute("x1", link.source.x);
    link.el.setAttribute("y1", link.source.y);
    link.el.setAttribute("x2", link.target.x);
    link.el.setAttribute("y2", link.target.y);
  });
  nodes.forEach((node) => node.el.setAttribute("transform", `translate(${node.x},${node.y})`));
}

function populateControls(nodes) {
  const communities = [...new Set(nodes.map((node) => node.community))].sort((a, b) => a - b);
  communitySelect.innerHTML = `<option value="all">All communities</option>${communities.map((id) => `<option value="${id}">Community ${id}</option>`).join("")}`;
  document.querySelector("#legend").innerHTML = communities.map((id) => `<div><span style="background:${color(id)}"></span>Community ${id}</div>`).join("");
}

function populateSummary(nodes, links) {
  const files = nodes.filter((node) => node.node_type === "module" && !isExternal(node)).length;
  const functions = nodes.filter((node) => node.node_type === "function").length;
  const classes = nodes.filter((node) => node.node_type === "class").length;
  summary.innerHTML = `<strong>${files}</strong> files · <strong>${functions}</strong> functions · <strong>${classes}</strong> classes · <strong>${links.length}</strong> edges`;
}

function bindFilters(svg, nodes, links) {
  const apply = () => {
    const query = search.value.toLowerCase();
    const community = communitySelect.value;
    const nodeType = nodeTypeSelect.value;
    const edgeType = edgeTypeSelect.value;
    const visible = new Set(nodes.filter((node) => matches(node, query, community, nodeType)).map((node) => node.id));
    nodes.forEach((node) => node.el.setAttribute("opacity", visible.has(node.id) ? "1" : "0.12"));
    links.forEach((link) => {
      const linkVisible = visible.has(link.source.id) && visible.has(link.target.id) && (edgeType === "all" || link.type === edgeType);
      link.el.setAttribute("opacity", linkVisible ? "0.5" : "0.03");
    });
  };
  search.addEventListener("input", apply);
  communitySelect.addEventListener("change", apply);
  nodeTypeSelect.addEventListener("change", apply);
  edgeTypeSelect.addEventListener("change", apply);
  hideExternal.addEventListener("change", apply);
  apply();
}

function bindPan(svg) {
  svg.addEventListener("wheel", (event) => {
    event.preventDefault();
    state.scale = Math.max(0.25, Math.min(5, state.scale * (event.deltaY > 0 ? 0.9 : 1.1)));
    updateViewport();
  });
  svg.addEventListener("pointerdown", (event) => {
    if (event.target.closest(".node")) return;
    state.panning = true;
    state.panStart = { x: event.clientX - state.x, y: event.clientY - state.y };
  });
  svg.addEventListener("pointermove", (event) => {
    if (!state.panning) return;
    state.x = event.clientX - state.panStart.x;
    state.y = event.clientY - state.panStart.y;
    updateViewport();
  });
  svg.addEventListener("pointerup", () => (state.panning = false));
}

function startDrag(event, node) {
  state.dragging = node;
  event.stopPropagation();
}

function screenToGraph(event) {
  return { x: (event.clientX - state.x) / state.scale, y: (event.clientY - state.y) / state.scale };
}

function updateViewport() {
  document.querySelector("#viewport").setAttribute("transform", `translate(${state.x},${state.y}) scale(${state.scale})`);
}

function fitToScreen(nodes) {
  const visible = nodes.filter((node) => node.el.getAttribute("opacity") !== "0.12");
  const active = visible.length ? visible : nodes;
  const minX = Math.min(...active.map((node) => node.x));
  const maxX = Math.max(...active.map((node) => node.x));
  const minY = Math.min(...active.map((node) => node.y));
  const maxY = Math.max(...active.map((node) => node.y));
  const graphWidth = Math.max(1, maxX - minX);
  const graphHeight = Math.max(1, maxY - minY);
  state.scale = Math.max(0.25, Math.min(4, Math.min((width - 360) / graphWidth, (height - 80) / graphHeight)));
  state.x = 340 + (width - 360 - graphWidth * state.scale) / 2 - minX * state.scale;
  state.y = 40 + (height - 80 - graphHeight * state.scale) / 2 - minY * state.scale;
  updateViewport();
}

function matches(node, query, community, nodeType) {
  const text = `${node.name} ${node.path}`.toLowerCase();
  const typeMatches = nodeType === "all" || node.node_type === nodeType;
  const externalMatches = !hideExternal.checked || !isExternal(node);
  return (!query || text.includes(query)) && (community === "all" || String(node.community) === community) && typeMatches && externalMatches;
}

function isExternal(node) {
  return String(node.path || "").startsWith("<external>/");
}

function showDetails(node, links) {
  const count = links.filter((link) => link.source.id === node.id || link.target.id === node.id).length;
  details.innerHTML = `<h2>${escapeHtml(node.name)}</h2><p>${escapeHtml(node.path)}</p><p>${escapeHtml(node.node_type)}</p><p>${count} connections</p>`;
}

function showTip(event, node, degree) {
  tooltip.style.opacity = 1;
  tooltip.style.left = `${event.pageX + 12}px`;
  tooltip.style.top = `${event.pageY + 12}px`;
  tooltip.innerHTML = `<strong>${escapeHtml(node.name)}</strong><br>${escapeHtml(node.path)}<br>${degree} connections`;
}

function color(id) {
  return palette[Math.abs(Number(id) || 0) % palette.length];
}

function el(name, attrs = {}) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", name);
  Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, value));
  return node;
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" })[char]);
}
