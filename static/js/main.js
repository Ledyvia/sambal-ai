const grid = document.getElementById("recipe-grid");
const pagination = document.getElementById("pagination");
const jarButtons = document.querySelectorAll(".jar");
const searchInput = document.getElementById("search-input");

let currentCategory = "";
let currentSearch = "";
let currentPage = 1;

function renderRecipes(recipes) {
    grid.innerHTML = "";
    if (recipes.length === 0) {
        grid.innerHTML = `<p style="grid-column: 1/-1; color: rgba(59,36,23,0.55);">Nggak ada resep yang cocok. Coba kata kunci lain.</p>`;
        return;
    }
    recipes.forEach((r) => {
        const card = document.createElement("a");
        card.href = `/resep/${r.id}`;
        card.className = "recipe-card";
        card.innerHTML = `
            <span class="cat-tag">${r.category}</span>
            <h3>${r.title}</h3>
            <div class="meta">
                <span>${r.total_ingredients} bahan</span>
                <span>${icon("heart-filled", 14)} ${r.loves}</span>
            </div>
        `;
        grid.appendChild(card);
    });
}

function renderPagination(page, totalPages) {
    pagination.innerHTML = "";
    if (totalPages <= 1) return;
    const maxButtons = 7;
    let start = Math.max(1, page - 3);
    let end = Math.min(totalPages, start + maxButtons - 1);
    start = Math.max(1, end - maxButtons + 1);

    for (let p = start; p <= end; p++) {
        const btn = document.createElement("button");
        btn.textContent = p;
        if (p === page) btn.classList.add("active");
        btn.addEventListener("click", () => {
            currentPage = p;
            fetchRecipes();
            window.scrollTo({ top: grid.offsetTop - 100, behavior: "smooth" });
        });
        pagination.appendChild(btn);
    }
}

async function fetchRecipes() {
    const params = new URLSearchParams({
        category: currentCategory,
        search: currentSearch,
        page: currentPage,
    });
    const res = await fetch(`/api/recipes?${params}`);
    const data = await res.json();
    renderRecipes(data.recipes);
    renderPagination(data.page, data.total_pages);
}

jarButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
        jarButtons.forEach((b) => b.classList.remove("active"));
        const isActive = currentCategory === btn.dataset.category;
        if (isActive) {
            currentCategory = "";
        } else {
            btn.classList.add("active");
            currentCategory = btn.dataset.category;
        }
        currentPage = 1;
        fetchRecipes();
    });
});

let searchTimeout;
searchInput.addEventListener("input", () => {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
        currentSearch = searchInput.value;
        currentPage = 1;
        fetchRecipes();
    }, 350);
});