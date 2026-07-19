const mpaiMessages = document.getElementById("mpai-messages");
const mpaiInput = document.getElementById("mpai-input");
const mpaiGenerateBtn = document.getElementById("mpai-generate");
const mpaiHariInput = document.getElementById("mpai-hari");
const mpaiOrangInput = document.getElementById("mpai-orang");

// ---------- Lokasi user (buat link Google Maps 'toko terdekat' yang akurat) ----------
// Sama kayak di chat.js — diminta pas generate DIKLIK (interaksi user), bukan
// otomatis pas halaman load, biar browser gak nge-block permintaannya.
let mpaiUserLocation = null; // {lat, lng} atau null kalau ditolak/gagal
let mpaiLocationRequested = false;

function mpaiRequestLocationOnce() {
    if (mpaiLocationRequested || !navigator.geolocation) return Promise.resolve(mpaiUserLocation);
    mpaiLocationRequested = true;
    return new Promise((resolve) => {
        navigator.geolocation.getCurrentPosition(
            (pos) => {
                mpaiUserLocation = { lat: pos.coords.latitude, lng: pos.coords.longitude };
                resolve(mpaiUserLocation);
            },
            () => {
                // ditolak/gagal -> tetap null, backend fallback ke pencarian generik
                // yang di-scope ke Yogyakarta (lihat services/shopping_links.py)
                resolve(null);
            },
            { timeout: 8000 }
        );
    });
}

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text == null ? "" : String(text);
    return div.innerHTML;
}

// ---------- Linkify balasan bot + kasih warna beda per jenis link ----------
// Video tutorial (YouTube), toko fisik terdekat (Google Maps), dan marketplace
// (Tokopedia/dst) dibedain warnanya biar user langsung ngerti jenis link-nya
// tanpa harus baca URL-nya dulu.
function classifyLink(url) {
    if (/youtube\.com|youtu\.be/i.test(url)) return "link-video";
    if (/google\.[a-z.]+\/maps/i.test(url)) return "link-maps";
    return "link-marketplace";
}

function linkify(escapedText) {
    const urlPattern = /(https?:\/\/[^\s]+)/g;
    return escapedText.replace(urlPattern, (url) => {
        const cls = classifyLink(url);
        return `<a href="${url}" target="_blank" rel="noopener noreferrer" class="${cls}">${url}</a>`;
    });
}

function mpaiAppend(text, sender, isLoading = false) {
    const bubble = document.createElement("div");
    bubble.className = `chat-msg ${sender}${isLoading ? " loading" : ""}`;
    if (sender === "bot") {
        bubble.innerHTML = linkify(escapeHtml(text));
    } else {
        bubble.textContent = text;
    }
    mpaiMessages.appendChild(bubble);
    mpaiMessages.scrollTop = mpaiMessages.scrollHeight;
    return bubble;
}

function renderPlanGrid(plan) {
    const bySlot = {};
    (plan || []).forEach((p) => { bySlot[`${p.day_of_week}|${p.meal_type}`] = p; });

    let html = '<div class="planner-corner"></div>';
    MPAI_DAYS.forEach((day) => { html += `<div class="planner-day-label">${escapeHtml(day)}</div>`; });

    MPAI_MEAL_TYPES.forEach((meal) => {
        html += `<div class="planner-meal-label">${escapeHtml(meal)}</div>`;
        MPAI_DAYS.forEach((day) => {
            const slot = bySlot[`${day}|${meal}`];
            if (slot) {
                html += `
                    <div class="planner-cell">
                        <div class="planner-filled">
                            <span class="cat-tag">${escapeHtml(slot.category)}</span>
                            <a href="/resep/${slot.recipe_id}">${escapeHtml(slot.title)}</a>
                        </div>
                    </div>`;
            } else {
                html += `<div class="planner-cell"><span style="opacity:.4; font-size:.8rem;">—</span></div>`;
            }
        });
    });
    return html;
}

// Ditampilin LANGSUNG di halaman (di luar kertas belanja) — sengaja cuma
// hint singkat, gak nampilin item satu-satu lagi (biar gak dobel sama isi
// kertas). Detail lengkap + tombol Cari/Peta ada di kertas (renderReceiptBody).
function renderShoppingLinks(items) {
    if (items.length === 0) {
        return "<p>Semua bahan yang dibutuhkan minggu ini udah kamu punya. Gak perlu belanja!</p>";
    }
    return '<p class="mpai-hint" style="margin:0;">Klik tombol di atas buat lihat rincian bahan, jumlah, harga, sama link belanjanya.</p>';
}

function formatRupiah(value) {
    return Math.round(value || 0).toLocaleString("id-ID");
}

// Isi kertas/struk belanja: nama bahan, jumlah, harga, & tombol Cari/Peta per
// item (gak ada "dipakai di X resep" — itu cuma noise buat versi yang dibawa
// belanja).
function renderReceiptBody(shoppingResult) {
    let html = "";
    if (shoppingResult.catatan_porsi) {
        html += `<p class="mpai-hint" style="margin-bottom:10px;">${escapeHtml(shoppingResult.catatan_porsi)}</p>`;
    }
    const items = shoppingResult.shopping_list || [];
    if (items.length === 0) {
        return html + "<p>Semua bahan yang dibutuhkan minggu ini udah kamu punya. Gak perlu belanja!</p>";
    }
    if (shoppingResult.total_harga_estimasi) {
        html += `
            <div class="receipt-total">
                <strong style="font-size:1.05rem;">Perkiraan total belanja: ~Rp${formatRupiah(shoppingResult.total_harga_estimasi)}</strong>
                <p class="mpai-hint" style="margin:6px 0 0;">${escapeHtml(shoppingResult.harga_disclaimer || "")}</p>
            </div>`;
    }
    html += '<div class="receipt-items">';
    items.forEach((item) => {
        html += `
            <div class="receipt-item-row">
                <div class="receipt-item-top">
                    <span class="receipt-item-name">${escapeHtml(item.bahan)}</span>
                    <span class="receipt-item-price">~Rp${formatRupiah(item.harga_estimasi)}${item.harga_kasar ? '<span title="Bahan ini gak ada di tabel referensi harga, jadi pakai harga generik">*</span>' : ""}</span>
                </div>
                <div class="receipt-item-bottom">
                    <span class="receipt-item-qty">${escapeHtml(item.jumlah || "cek pas belanja")}</span>
                    <span class="receipt-item-actions">
                        <a href="${item.marketplace_url}" target="_blank" rel="noopener" class="receipt-link-btn cari">Cari</a>
                        ${item.maps_url ? `<a href="${item.maps_url}" target="_blank" rel="noopener" class="receipt-link-btn peta">${icon("map-pin", 12)} Peta</a>` : ""}
                    </span>
                </div>
            </div>`;
    });
    html += "</div>";
    return html;
}

// ---------- Toggle kertas/struk belanja (modal "Lihat List Belanjaan") ----------
const lihatBelanjaBtn = document.getElementById("lihat-belanja-btn");
const shoppingReceiptOverlay = document.getElementById("shopping-receipt-overlay");
const receiptCloseBtn = document.getElementById("receipt-close");

if (lihatBelanjaBtn && shoppingReceiptOverlay) {
    lihatBelanjaBtn.addEventListener("click", () => shoppingReceiptOverlay.classList.add("open"));
    receiptCloseBtn.addEventListener("click", () => shoppingReceiptOverlay.classList.remove("open"));
    shoppingReceiptOverlay.addEventListener("click", (e) => {
        if (e.target === shoppingReceiptOverlay) shoppingReceiptOverlay.classList.remove("open");
    });
}

async function generateMealPlan() {
    const message = mpaiInput.value.trim();
    const jumlahHari = parseInt(mpaiHariInput.value, 10) || 7;
    const jumlahOrang = parseInt(mpaiOrangInput.value, 10) || 4;

    await mpaiRequestLocationOnce();

    if (message) mpaiAppend(message, "user");
    mpaiInput.value = "";
    mpaiGenerateBtn.disabled = true;
    const loadingBubble = mpaiAppend(
        "Menyusun rencana menu seminggu & menghitung belanja... (bisa makan waktu beberapa detik)",
        "bot", true,
    );

    try {
        const res = await fetch("/api/meal-plan-ai/generate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                message,
                jumlah_hari: jumlahHari,
                jumlah_orang: jumlahOrang,
                lat: mpaiUserLocation ? mpaiUserLocation.lat : null,
                lng: mpaiUserLocation ? mpaiUserLocation.lng : null,
            }),
        });
        const data = await res.json();
        loadingBubble.remove();

        if (res.status === 401) {
            mpaiAppend("Sesi login kamu habis, silakan login lagi.", "bot");
            setTimeout(() => { window.location.href = "/login"; }, 1200);
            return;
        }

        mpaiAppend(data.reply || "Maaf, terjadi kendala.", "bot");

        if (data.meta && data.meta.save_error) {
            const warnBubble = mpaiAppend(
                "Rencana menu & daftar belanja di atas TIDAK berhasil disimpan ke database " +
                "(jadi tombol Export PDF nanti bakal bilang \"belum ada daftar belanja\", dan hasil " +
                "ini akan hilang kalau halaman di-reload). Detail error: " + data.meta.save_error,
                "bot"
            );
            warnBubble.classList.add("warning");
            warnBubble.innerHTML = icon("warning", 16) + " " + warnBubble.innerHTML;
        }

        // Render langsung dari hasil response, TANPA reload halaman — biar
        // chat yang baru aja muncul gak ke-reset pas lagi dibaca/discroll.
        if (data.meta && data.meta.plan) {
            const planSection = document.getElementById("ai-plan-section");
            const planGrid = document.getElementById("ai-plan-grid");
            planGrid.innerHTML = renderPlanGrid(data.meta.plan);
            planSection.style.display = "";
        }
        if (data.meta && data.meta.shopping_result) {
            const shoppingSection = document.getElementById("ai-shopping-section");
            const shoppingBody = document.getElementById("ai-shopping-body");
            const receiptBody = document.getElementById("receipt-body");
            shoppingBody.innerHTML = renderShoppingLinks(data.meta.shopping_result.shopping_list || []);
            if (receiptBody) receiptBody.innerHTML = renderReceiptBody(data.meta.shopping_result);
            shoppingSection.style.display = "";
        }
    } catch (err) {
        loadingBubble.remove();
        mpaiAppend("Maaf, gagal terhubung ke server. Coba lagi ya.", "bot");
    } finally {
        mpaiGenerateBtn.disabled = false;
    }
}

mpaiGenerateBtn.addEventListener("click", generateMealPlan);
mpaiInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
        e.preventDefault();
        generateMealPlan();
    }
});

const mpaiClearBtn = document.getElementById("mpai-clear");
mpaiClearBtn.addEventListener("click", async () => {
    if (!confirm("Hapus chat & rencana menu yang tersimpan? Ini gak bisa dibatalin.")) return;

    mpaiClearBtn.disabled = true;
    try {
        const res = await fetch("/api/meal-plan-ai/clear", { method: "POST" });
        if (res.status === 401) {
            window.location.href = "/login";
            return;
        }
        // Reset chatbox ke cuma pesan sapaan awal
        mpaiMessages.innerHTML = '<div class="chat-msg bot">Halo! Ceritain bahan yang udah kamu punya di rumah (atau langsung klik "Buat Rencana Menu" kalau mau AI pilihin dari nol).</div>';

        // Sembunyiin & kosongin section rencana menu + daftar belanja
        const planSection = document.getElementById("ai-plan-section");
        const shoppingSection = document.getElementById("ai-shopping-section");
        document.getElementById("ai-plan-grid").innerHTML = "";
        document.getElementById("ai-shopping-body").innerHTML = "";
        const receiptBody = document.getElementById("receipt-body");
        if (receiptBody) receiptBody.innerHTML = "";
        if (shoppingReceiptOverlay) shoppingReceiptOverlay.classList.remove("open");
        planSection.style.display = "none";
        shoppingSection.style.display = "none";
    } catch (err) {
        alert("Gagal bersihin chat, coba lagi ya.");
    } finally {
        mpaiClearBtn.disabled = false;
    }
});