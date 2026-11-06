const localApi = "http://localhost:5000/api/v1";
const deployedApi = "https://jobs-backend.onrender.com/api/v1";
const localHosts = new Set(["localhost", "127.0.0.1", "::1"]);

window.APP_CONFIG = {
  API_BASE: localHosts.has(window.location.hostname) ? localApi : deployedApi,
};
