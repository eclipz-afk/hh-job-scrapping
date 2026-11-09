"use strict";

const API_BASE = window.APP_CONFIG?.API_BASE || "/api/v1";
const colors = {
  it: "#2459d3",
  data_science: "#087f8c",
};
const sourceNames = {
  hh: "HeadHunter",
  arbeitnow: "Arbeitnow",
};
const skillNames = {
  python: "Python",
  sql: "SQL",
  postgresql: "PostgreSQL",
  javascript: "JavaScript",
  typescript: "TypeScript",
  golang: "Go",
  "c++": "C++",
  aws: "AWS",
  gcp: "Google Cloud",
  "power bi": "Power BI",
  fastapi: "FastAPI",
  pytorch: "PyTorch",
  tensorflow: "TensorFlow",
  numpy: "NumPy",
  "scikit-learn": "Scikit-learn",
};

// State
const state = {
  role: "all",
  view: "overview",
  source: "all",
  page: 1,
  search: "",
  skill: "",
  company: "",
  location: "",
  country: "",
  category: "",
  pageSize: window.innerHeight < 800 ? 7 : 8,
  metrics: null,
  metricErrors: {},
};
let dashboardVersion = 0;
let jobsVersion = 0;
let cloudLayout = null;
let searchTimer;
let resizeTimer;

// Shared helpers
const byId = (id) => document.getElementById(id);
const count = (value) => new Intl.NumberFormat("en-US").format(value || 0);

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) {
    node.className = className;
  }
  if (text !== undefined) {
    node.textContent = text;
  }
  return node;
}

function setStatus(message, isError = false) {
  const node = byId("statusLine");
  node.textContent = message;
  node.classList.toggle("error", isError);
  const retry = byId("retryBtn");
  if (retry) {
    retry.hidden = !isError;
  }
}

async function fetchJSON(path, options = {}) {
  if (window.location?.protocol === "file:") {
    throw new Error("Open the dashboard at http://localhost:8080 instead of opening index.html.");
  }
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    signal: options.signal || AbortSignal.timeout(30000),
  });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const payload = await response.json();
      message = payload.error || message;
    } catch {
      // Keep the HTTP status when no JSON is available.
    }
    throw new Error(message);
  }
  return response.json();
}

function filterQuery() {
  const query = new URLSearchParams();
  if (state.role !== "all") {
    query.set("role_family", state.role);
  }
  if (state.source !== "all") {
    query.set("source", state.source);
  }
  return query;
}

function metricPath(name, limit) {
  const query = filterQuery();
  if (limit) {
    query.set("limit", limit);
  }
  return `/metrics/${name}?${query}`;
}

function formatMoney(value) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) {
    return "Not available";
  }
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value);
}

function labelSkill(name) {
  return skillNames[name] || name.charAt(0).toUpperCase() + name.slice(1);
}

function empty(container, text) {
  container.replaceChildren(element("p", "chart-empty", text));
}

function svgEmpty(svg, text) {
  svg.selectAll("*").remove();
  const width = svg.node().clientWidth || 300;
  const height = svg.node().clientHeight || 200;
  svg
    .attr("viewBox", `0 0 ${width} ${height}`)
    .append("text")
    .attr("x", width / 2)
    .attr("y", height / 2)
    .attr("text-anchor", "middle")
    .attr("fill", "#60738a")
    .attr("font-size", 12)
    .text(text);
}

// Dashboard rendering
function applyKpis(overview) {
  const countsById = {
    kpiTotalJobs: overview.total_jobs,
    kpiCompanies: overview.total_companies,
    kpiUniqueTitles: overview.unique_titles,
    kpiLocations: overview.total_locations,
  };
  for (const [id, value] of Object.entries(countsById)) {
    byId(id).textContent = count(value);
  }
  byId("kpiAvgSalary").textContent = formatMoney(overview.avg_salary_usd);
  byId("kpiMedianSalary").textContent = formatMoney(overview.median_salary_usd);

  const coverage = overview.total_jobs
    ? (overview.salary_jobs || 0) / overview.total_jobs * 100
    : 0;
  byId("salaryCoverage").textContent = `${coverage.toFixed(1)}%`;
  byId("coverageBar").style.width = `${coverage}%`;
  byId("salarySample").textContent =
    `${count(overview.salary_jobs)} of ${count(overview.total_jobs)} vacancies disclose a salary.`;
  byId("salaryRateNote").textContent =
    `CBR rates: ${overview.salary_rate_date || "not supplied"}. Pay periods may differ; not a market-wide estimate.`;
  byId("salaryRateNote").title = overview.salary_rate_source || "";
  const collectionDate = overview.last_collected_at ? new Date(overview.last_collected_at) : null;
  let collectionLabel = "No collection date available";
  if (collectionDate && !Number.isNaN(collectionDate.getTime())) {
    const formattedDate = collectionDate.toLocaleDateString("en-GB", {
      day: "numeric",
      month: "short",
      year: "numeric",
    });
    collectionLabel = `Last collected ${formattedDate}`;
  }
  byId("collectionDate").textContent = collectionLabel;
}

function bar(fraction, color) {
  const track = element("div", "bar-track");
  const fill = element("div", "bar-fill");
  fill.style.width = `${Math.min(100, Math.max(0, fraction * 100))}%`;
  if (color) {
    fill.style.background = color;
  }
  track.appendChild(fill);
  return track;
}

function renderRoles(data) {
  const container = byId("rolesChart");
  container.replaceChildren();
  if (!data.length) {
    return empty(container, "No roles match these filters. Try all tech roles.");
  }
  const maximum = Math.max(...data.map((row) => row.count));
  for (const item of data) {
    const row = element("button", "role-row");
    row.type = "button";
    row.setAttribute("aria-label", `Explore ${item.category} vacancies`);
    row.addEventListener("click", () => selectCategory(item.category));
    row.append(
      element("span", "role-label", item.category),
      bar(item.count / maximum, colors[item.role_family]),
      element("span", "role-count", count(item.count)),
    );
    row.title = `${item.category}: ${count(item.count)} vacancies`;
    container.appendChild(row);
  }
}

function renderSkills(data) {
  const container = byId("skillsChart");
  container.replaceChildren();
  if (!data.length) {
    return empty(container, "No skill mentions recorded for this selection.");
  }
  const maximum = Math.max(...data.map((item) => item.count));
  for (const item of data) {
    const row = element("button", "skill-row");
    row.type = "button";
    const skillLabel = labelSkill(item.skill);
    row.setAttribute("aria-label", `Explore ${count(item.count)} vacancies mentioning ${skillLabel}`);
    row.append(
      element("span", "skill-name", skillLabel),
      bar(item.count / maximum),
      element("span", "", count(item.count)),
    );
    row.addEventListener("click", () => selectSkill(item.skill));
    container.appendChild(row);
  }
}

function renderEmployers(data) {
  const container = byId("employerChart");
  container.replaceChildren();
  if (!data.length) {
    return empty(container, "No employers match these filters.");
  }
  for (const [index, item] of data.entries()) {
    const row = element("button", "employer-row");
    row.type = "button";
    row.setAttribute("aria-label", `Explore vacancies at ${item.company}`);
    row.addEventListener("click", () => selectCompany(item.company));
    const initials = item.company.replace(/[^\p{L}\p{N}]/gu, "").slice(0, 2).toUpperCase();
    const avatar = element("span", "employer-avatar", initials);
    avatar.style.background = ["#edf3ff", "#eaf6f5", "#f3f0fb", "#eef4f8"][index % 4];
    const name = element("span", "employer-name", item.company);
    name.title = item.company;
    const total = element("span", "employer-count", count(item.count));
    total.appendChild(element("small", "", "roles"));
    row.append(avatar, name, total);
    container.appendChild(row);
  }
}

function showTooltip(event, text) {
  const tooltip = byId("chartTooltip");
  tooltip.textContent = text;
  tooltip.hidden = false;
  const bounds = event.currentTarget.getBoundingClientRect();
  const anchorX = event.clientX || bounds.x + bounds.width / 2;
  const anchorY = event.clientY || bounds.y;
  const left = Math.max(8, Math.min(window.innerWidth - 265, anchorX + 12));
  const top = Math.min(window.innerHeight - 70, Math.max(8, anchorY - 42));
  tooltip.style.left = `${left}px`;
  tooltip.style.top = `${top}px`;
}

function renderLocationWords(svg, placedWords, width, height) {
  const wordColors = ["#2459d3", "#087f8c", "#42638d", "#728baa", "#346aae"];
  const nodes = svg
    .append("g")
    .attr("transform", `translate(${width / 2},${height / 2})`)
    .selectAll("text")
    .data(placedWords)
    .join("text")
    .attr("transform", (item) => `translate(${item.x},${item.y})`)
    .attr("text-anchor", "middle")
    .attr("font-family", "Manrope, sans-serif")
    .attr("font-size", (item) => item.size)
    .attr("font-weight", 700)
    .attr("fill", (_, index) => wordColors[index % wordColors.length])
    .attr("tabindex", 0)
    .attr("role", "button")
    .attr("aria-label", (item) => `${item.location}, ${item.country}: ${count(item.count)} vacancies`)
    .text((item) => item.text);
  nodes
    .on("pointermove focus", (event, item) => {
      showTooltip(event, `${item.location}, ${item.country} | ${count(item.count)} vacancies`);
    })
    .on("pointerleave blur", hideTooltip)
    .on("click", (_, item) => selectLocation(item.location, item.country))
    .on("keydown", (event, item) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        selectLocation(item.location, item.country);
      }
    });
  nodes
    .append("title")
    .text((item) => `${item.location}, ${item.country}: ${count(item.count)}`);
}

function renderLocations(data) {
  const svg = d3.select("#locationChart");
  if (cloudLayout) {
    cloudLayout.stop();
  }
  svg.selectAll("*").remove();
  if (!data.length) {
    return svgEmpty(svg, "No locations recorded for this selection");
  }
  const width = svg.node().clientWidth || 430;
  const height = svg.node().clientHeight || 247;
  svg.attr("viewBox", `0 0 ${width} ${height}`);
  byId("citiesCount").textContent = `Top ${data.length} locations`;
  const sizeScale = d3.scaleSqrt()
    .domain([0, d3.max(data, (item) => item.count)])
    .range([12, Math.min(width < 350 ? 37 : 46, height / 4)]);
  const words = data.map((item) => ({
    ...item,
    text: item.location,
    size: sizeScale(item.count),
  }));
  cloudLayout = d3.layout.cloud()
    .size([width, height])
    .words(words)
    .padding(7)
    .rotate(0)
    .random(d3.randomLcg(.42))
    .font("Manrope")
    .fontWeight(700)
    .fontSize((item) => item.size)
    .on("end", (placedWords) => {
      renderLocationWords(svg, placedWords, width, height);
    });
  cloudLayout.start();
}

function renderSalary(data) {
  const container = byId("salaryChart");
  container.replaceChildren();
  if (!data.length) {
    return container.appendChild(element("p", "panel-footnote", "No advertised salaries in this selection."));
  }
  const bands = [
    ["under_1k", "Under $1k"],
    ["1k_to_2k", "$1k–2k"],
    ["2k_to_4k", "$2k–4k"],
    ["4k_plus", "$4k+"],
  ];
  const total = data.reduce((sum, item) => sum + item.count, 0);
  for (const [key, label] of bands) {
    const bandCount = data.find((item) => item.band === key)?.count || 0;
    const node = element("div", "salary-band", label);
    node.appendChild(element("strong", "", count(bandCount)));
    const line = element("div", "salary-band-line");
    const fill = element("i");
    fill.style.width = `${bandCount / total * 100}%`;
    line.appendChild(fill);
    node.appendChild(line);
    container.appendChild(node);
  }
}

function safeJobUrl(value) {
  try {
    const url = new URL(value);
    const allowedProtocol = ["https:", "http:"].includes(url.protocol);
    if (!allowedProtocol || url.username || url.password) {
      return null;
    }
    return url.href;
  } catch {
    return null;
  }
}

function jobSalary(job) {
  if (job.salary_from == null && job.salary_to == null) {
    return "Not disclosed";
  }
  const format = (value) => count(Math.round(value));
  const currency = job.salary_currency === "RUR" ? "RUB" : job.salary_currency || "";
  if (job.salary_from != null && job.salary_to != null) {
    return `${format(job.salary_from)}–${format(job.salary_to)} ${currency}`;
  }
  if (job.salary_from != null) {
    return `From ${format(job.salary_from)} ${currency}`;
  }
  return `Up to ${format(job.salary_to)} ${currency}`;
}

function renderJobRow(job) {
  const row = element("tr");
  const titleCell = element("td");
  const safeUrl = safeJobUrl(job.url);
  const title = element(safeUrl ? "a" : "span", "job-title", job.title);
  title.title = job.title;
  if (safeUrl) {
    title.href = safeUrl;
    title.target = "_blank";
    title.rel = "noopener noreferrer";
  }
  const company = element("span", "company-label", job.company);
  company.title = job.company;
  titleCell.append(title, company);

  const locationCell = element("td");
  const location = job.city || job.location || "Not supplied";
  const countryNotSupplied = job.country === "unknown" || job.country === "Global";
  const country = countryNotSupplied ? "Country not supplied" : job.country || "Country not supplied";
  locationCell.append(
    element("span", "job-location", location),
    element("span", "job-country", country),
  );
  locationCell.title = `${location}, ${country}`;

  const roleCell = element("td");
  const isDataScience = job.role_family === "data_science";
  const roleClass = isDataScience ? "role-tag data" : "role-tag";
  const roleLabel = isDataScience ? "Data Science" : "IT & engineering";
  roleCell.appendChild(element("span", roleClass, roleLabel));

  const salary = jobSalary(job);
  const salaryClass = salary === "Not disclosed" ? "salary-undisclosed" : "";
  row.append(
    titleCell,
    locationCell,
    roleCell,
    element("td", salaryClass, salary),
    element("td", "source-label", sourceNames[job.source] || job.source),
  );
  return row;
}

function renderPagination(payload) {
  const start = payload.total ? (payload.page - 1) * payload.page_size + 1 : 0;
  const end = Math.min(payload.page * payload.page_size, payload.total);
  const totalPages = Math.max(1, Math.ceil(payload.total / payload.page_size));
  byId("tableMeta").textContent = `Showing ${count(start)}–${count(end)} of ${count(payload.total)} vacancies`;
  byId("pageLabel").textContent = `Page ${payload.page} of ${totalPages}`;
  byId("previousPage").disabled = payload.page <= 1;
  byId("nextPage").disabled = payload.page * payload.page_size >= payload.total;
}

function renderJobsTable(payload) {
  const body = byId("jobsTableBody");
  body.replaceChildren();
  if (!payload.items.length) {
    const row = element("tr");
    const cell = element("td", "chart-empty", "No vacancies match. Clear the search or reset your filters.");
    cell.colSpan = 5;
    row.appendChild(cell);
    body.appendChild(row);
  }
  for (const job of payload.items) {
    body.appendChild(renderJobRow(job));
  }
  renderPagination(payload);
  const skillButton = byId("clearSkill");
  skillButton.hidden = !state.skill;
  skillButton.textContent = state.skill ? `${labelSkill(state.skill)} ×` : "";
  skillButton.title = skillButton.textContent;
  skillButton.setAttribute("aria-label", "Clear selected skill");
  for (const [id, value, label] of [
    ["clearCompany", state.company, "Employer"],
    ["clearLocation", state.location, "Location"],
    ["clearCategory", state.category, "Role"],
  ]) {
    const button = byId(id);
    if (button) {
      button.hidden = !value;
      button.textContent = `${label}: ${value} ×`;
      button.title = button.textContent;
      button.setAttribute("aria-label", `Clear selected ${label.toLowerCase()}`);
    }
  }
}

function chartMessage(id, message) {
  const container = byId(id);
  if (container.namespaceURI === "http://www.w3.org/2000/svg") {
    const text = document.createElementNS(container.namespaceURI, "text");
    text.setAttribute("x", "50%");
    text.setAttribute("y", "50%");
    text.setAttribute("text-anchor", "middle");
    text.setAttribute("fill", "#60738a");
    text.setAttribute("font-size", "13");
    text.textContent = message;
    container.replaceChildren(text);
  } else {
    empty(container, message);
  }
}

function renderCharts() {
  if (!state.metrics) {
    return;
  }
  if (state.metrics.overview) {
    applyKpis(state.metrics.overview);
  } else {
    for (const id of [
      "kpiTotalJobs", "kpiCompanies", "kpiUniqueTitles", "kpiLocations",
      "kpiAvgSalary", "kpiMedianSalary", "salaryCoverage",
    ]) {
      byId(id).textContent = "Unavailable";
    }
    byId("coverageBar").style.width = "0%";
    byId("salarySample").textContent = "Salary coverage could not load.";
  }
  if (state.view !== "overview") {
    return;
  }
  const widgets = [
    ["roles", "rolesChart", renderRoles],
    ["skills", "skillsChart", renderSkills],
    ["employers", "employerChart", renderEmployers],
    ["locations", "locationChart", renderLocations],
    ["salary", "salaryChart", renderSalary],
  ];
  for (const [key, id, render] of widgets) {
    if (!state.metrics[key]) {
      chartMessage(id, "Data unavailable. Click Retry.");
      continue;
    }
    if (key === "locations" && typeof d3 === "undefined") {
      chartMessage(id, "Chart library unavailable. Reload the page.");
      state.metricErrors[key] = true;
      continue;
    }
    try {
      render(state.metrics[key]);
    } catch {
      chartMessage(id, "Could not draw this chart. Click Retry.");
      state.metricErrors[key] = true;
    }
  }
}

// Data loading and dataset actions
async function loadJobs() {
  const version = ++jobsVersion;
  const query = filterQuery();
  query.set("page", state.page);
  query.set("page_size", state.pageSize);
  if (state.search) {
    query.set("search", state.search);
  }
  if (state.skill) {
    query.set("skill", state.skill);
  }
  for (const key of ["company", "location", "country", "category"]) {
    if (state[key]) {
      query.set(key, state[key]);
    }
  }
  byId("tableMeta").textContent = "Loading matching vacancies...";
  for (const id of ["previousPage", "nextPage"]) {
    byId(id).disabled = true;
  }
  try {
    const payload = await fetchJSON(`/jobs?${query}`);
    if (version === jobsVersion) {
      renderJobsTable(payload);
    }
    return true;
  } catch (error) {
    if (version === jobsVersion) {
      byId("tableMeta").textContent = "Could not load vacancies. Try Refresh.";
      setStatus(error.message, true);
      const row = element("tr");
      const cell = element("td", "chart-empty", "Vacancies could not load. Click Retry to reconnect.");
      cell.colSpan = 5;
      row.appendChild(cell);
      byId("jobsTableBody").replaceChildren(row);
    }
    return false;
  }
}

async function loadDashboard() {
  const version = ++dashboardVersion;
  byId("dashboardContent").setAttribute("aria-busy", "true");
  setStatus("Loading the selected market...");
  const jobs = loadJobs();
  try {
    const metricNames = [
      "overview",
      "roles",
      "skills",
      "employers",
      "locations",
      "salary-bands",
    ];
    const metricLimits = {
      skills: 10,
      employers: 7,
      locations: 24,
    };
    const metricRequests = metricNames.map((name) => {
      const path = metricPath(name, metricLimits[name]);
      return fetchJSON(path);
    });
    const results = await Promise.allSettled(metricRequests);
    if (version !== dashboardVersion) {
      return;
    }
    const keys = ["overview", "roles", "skills", "employers", "locations", "salary"];
    state.metrics = {};
    state.metricErrors = {};
    for (const [index, result] of results.entries()) {
      const key = keys[index];
      state.metrics[key] = result.status === "fulfilled" ? result.value : null;
      if (result.status === "rejected") {
        state.metricErrors[key] = true;
      }
    }
    renderCharts();
    const jobsLoaded = await jobs;
    if (version !== dashboardVersion) {
      return;
    }
    if (Object.keys(state.metricErrors).length || !jobsLoaded) {
      setStatus("Some data could not load. Available sections are shown; click Retry to reconnect.", true);
      return;
    }
    let roleLabel = "IT & engineering";
    if (state.role === "all") {
      roleLabel = "all tech roles";
    } else if (state.role === "data_science") {
      roleLabel = "Data Science";
    }
    const sourceLabel = state.source === "all" ? "all sources" : sourceNames[state.source];
    setStatus(`Viewing ${roleLabel} from ${sourceLabel}.`);
  } catch (error) {
    if (version === dashboardVersion) {
      setStatus(`Could not load the dashboard. ${error.message} Check the API connection and try Refresh.`, true);
    }
  } finally {
    await jobs;
    if (version === dashboardVersion) {
      byId("dashboardContent").setAttribute("aria-busy", "false");
    }
  }
}

function requestEtlToken() {
  const dialog = byId("etlAuthDialog");
  const input = byId("etlToken");
  input.value = "";
  dialog.returnValue = "";
  return new Promise((resolve) => {
    dialog.addEventListener(
      "close",
      () => {
        const token = dialog.returnValue === "run" ? input.value : null;
        input.value = "";
        resolve(token);
      },
      { once: true },
    );
    dialog.showModal();
  });
}

async function runEtl() {
  byId("runEtlBtn").disabled = true;
  try {
    const token = await requestEtlToken();
    if (!token) {
      return;
    }
    setStatus("Updating the dataset. Collection can take several minutes; you can keep exploring.");
    const result = await fetchJSON("/etl/run", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ target_rows: 5000 }),
      signal: AbortSignal.timeout(900000),
    });
    await loadDashboard();
    const notes = (result.notes || []).join(" ");
    setStatus(
      `Dataset updated: ${count(result.cleaned_rows)} vacancies processed, ${count(result.inserted_rows)} added. ${notes}`,
    );
  } catch (error) {
    setStatus(`Dataset update failed. ${error.message}`, true);
  } finally {
    byId("runEtlBtn").disabled = false;
  }
}

// Events
function selectRole(role) {
  state.role = role;
  state.category = "";
  state.page = 1;
  for (const button of document.querySelectorAll("[data-role]")) {
    const selected = button.dataset.role === role;
    button.classList.toggle("selected", selected);
    button.setAttribute("aria-pressed", String(selected));
  }
  loadDashboard();
}

function selectSkill(skill) {
  state.skill = skill;
  state.page = 1;
  setView("vacancies");
  loadJobs();
}

function selectCompany(company) {
  state.company = company;
  state.page = 1;
  setView("vacancies");
  loadJobs();
}

function selectCategory(category) {
  state.category = category;
  state.page = 1;
  setView("vacancies");
  loadJobs();
}

function selectLocation(location, country) {
  state.location = location;
  state.country = country;
  state.page = 1;
  hideTooltip();
  setView("vacancies");
  loadJobs();
}

function setView(view) {
  state.view = view;
  byId("overviewView").hidden = view !== "overview";
  byId("vacanciesSection").hidden = view !== "vacancies";
  for (const button of document.querySelectorAll("[data-view]")) {
    const selected = button.dataset.view === view;
    button.classList.toggle("selected", selected);
    button.setAttribute("aria-pressed", String(selected));
  }
  if (view === "overview") {
    renderCharts();
  }
}

function hideTooltip() {
  byId("chartTooltip").hidden = true;
}

function resetFilters() {
  state.source = "all";
  state.search = "";
  state.skill = "";
  state.company = "";
  state.location = "";
  state.country = "";
  state.category = "";
  byId("sourceFilter").value = "all";
  byId("jobSearch").value = "";
  selectRole("all");
}

function bindEvents() {
  byId("refreshBtn").addEventListener("click", loadDashboard);
  byId("runEtlBtn").addEventListener("click", runEtl);
  byId("retryBtn").addEventListener("click", loadDashboard);
  for (const button of document.querySelectorAll("[data-view]")) {
    button.addEventListener("click", () => setView(button.dataset.view));
  }
  byId("sourceFilter").addEventListener("change", (event) => {
    state.source = event.target.value;
    state.page = 1;
    loadDashboard();
  });
  for (const button of document.querySelectorAll("[data-role]")) {
    button.addEventListener("click", () => selectRole(button.dataset.role));
  }
  byId("resetFilters").addEventListener("click", resetFilters);
  byId("jobSearch").addEventListener("input", (event) => {
    clearTimeout(searchTimer);
    state.search = event.target.value.trim();
    state.page = 1;
    searchTimer = setTimeout(loadJobs, 300);
  });
  byId("clearSkill").addEventListener("click", () => {
    state.skill = "";
    state.page = 1;
    loadJobs();
  });
  byId("clearCompany").addEventListener("click", () => {
    state.company = "";
    state.page = 1;
    loadJobs();
  });
  byId("clearLocation").addEventListener("click", () => {
    state.location = "";
    state.country = "";
    state.page = 1;
    loadJobs();
  });
  byId("clearCategory").addEventListener("click", () => {
    state.category = "";
    state.page = 1;
    loadJobs();
  });
  byId("previousPage").addEventListener("click", () => {
    if (state.page > 1) {
      state.page--;
      loadJobs();
    }
  });
  byId("nextPage").addEventListener("click", () => {
    state.page++;
    loadJobs();
  });
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      renderCharts();
      const pageSize = window.innerHeight < 800 ? 7 : 8;
      if (state.pageSize !== pageSize) {
        state.pageSize = pageSize;
        state.page = 1;
        loadJobs();
      }
    }, 180);
  });
}

bindEvents();
loadDashboard();
document.fonts?.ready.then(() => {
  if (state.view === "overview" && state.metrics?.locations && typeof d3 !== "undefined") {
    renderLocations(state.metrics.locations);
  }
});
