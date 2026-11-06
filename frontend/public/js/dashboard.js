const API_BASE = (window.APP_CONFIG && window.APP_CONFIG.API_BASE) || "http://localhost:5000/api/v1";

const roleFilter = document.getElementById("roleFilter");
const sourceFilter = document.getElementById("sourceFilter");
const refreshBtn = document.getElementById("refreshBtn");
const runEtlBtn = document.getElementById("runEtlBtn");
const statusLine = document.getElementById("statusLine");
const jobsTableBody = document.getElementById("jobsTableBody");
const tableMeta = document.getElementById("tableMeta");

async function fetchJSON(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, options);
  if (!res.ok) {
    throw new Error(`API ${res.status}: ${await res.text()}`);
  }
  return res.json();
}

function setStatus(message, isError = false) {
  statusLine.textContent = message;
  statusLine.style.color = isError ? "var(--danger)" : "var(--text-dim)";
}

function formatMoney(value) {
  if (value === null || value === undefined) return "n/a";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value);
}

function applyKpis(overview) {
  document.getElementById("kpiTotalJobs").textContent = overview.total_jobs.toLocaleString();
  document.getElementById("kpiCompanies").textContent = overview.total_companies.toLocaleString();
  document.getElementById("kpiAvgSalary").textContent = formatMoney(overview.avg_salary_usd);
  document.getElementById("kpiMedianSalary").textContent = formatMoney(overview.median_salary_usd);
  document.getElementById("kpiUniqueTitles").textContent = (overview.unique_titles || 0).toLocaleString();
  document.getElementById("kpiTopEmployer").textContent = overview.top_employer || "n/a";
  document.getElementById("kpiTopEmployerCount").textContent = overview.top_employer_jobs
    ? `${overview.top_employer_jobs.toLocaleString()} vacancies`
    : "no data";
}

function renderSkills(data) {
  const svg = d3.select("#skillsChart");
  svg.selectAll("*").remove();

  const width = svg.node().clientWidth;
  const height = svg.node().clientHeight;
  const margin = { top: 10, right: 12, bottom: 50, left: 40 };

  if (!data.length) return;

  const x = d3
    .scaleBand()
    .domain(data.map((d) => d.skill))
    .range([margin.left, width - margin.right])
    .padding(0.25);

  const y = d3
    .scaleLinear()
    .domain([0, d3.max(data, (d) => d.count)])
    .nice()
    .range([height - margin.bottom, margin.top]);

  svg
    .append("g")
    .selectAll("rect")
    .data(data)
    .join("rect")
    .attr("x", (d) => x(d.skill))
    .attr("width", x.bandwidth())
    .attr("y", height - margin.bottom)
    .attr("height", 0)
    .attr("fill", "#3dd6d0")
    .transition()
    .duration(650)
    .attr("y", (d) => y(d.count))
    .attr("height", (d) => height - margin.bottom - y(d.count));

  svg
    .append("g")
    .attr("transform", `translate(0,${height - margin.bottom})`)
    .call(d3.axisBottom(x))
    .selectAll("text")
    .style("fill", "#e9fcff")
    .attr("transform", "rotate(-35)")
    .style("text-anchor", "end")
    .style("font-size", "10px");

  svg
    .append("g")
    .attr("transform", `translate(${margin.left},0)`)
    .call(d3.axisLeft(y).ticks(5))
    .selectAll("text")
    .style("fill", "#e9fcff")
    .style("font-size", "10px");
}

function renderSalaryBands(data) {
  const svg = d3.select("#salaryChart");
  svg.selectAll("*").remove();

  const width = svg.node().clientWidth;
  const height = svg.node().clientHeight;
  const radius = Math.min(width, height) / 2 - 14;
  const group = svg.append("g").attr("transform", `translate(${width / 2},${height / 2})`);

  if (!data.length) return;

  const color = d3.scaleOrdinal().domain(data.map((d) => d.band)).range(["#ffd166", "#3dd6d0", "#6ea8fe", "#ff8c42"]);

  const pie = d3.pie().value((d) => d.count).sort(null);
  const arc = d3.arc().innerRadius(radius * 0.48).outerRadius(radius);

  group
    .selectAll("path")
    .data(pie(data))
    .join("path")
    .attr("d", arc)
    .attr("fill", (d) => color(d.data.band))
    .attr("stroke", "rgba(6,22,34,0.9)")
    .attr("stroke-width", 2)
    .append("title")
    .text((d) => `${d.data.band}: ${d.data.count}`);

  group
    .append("text")
    .attr("text-anchor", "middle")
    .attr("dy", "0.35em")
    .style("font-size", "11px")
    .style("fill", "#e9fcff")
    .text("Salary share");
}

function renderLocations(data) {
  const svg = d3.select("#locationChart");
  svg.selectAll("*").remove();

  const width = svg.node().clientWidth;
  const height = svg.node().clientHeight;

  if (!data.length) return;

  const maxCount = d3.max(data, (d) => d.count) || 1;
  const sizeScale = d3.scaleSqrt().domain([1, maxCount]).range([12, 44]);

  const words = data.map((d) => ({
    text: d.location,
    size: sizeScale(d.count),
    count: d.count,
    country: d.country,
  }));

  if (!d3.layout || !d3.layout.cloud) {
    svg
      .append("text")
      .attr("x", width / 2)
      .attr("y", height / 2)
      .attr("text-anchor", "middle")
      .style("fill", "#9bc0d0")
      .style("font-size", "12px")
      .text("Word cloud library not loaded");
    return;
  }

  d3.layout
    .cloud()
    .size([width, height])
    .words(words)
    .padding(4)
    .rotate(() => (Math.random() > 0.85 ? 90 : 0))
    .font("Space Grotesk")
    .fontSize((d) => d.size)
    .on("end", (layoutWords) => {
      const color = d3.scaleSequential().domain([1, maxCount]).interpolator(d3.interpolateTurbo);
      svg
        .append("g")
        .attr("transform", `translate(${width / 2},${height / 2})`)
        .selectAll("text")
        .data(layoutWords)
        .join("text")
        .style("font-family", "Space Grotesk")
        .style("font-size", (d) => `${d.size}px`)
        .style("font-weight", "700")
        .style("fill", (d) => color(d.count))
        .attr("text-anchor", "middle")
        .attr("transform", (d) => `translate(${d.x},${d.y}) rotate(${d.rotate})`)
        .text((d) => d.text)
        .append("title")
        .text((d) => `${d.text} (${d.country}): ${d.count}`);
    })
    .start();
}

function renderTimeline(data) {
  const svg = d3.select("#timelineChart");
  svg.selectAll("*").remove();

  if (!data.length) return;

  const width = svg.node().clientWidth;
  const height = svg.node().clientHeight;
  const margin = { top: 14, right: 14, bottom: 36, left: 42 };

  const parsed = data
    .map((d) => ({ date: new Date(d.week), count: d.count }))
    .filter((d) => !Number.isNaN(d.date.getTime()));

  const x = d3
    .scaleTime()
    .domain(d3.extent(parsed, (d) => d.date))
    .range([margin.left, width - margin.right]);

  const y = d3
    .scaleLinear()
    .domain([0, d3.max(parsed, (d) => d.count)])
    .nice()
    .range([height - margin.bottom, margin.top]);

  const line = d3
    .line()
    .x((d) => x(d.date))
    .y((d) => y(d.count))
    .curve(d3.curveCatmullRom.alpha(0.5));

  svg
    .append("path")
    .datum(parsed)
    .attr("fill", "none")
    .attr("stroke", "#ffd166")
    .attr("stroke-width", 2.5)
    .attr("d", line);

  svg
    .append("g")
    .attr("transform", `translate(0,${height - margin.bottom})`)
    .call(d3.axisBottom(x).ticks(6))
    .selectAll("text")
    .style("fill", "#e9fcff")
    .style("font-size", "10px");

  svg
    .append("g")
    .attr("transform", `translate(${margin.left},0)`)
    .call(d3.axisLeft(y).ticks(5))
    .selectAll("text")
    .style("fill", "#e9fcff")
    .style("font-size", "10px");

  svg
    .append("g")
    .selectAll("circle")
    .data(parsed)
    .join("circle")
    .attr("cx", (d) => x(d.date))
    .attr("cy", (d) => y(d.count))
    .attr("r", 3)
    .attr("fill", "#3dd6d0");
}

function renderEmployers(data) {
  const svg = d3.select("#employerChart");
  svg.selectAll("*").remove();

  if (!data.length) return;

  const width = svg.node().clientWidth;
  const height = svg.node().clientHeight;
  const margin = { top: 10, right: 16, bottom: 12, left: 140 };

  const y = d3
    .scaleBand()
    .domain(data.map((d) => d.company))
    .range([margin.top, height - margin.bottom])
    .padding(0.2);

  const x = d3
    .scaleLinear()
    .domain([0, d3.max(data, (d) => d.count)])
    .nice()
    .range([margin.left, width - margin.right]);

  svg
    .append("g")
    .selectAll("rect")
    .data(data)
    .join("rect")
    .attr("x", margin.left)
    .attr("y", (d) => y(d.company))
    .attr("height", y.bandwidth())
    .attr("width", 0)
    .attr("fill", "#6ea8fe")
    .transition()
    .duration(650)
    .attr("width", (d) => x(d.count) - margin.left);

  svg
    .append("g")
    .attr("transform", `translate(0,${height - margin.bottom})`)
    .call(d3.axisBottom(x).ticks(5))
    .selectAll("text")
    .style("fill", "#e9fcff")
    .style("font-size", "10px");

  svg
    .append("g")
    .attr("transform", `translate(${margin.left},0)`)
    .call(d3.axisLeft(y).tickFormat((name) => (name.length > 24 ? `${name.slice(0, 24)}...` : name)))
    .selectAll("text")
    .style("fill", "#e9fcff")
    .style("font-size", "10px");
}

function renderJobsTable(payload) {
  jobsTableBody.replaceChildren();
  payload.items.forEach((job) => {
    const tr = document.createElement("tr");
    const titleCell = document.createElement("td");
    const safeUrl = safeJobUrl(job.url);
    if (safeUrl) {
      const link = document.createElement("a");
      link.href = safeUrl;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = job.title;
      titleCell.appendChild(link);
    } else {
      titleCell.textContent = job.title;
    }
    tr.appendChild(titleCell);
    for (const value of [job.company, job.role_family, job.location, job.source]) {
      const cell = document.createElement("td");
      cell.textContent = value ?? "";
      tr.appendChild(cell);
    }
    jobsTableBody.appendChild(tr);
  });
  tableMeta.textContent = `${payload.total.toLocaleString()} total rows`;
}

function safeJobUrl(value) {
  try {
    const url = new URL(value);
    if (!["https:", "http:"].includes(url.protocol) || url.username || url.password) return null;
    return url.href;
  } catch {
    return null;
  }
}

function requestEtlToken() {
  const dialog = document.getElementById("etlAuthDialog");
  const input = document.getElementById("etlToken");
  input.value = "";
  dialog.returnValue = "";
  return new Promise((resolve) => {
    dialog.addEventListener("close", () => {
      const token = dialog.returnValue === "run" ? input.value : null;
      input.value = "";
      resolve(token);
    }, { once: true });
    dialog.showModal();
  });
}

async function loadDashboard() {
  setStatus("Loading dashboard data...");

  const role = roleFilter.value;
  const source = sourceFilter.value;

  const query = new URLSearchParams({ page: "1", page_size: "25" });
  const metricQuery = new URLSearchParams();
  if (role !== "all") query.set("role_family", role);
  if (role !== "all") metricQuery.set("role_family", role);
  if (source !== "all") query.set("source", source);
  if (source !== "all") metricQuery.set("source", source);

  const metricSuffix = metricQuery.toString() ? `?${metricQuery.toString()}` : "";
  const skillsSuffix = metricQuery.toString()
    ? `?${metricQuery.toString()}&limit=12`
    : "?limit=12";
  const locationsSuffix = metricQuery.toString()
    ? `?${metricQuery.toString()}&limit=16`
    : "?limit=16";
  const employersSuffix = metricQuery.toString()
    ? `?${metricQuery.toString()}&limit=10`
    : "?limit=10";

  try {
    const [overview, skills, salaryBands, locations, timeline, employers, jobs] = await Promise.all([
      fetchJSON(`/metrics/overview${metricSuffix}`),
      fetchJSON(`/metrics/skills${skillsSuffix}`),
      fetchJSON(`/metrics/salary-bands${metricSuffix}`),
      fetchJSON(`/metrics/locations${locationsSuffix}`),
      fetchJSON(`/metrics/timeline${metricSuffix}`),
      fetchJSON(`/metrics/employers${employersSuffix}`),
      fetchJSON(`/jobs?${query.toString()}`),
    ]);

    applyKpis(overview);
    renderSkills(skills);
    renderSalaryBands(salaryBands);
    renderLocations(locations);
    renderTimeline(timeline);
    renderEmployers(employers);
    renderJobsTable(jobs);

    setStatus(`Updated at ${new Date().toLocaleTimeString()}`);
  } catch (error) {
    setStatus(`Failed to load dashboard: ${error.message}`, true);
  }
}

async function runEtl() {
  runEtlBtn.disabled = true;

  try {
    const token = await requestEtlToken();
    if (!token) return;
    setStatus("Running ETL. This can take a few minutes for 5000 cleaned rows...");
    const result = await fetchJSON("/etl/run", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ target_rows: 5000 }),
    });
    const sourceStats = Object.entries(result.source_rows || {})
      .map(([name, count]) => `${name}:${count}`)
      .join(", ");
    const notes = (result.notes || []).join(" ");
    setStatus(
      `ETL done. scraped=${result.scraped_rows}, cleaned=${result.cleaned_rows}, inserted=${result.inserted_rows}, updated=${result.updated_rows}. sources=[${sourceStats}] ${notes}`.trim()
    );
    await loadDashboard();
  } catch (error) {
    setStatus(`ETL failed: ${error.message}`, true);
  } finally {
    runEtlBtn.disabled = false;
  }
}

refreshBtn.addEventListener("click", loadDashboard);
runEtlBtn.addEventListener("click", runEtl);
roleFilter.addEventListener("change", loadDashboard);
sourceFilter.addEventListener("change", loadDashboard);

loadDashboard();
