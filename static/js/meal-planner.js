const picker = document.getElementById("recipe-picker");
const pickerSearch = document.getElementById("picker-search");
const pickerResults = document.getElementById("picker-results");
const pickerClose = document.getElementById("picker-close");

let activeCell = null;

function openPicker(cell) {
    activeCell = cell;
    picker.classList.add("open");
    pickerSearch.value = "";
    pickerSearch.focus();
    searchRecipes("");
}

function closePicker() {
    picker.classList.remove("open");
    activeCell = null;
}

pickerClose.addEventListener("click", closePicker);
picker.addEventListener("click", (e) => {
    if (e.target === picker) closePicker();
});

async function searchRecipes(q) {
    const res = await fetch(`/api/recipes/search?q=${encodeURIComponent(q)}`);
    const recipes = await res.json();
    pickerResults.innerHTML = "";
    if (recipes.length === 0) {
        pickerResults.innerHTML = `<p style="color: rgba(59,36,23,0.5); padding: 12px;">Nggak ketemu resep.</p>`;
        return;
    }
    recipes.forEach((r) => {
        const item = document.createElement("button");
        item.className = "picker-item";
        item.innerHTML = `<span class="cat-tag">${r.category}</span> ${r.title}`;
        item.addEventListener("click", () => assignRecipe(r));
        pickerResults.appendChild(item);
    });
}

let searchDebounce;
pickerSearch.addEventListener("input", () => {
    clearTimeout(searchDebounce);
    searchDebounce = setTimeout(() => searchRecipes(pickerSearch.value), 300);
});

async function assignRecipe(recipe) {
    if (!activeCell) return;
    const day = activeCell.dataset.day;
    const meal = activeCell.dataset.meal;

    await fetch("/api/meal-plan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ day, meal_type: meal, recipe_id: recipe.id }),
    });

    activeCell.innerHTML = `
        <div class="planner-filled">
            <span class="cat-tag">${recipe.category}</span>
            <a href="/resep/${recipe.id}">${recipe.title}</a>
            <button class="planner-remove" title="Hapus">${icon("close", 14)}</button>
        </div>
    `;
    attachCellEvents(activeCell);
    closePicker();
}

async function removeSlot(cell) {
    const day = cell.dataset.day;
    const meal = cell.dataset.meal;
    await fetch("/api/meal-plan", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ day, meal_type: meal }),
    });
    cell.innerHTML = `<button class="planner-add">+ Tambah</button>`;
    attachCellEvents(cell);
}

function attachCellEvents(cell) {
    const addBtn = cell.querySelector(".planner-add");
    if (addBtn) addBtn.addEventListener("click", () => openPicker(cell));

    const removeBtn = cell.querySelector(".planner-remove");
    if (removeBtn) removeBtn.addEventListener("click", (e) => {
        e.preventDefault();
        removeSlot(cell);
    });
}

document.querySelectorAll(".planner-cell").forEach(attachCellEvents);