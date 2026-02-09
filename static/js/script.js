document.addEventListener("DOMContentLoaded", function () {
    let searchForm = document.querySelector('.search-form');
    let shoppingCart = document.querySelector('.shopping-cart');
    let navbar = document.querySelector('.navbar');

    // Ensure elements exist before adding event listeners
    document.querySelector('#search-btn')?.addEventListener("click", () => {
        searchForm.classList.toggle('active');
        shoppingCart?.classList.remove('active');
        navbar?.classList.remove('active');
    });

    document.querySelector('#cart-btn')?.addEventListener("click", () => {
        shoppingCart.classList.toggle('active');
        searchForm?.classList.remove('active');
    });

    document.querySelector('#menu-btn')?.addEventListener("click", () => {
        navbar.classList.toggle('active');
        shoppingCart?.classList.remove('active');
        searchForm?.classList.remove('active');
    });

    window.onscroll = () => {
        searchForm?.classList.remove('active');
        shoppingCart?.classList.remove('active');
        navbar?.classList.remove('active');
    };

    // Cart functionality
    let cart = JSON.parse(localStorage.getItem("cart")) || [];
    if (!Array.isArray(cart)) cart = [];

    function renderCart() {
        const cartItemsContainer = document.getElementById("cart-items");
        if (!cartItemsContainer) {
            console.error("Cart container not found!");
            return;
        }

        cartItemsContainer.innerHTML = "";

        cart.forEach((item, index) => {
            let cartItem = document.createElement("div");
            cartItem.classList.add("box");
            cartItem.innerHTML = `
                <i class="fas fa-trash remove-btn" data-index="${index}"></i>
                <img src="${item.image}" alt="${item.name}">
                <div class="content">
                    <h3>${item.name}</h3>
                    <span class="price">${item.price} Rs.</span>
                    <span class="quantity">Qty: ${item.quantity}</span>
                </div>
            `;
            cartItemsContainer.appendChild(cartItem);
        });

        // Attach event listeners to remove buttons
        document.querySelectorAll(".remove-btn").forEach(button => {
            button.addEventListener("click", function () {
                let index = this.getAttribute("data-index");
                removeFromCart(index);
            });
        });
    }

    function removeFromCart(index) {
        cart.splice(index, 1);
        localStorage.setItem("cart", JSON.stringify(cart));
        renderCart();
    }

    function checkoutCart() {
        let email = document.getElementById("email-input").value.trim();
        if (!email) {
            alert("Please enter a valid email address.");
            return;
        }

        if (cart.length === 0) {
            alert("Your cart is empty!");
            return;
        }

        let cartDetails = cart.map(item => `${item.name} (Qty: ${item.quantity}) - ${item.price} Rs.`).join("\n");

        // Prepare form data for Django
        let formData = new FormData();
        formData.append("email", email);
        formData.append("message", `Order Details:\n${cartDetails}`);

        // Send the POST request to Django
        fetch(SEND_QUERY_URL, {
            method: "POST",
            headers: { "X-CSRFToken": document.querySelector("[name=csrfmiddlewaretoken]").value },
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                alert("Order placed successfully! Please wait for a response from us through mail");
                cart=[]
                localStorage.setItem("cart", JSON.stringify(cart));
                renderCart(); // Update UI
            } else {
                alert("Error: " + data.error);
            }
        })
        .catch(error => console.error("Error:", error));
    }

    // Attach event listener to checkout button
    document.getElementById("checkout-btn")?.addEventListener("click", checkoutCart);

    function addToCart(event) {
        event.preventDefault(); // Prevent default anchor behavior
    
        let button = event.target;
        let productBox = button.closest(".box"); // Get the product container
    
        // Extract details from the HTML
        let name = button.getAttribute("data-name");
        let price = button.getAttribute("data-price");
        let image = productBox.querySelector("img").src; // Get the image source
    
        // Check if item already exists in the cart
        let existingItem = cart.find(item => item.name === name);
        if (existingItem) {
            existingItem.quantity += 1; // Increase quantity if it exists
        } else {
            cart.push({ name, price, image, quantity: 1 });
        }
    
        // Save updated cart to localStorage
        localStorage.setItem("cart", JSON.stringify(cart));
        renderCart(); // Update the UI
    }
    
    // Attach event listeners to all "Add to Cart" buttons
    document.querySelectorAll(".btn").forEach(button => {
        button.addEventListener("click", addToCart);
    });
    
    let queryForm = document.getElementById("query-form");

    if (queryForm) {
        queryForm.addEventListener("submit", function (event) {
            event.preventDefault(); // Prevent default form submission

            let formData = new FormData(queryForm); // Collect form data

            fetch(SEND_QUERY_URL, {
                method: "POST",
                headers: {
                    "X-CSRFToken": formData.get("csrfmiddlewaretoken"), // CSRF token
                },
                body: formData // Send as FormData (not JSON)
            })
            .then(response => response.json()) // Parse JSON response
            .then(data => {
                if (data.success) {
                    alert("✅ Query sent successfully!");
                    queryForm.reset(); // Clear the form
                } else {
                    alert("❌ Error: " + (data.error || "Something went wrong"));
                }
            })
            .catch(error => {
                console.error("Error:", error);
                alert("❌ Network error! Please try again.");
            });
        });
    }
    


    renderCart(); // Render cart on page load
});
