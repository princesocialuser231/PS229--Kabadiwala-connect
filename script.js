const API = "";

let kabadiwalas = [];
let catalog = [];
let cart = [];
let selectedKabadiwala = null;
let lastTrackingCode = null;

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

async function api(path, options) {
  const response = await fetch(API + path, options);
  const data = await response.json().catch(function () { return {}; });
  if (!response.ok) {
    throw new Error(data.error || "Request failed");
  }
  return data;
}

function showScreen(name) {
  document.querySelectorAll(".screen").forEach(function (el) {
    el.classList.remove("active");
  });
  document.getElementById("screen-" + name).classList.add("active");
  window.scrollTo(0, 0);
}

function scrollToInfo(id) {
  showScreen("home");
  setTimeout(function () {
    document.getElementById(id).scrollIntoView({ behavior: "smooth" });
  }, 50);
}

function goHome() {
  showScreen("home");
}

async function loadStats() {
  const stats = await api("/api/stats");
  const el = document.getElementById("impact-stats");
  if (!el) return;
  el.innerHTML =
    statCard("Pickups logged", stats.pickup_count || 0) +
    statCard("Completed", stats.completed_count || 0) +
    statCard("Kg diverted", Number(stats.kg_diverted || 0).toFixed(1)) +
    statCard("Collector earnings", "₹" + Number(stats.collector_earnings || 0).toFixed(0));
}

function statCard(label, value) {
  return '<div class="stat-card"><span>' + escapeHtml(label) + "</span><strong>" + escapeHtml(value) + "</strong></div>";
}

async function loadKabadiwalas(query) {
  const params = new URLSearchParams();
  if (query) params.set("q", query);
  if (window._userGeo) {
    params.set("lat", window._userGeo.lat);
    params.set("lng", window._userGeo.lng);
  }
  const qs = params.toString() ? "?" + params.toString() : "";
  const data = await api("/api/kabadiwalas" + qs);
  kabadiwalas = data.kabadiwalas;
  renderKabadiwalas();
}

function renderKabadiwalas() {
  const list = document.getElementById("kabadiwala-list");
  list.innerHTML = "";
  if (!kabadiwalas.length) {
    list.innerHTML = "<p class='muted'>No kabadiwalas match that area yet.</p>";
    return;
  }
    kabadiwalas.forEach(function (k) {
    const card = document.createElement("div");
    card.className = "kabadiwala-card";
    const distance = k.distance_km != null ? " • " + k.distance_km + " km away" : "";
    card.innerHTML =
      "<h3>" + escapeHtml(k.name) + "</h3>" +
      "<p>" + escapeHtml(k.area) + " • ⭐ " + escapeHtml(k.rating) + escapeHtml(distance) + "</p>" +
      "<p>+91 " + escapeHtml(k.phone) + "</p>" +
      "<button class='btn' type='button'>View Items</button>";
    card.querySelector("button").addEventListener("click", function () {
      openItems(k.id);
    });
    list.appendChild(card);
  });
}

async function openItems(kabadiwalaId) {
  selectedKabadiwala = kabadiwalas.find(function (k) { return k.id === kabadiwalaId; });
  const data = await api("/api/kabadiwalas/" + kabadiwalaId + "/catalog");
  catalog = data.items;

  document.getElementById("items-heading").textContent = selectedKabadiwala.name + "'s Rate List";
  document.getElementById("items-subheading").textContent = selectedKabadiwala.area + " • +91 " + selectedKabadiwala.phone;

  const grid = document.getElementById("item-grid");
  grid.innerHTML = "";
  catalog.forEach(function (item) {
    const card = document.createElement("div");
    card.className = "item-card";
    const qtyId = "qty-" + item.id;
    card.innerHTML =
      "<div class='icon'>" + escapeHtml(item.icon) + "</div>" +
      "<h4>" + escapeHtml(item.name) + "</h4>" +
      "<div class='price'>₹" + escapeHtml(item.rate_per_kg) + "/kg</div>" +
      "<input type='number' id='" + qtyId + "' min='0.5' step='0.5' value='1'>" +
      "<br><button class='btn' type='button'>Add to Cart</button>";
    card.querySelector("button").addEventListener("click", function () {
      addToCart(item.id);
    });
    grid.appendChild(card);
  });
  showScreen("items");
}

function addToCart(itemId) {
  const item = catalog.find(function (row) { return row.id === itemId; });
  const weight = parseFloat(document.getElementById("qty-" + itemId).value) || 0;
  if (weight <= 0) return;
  cart.push({
    name: item.name,
    rate_per_kg: item.rate_per_kg,
    weight_kg: weight,
    is_custom: false
  });
  updateCartCount();
  flashCart();
}

function flashCart() {
  const btn = document.getElementById("cart-button");
  btn.style.background = "#B5542E";
  btn.style.color = "#fff";
  setTimeout(function () {
    btn.style.background = "";
    btn.style.color = "";
  }, 350);
}

function addOtherItem() {
  const name = document.getElementById("other-item-name").value.trim();
  const weight = parseFloat(document.getElementById("other-item-weight").value) || 0;
  if (!name || weight <= 0) return;
  cart.push({ name: name, rate_per_kg: null, weight_kg: weight, is_custom: true });
  document.getElementById("other-item-name").value = "";
  document.getElementById("other-item-weight").value = "";
  updateCartCount();
  flashCart();
}

function updateCartCount() {
  document.getElementById("cart-count").textContent = cart.length;
}

function renderCart() {
  const container = document.getElementById("cart-items");
  const emptyMessage = document.getElementById("empty-cart-message");
  const totalBox = document.getElementById("cart-total");
  container.innerHTML = "";

  if (cart.length === 0) {
    emptyMessage.style.display = "block";
    totalBox.textContent = "";
    return;
  }

  emptyMessage.style.display = "none";
  let total = 0;
  cart.forEach(function (item, index) {
    const lineValue = item.rate_per_kg ? item.rate_per_kg * item.weight_kg : null;
    if (lineValue) total += lineValue;
    const row = document.createElement("div");
    row.className = "cart-row";
    row.innerHTML =
      "<div><strong>" + escapeHtml(item.name) + "</strong> — " + escapeHtml(item.weight_kg) + " kg" +
      (item.rate_per_kg ? " @ ₹" + escapeHtml(item.rate_per_kg) + "/kg" : " (rate to be quoted)") +
      "</div><div>" + (lineValue ? "₹" + lineValue.toFixed(0) : "") +
      " <button class='remove' type='button'>Remove</button></div>";
    row.querySelector(".remove").addEventListener("click", function () {
      removeFromCart(index);
    });
    container.appendChild(row);
  });
  totalBox.textContent = "Estimated total: ₹" + total.toFixed(0);
}

function removeFromCart(index) {
  cart.splice(index, 1);
  updateCartCount();
  renderCart();
}

function goToCheckout() {
  if (cart.length === 0 || !selectedKabadiwala) {
    showScreen("cart");
    renderCart();
    const msg = document.getElementById("empty-cart-message");
    if (msg) {
      msg.style.display = "block";
      msg.textContent = "Add items and pick a kabadiwala before requesting pickup.";
    }
    return;
  }
  showScreen("checkout");
}

function startOver() {
  cart = [];
  updateCartCount();
  document.getElementById("checkout-form").reset();
  showScreen("home");
  loadStats();
}

document.getElementById("checkout-form").addEventListener("submit", async function (event) {
  event.preventDefault();
  const errorBox = document.getElementById("checkout-error");
  errorBox.hidden = true;
  try {
    const created = await api("/api/pickups", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        kabadiwala_id: selectedKabadiwala.id,
        household_name: document.getElementById("cf-name").value,
        household_phone: document.getElementById("cf-phone").value,
        address: document.getElementById("cf-address").value,
        area: selectedKabadiwala.area,
        preferred_time: document.getElementById("cf-time").value,
        items: cart
      })
    });
    lastTrackingCode = created.tracking_code;
    document.getElementById("tracking-code").textContent = created.tracking_code;
    document.getElementById("confirmation-summary").textContent =
      created.household_name + ", pickup with " + created.kabadiwala_name +
      " is logged. Estimated payout ₹" + Number(created.estimated_total).toFixed(0) + ".";
    document.getElementById("track-link").href = "track.html?code=" + encodeURIComponent(created.tracking_code);
    showScreen("confirmation");
    cart = [];
    updateCartCount();
  } catch (err) {
    errorBox.hidden = false;
    errorBox.textContent = err.message;
  }
});

document.getElementById("area-search").addEventListener("input", function (event) {
  loadKabadiwalas(event.target.value);
});

document.getElementById("cart-button").addEventListener("click", function () {
  renderCart();
  showScreen("cart");
});

async function boot() {
  try {
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(function (pos) {
        window._userGeo = { lat: pos.coords.latitude, lng: pos.coords.longitude };
        loadKabadiwalas(document.getElementById("area-search").value);
      }, function () {}, { timeout: 4000 });
    }
    await Promise.all([loadKabadiwalas(), loadStats()]);
  } catch (err) {
    document.getElementById("kabadiwala-list").innerHTML =
      "<p class='banner'>Backend is not running. Start it with <code>python run.py</code> then refresh.</p>";
  }
}

boot();
