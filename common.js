async function api(path, options) {
  const opts = options || {};
  opts.headers = Object.assign({ "Content-Type": "application/json" }, opts.headers || {});
  const token = sessionStorage.getItem("kc_token");
  if (token) opts.headers["Authorization"] = "Bearer " + token;
  const response = await fetch(path, opts);
  const data = await response.json().catch(function () { return {}; });
  if (!response.ok) throw new Error(data.error || "Request failed");
  return data;
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function badge(status) {
  return "<span class='badge " + escapeHtml(status) + "'>" + escapeHtml(status.replace("_", " ")) + "</span>";
}
