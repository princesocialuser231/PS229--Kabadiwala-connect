/* ----------------------------------------------------------
       FAKE DATA -- for the demo only. Edit these lists to add
       more kabadiwalas or change item prices.
    ---------------------------------------------------------- */

    let kabadiwalas = [
      { id: 1, name: "Prince Kumar", area: "Sector 12", phone: "+91 9310176402", rating: "4.6" },
      { id: 2, name: "jha scrap dealers", area: "Sector 9",  phone: "+91 7079840944", rating: "4.3" },
      { id: 3, name: "Green Scrap Co.", area: "Block C",  phone: "+91 00000000000", rating: "4.8" }
    ];

    // Same catalog is shown for every kabadiwala in this demo version.
    let catalog = [
      { name: "Newspaper",     rate: 14, icon: "📰" },
      { name: "Cardboard",     rate: 11, icon: "📦" },
      { name: "Plastic Bottles", rate: 22, icon: "🧴" },
      { name: "Iron Scrap",    rate: 28, icon: "🔩" },
      { name: "Aluminum",      rate: 32, icon: "🥫" },
      { name: "E-waste",       rate: 35, icon: "🔌" },
      { name: "Glass Bottles", rate: 8,  icon: "🍾" },
      { name: "Copper Wire",   rate: 55, icon: "🧵" }
    ];

    let cart = [];               // items the user has added
    let selectedKabadiwala = null;


    /* ---------- SCREEN SWITCHING ---------- */
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


    /* ---------- HOME SCREEN: render kabadiwala list ---------- */
    function renderKabadiwalas() {
      const list = document.getElementById("kabadiwala-list");
      list.innerHTML = "";
      kabadiwalas.forEach(function (k) {
        const card = document.createElement("div");
        card.className = "kabadiwala-card";
        card.innerHTML = `
          <h3>${k.name}</h3>
          <p>${k.area} • ⭐ ${k.rating}</p>
          <p>${k.phone}</p>
          <button class="btn" onclick="openItems(${k.id})">View Items</button>
        `;
        list.appendChild(card);
      });
    }


    /* ---------- ITEMS SCREEN ---------- */
    function openItems(kabadiwalaId) {
      selectedKabadiwala = kabadiwalas.find(function (k) { return k.id === kabadiwalaId; });

      document.getElementById("items-heading").textContent = selectedKabadiwala.name + "'s Rate List";
      document.getElementById("items-subheading").textContent = selectedKabadiwala.area + " • " + selectedKabadiwala.phone;

      const grid = document.getElementById("item-grid");
      grid.innerHTML = "";
      catalog.forEach(function (item, index) {
        const card = document.createElement("div");
        card.className = "item-card";
        card.innerHTML = `
          <div class="icon">${item.icon}</div>
          <h4>${item.name}</h4>
          <div class="price">₹${item.rate}/kg</div>
          <div><input type="number" id="qty-${index}" placeholder="kg" min="0" value="1"></div>
          <button class="btn" onclick="addToCart(${index})">Add to Cart</button>
        `;
        grid.appendChild(card);
      });

      showScreen("items");
    }

    function addToCart(index) {
      const item = catalog[index];
      const weight = parseFloat(document.getElementById("qty-" + index).value) || 0;
      if (weight <= 0) return;

      cart.push({
        name: item.name,
        rate: item.rate,
        weight: weight
      });

      updateCartCount();
    }

    function addOtherItem() {
      const name = document.getElementById("other-item-name").value;
      const weight = parseFloat(document.getElementById("other-item-weight").value) || 0;
      if (name === "" || weight <= 0) return;

      cart.push({
        name: name + " (custom)",
        rate: null,   // no fixed rate -- kabadiwala will quote this in person
        weight: weight
      });

      document.getElementById("other-item-name").value = "";
      document.getElementById("other-item-weight").value = "";
      updateCartCount();
    }

    function updateCartCount() {
      document.getElementById("cart-count").textContent = cart.length;
    }


    /* ---------- CART SCREEN ---------- */
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
        const lineValue = item.rate ? item.rate * item.weight : null;
        if (lineValue) total += lineValue;

        const row = document.createElement("div");
        row.className = "cart-row";
        row.innerHTML = `
          <div>
            <strong>${item.name}</strong> — ${item.weight} kg
            ${item.rate ? " @ ₹" + item.rate + "/kg" : " (rate to be quoted)"}
          </div>
          <div>
            ${lineValue ? "₹" + lineValue.toFixed(0) : ""}
            <button class="remove" onclick="removeFromCart(${index})">Remove</button>
          </div>
        `;
        container.appendChild(row);
      });

      totalBox.textContent = "Estimated total: ₹" + total.toFixed(0);
    }

    function removeFromCart(index) {
      cart.splice(index, 1);
      updateCartCount();
      renderCart();
    }


    /* ---------- CHECKOUT SCREEN ---------- */
    function goToCheckout() {
      if (cart.length === 0) return;
      showScreen("checkout");
    }

    // PASTE YOUR OWN FORMSPREE ENDPOINT HERE (from formspree.io after creating your form)
    const FORMSPREE_ENDPOINT = "https://formspree.io/f/moeqlgnb";

    document.getElementById("checkout-form").addEventListener("submit", function (event) {
      event.preventDefault();

      const name = document.getElementById("cf-name").value;
      const phone = document.getElementById("cf-phone").value;
      const address = document.getElementById("cf-address").value;
      const time = document.getElementById("cf-time").value;

      // Turn the cart into a readable block of text to send along with the form
      const cartSummary = cart.map(function (item) {
        return item.name + " - " + item.weight + "kg" +
          (item.rate ? " @ ₹" + item.rate + "/kg" : " (rate to be quoted)");
      }).join(", ");

      // Package everything into a FormData object -- this is what gets sent to Formspree
      const formData = new FormData();
      formData.append("name", name);
      formData.append("phone", phone);
      formData.append("address", address);
      formData.append("preferred_time", time);
      formData.append("kabadiwala", selectedKabadiwala ? selectedKabadiwala.name : "Not selected");
      formData.append("cart_items", cartSummary);

      fetch(FORMSPREE_ENDPOINT, {
        method: "POST",
        headers: { "Accept": "application/json" },
        body: formData
      })
      .then(function (response) {
        if (!response.ok) {
          throw new Error("Formspree returned an error");
        }
        const summary = `${name}, we've noted your pickup request for ` +
          `${cart.length} item(s) with ${selectedKabadiwala ? selectedKabadiwala.name : "a kabadiwala"} ` +
          `at ${address}, preferred time ${time.replace("T", " ")}.`;

        document.getElementById("confirmation-summary").textContent = summary;
        showScreen("confirmation");
      })
      .catch(function (error) {
        alert("Something went wrong sending your request. Please check your internet connection and try again.");
      });
    });

    function startOver() {
      cart = [];
      updateCartCount();
      document.getElementById("checkout-form").reset();
      showScreen("home");
    }


    /* ---------- INITIAL LOAD ---------- */
    renderKabadiwalas();

    // Re-render the cart screen every time it's opened, so it's always up to date
    document.getElementById("cart-button").addEventListener("click", renderCart);
