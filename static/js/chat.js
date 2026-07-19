const chatFab = document.getElementById("chat-fab");
const chatPanel = document.getElementById("chat-panel");
const chatMessages = document.getElementById("chat-messages");
const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");

function toggleChat(forceOpen) {
    const shouldOpen = forceOpen !== undefined ? forceOpen : !chatPanel.classList.contains("open");
    chatPanel.classList.toggle("open", shouldOpen);
    // Hentiin ping animasi di tombol FAB begitu user udah pernah buka chat
    // sekali — biar nggak terus mancing perhatian padahal udah dipakai.
    chatFab.classList.add("open");
}

chatFab.addEventListener("click", () => toggleChat());
document.getElementById("chat-close").addEventListener("click", () => toggleChat(false));

// ---------- Lokasi user (buat link Google Maps 'toko terdekat' yang akurat) ----------
// Diminta sekali pas chat pertama kali dikirim, BUKAN otomatis pas halaman load —
// browser modern nge-block permintaan geolocation yang nggak dipicu interaksi user.
let userLocation = null; // {lat, lng} atau null kalau ditolak/gagal/belum diminta
let locationRequested = false;

function requestLocationOnce() {
    if (locationRequested || !navigator.geolocation) return Promise.resolve(userLocation);
    locationRequested = true;
    return new Promise((resolve) => {
        navigator.geolocation.getCurrentPosition(
            (pos) => {
                userLocation = { lat: pos.coords.latitude, lng: pos.coords.longitude };
                resolve(userLocation);
            },
            () => {
                // ditolak / gagal -> userLocation tetap null, backend fallback ke
                // pencarian generik yang di-scope ke Yogyakarta (lihat services/shopping_links.py)
                resolve(null);
            },
            { timeout: 8000 }
        );
    });
}

// ---------- Render pesan (link di balasan bot dibikin bisa diklik) ----------
function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

function linkify(escapedText) {
    // escapedText SUDAH lolos escapeHtml() duluan, jadi aman disisipin <a> di sini.
    const urlPattern = /(https?:\/\/[^\s]+)/g;
    return escapedText.replace(urlPattern, (url) => {
        const cls = classifyLink(url);
        return `<a href="${url}" target="_blank" rel="noopener noreferrer" class="${cls}">${url}</a>`;
    });
}

// Video tutorial (YouTube), toko fisik terdekat (Google Maps), dan marketplace
// (Tokopedia/dst) dibedain warnanya biar user langsung ngerti jenis link-nya
// tanpa harus baca URL-nya dulu. Sama persis dengan meal-planner-ai.js biar
// konsisten di seluruh aplikasi.
function classifyLink(url) {
    if (/youtube\.com|youtu\.be/i.test(url)) return "link-video";
    if (/google\.[a-z.]+\/maps/i.test(url)) return "link-maps";
    return "link-marketplace";
}

function appendMessage(text, sender, isLoading = false) {
    const bubble = document.createElement("div");
    bubble.className = `chat-msg ${sender}${isLoading ? " loading" : ""}`;
    if (sender === "bot") {
        bubble.innerHTML = linkify(escapeHtml(text));
    } else {
        bubble.textContent = text; // pesan user nggak perlu linkify
    }
    chatMessages.appendChild(bubble);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    return bubble;
}

function appendFeedbackButtons(chatHistoryId) {
    if (!chatHistoryId) return;
    const wrap = document.createElement("div");
    wrap.className = "chat-feedback";

    const up = document.createElement("button");
    up.innerHTML = icon("thumbs-up", 15);
    up.title = "Membantu";
    const down = document.createElement("button");
    down.innerHTML = icon("thumbs-down", 15);
    down.title = "Kurang membantu";

    async function sendFeedback(rating, clickedBtn) {
        try {
            await fetch("/api/chat/feedback", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ chat_history_id: chatHistoryId, rating }),
            });
            wrap.querySelectorAll("button").forEach((b) => (b.disabled = true));
            clickedBtn.classList.add("chosen");
        } catch (err) {
            // gagal kirim feedback, biarin tombol tetap aktif
        }
    }

    up.addEventListener("click", () => sendFeedback(5, up));
    down.addEventListener("click", () => sendFeedback(1, down));

    wrap.appendChild(up);
    wrap.appendChild(down);
    chatMessages.appendChild(wrap);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

async function loadHistory() {
    if (!window.IS_LOGGED_IN) return;
    try {
        const res = await fetch("/api/chat/history?limit=10");
        const data = await res.json();
        if (data.history && data.history.length > 0) {
            chatMessages.innerHTML = "";
            data.history.forEach((item) => {
                appendMessage(item.message, "user");
                appendMessage(item.reply, "bot");
            });
        }
    } catch (err) {
        // biarin greeting default kalau gagal load riwayat
    }
}
loadHistory();

async function sendMessage(message) {
    if (!message.trim()) return;

    if (!window.IS_LOGGED_IN) {
        appendMessage(message, "user");
        appendMessage("Kamu perlu login dulu buat pakai fitur chat AI ini.", "bot");
        setTimeout(() => {
            window.location.href = `${window.LOGIN_URL}?next=${encodeURIComponent(window.location.pathname)}`;
        }, 1200);
        return;
    }

    await requestLocationOnce();

    appendMessage(message, "user");
    const loadingBubble = appendMessage("Menganalisis bahan & mencari resep...", "bot", true);

    try {
        const res = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                message,
                lat: userLocation ? userLocation.lat : null,
                lng: userLocation ? userLocation.lng : null,
            }),
        });
        const data = await res.json();
        loadingBubble.remove();

        if (res.status === 401) {
            appendMessage("Sesi login kamu habis, silakan login lagi.", "bot");
            setTimeout(() => { window.location.href = window.LOGIN_URL; }, 1200);
            return;
        }

        appendMessage(data.reply || "Maaf, terjadi kendala.", "bot");
        appendFeedbackButtons(data.chat_history_id);
    } catch (err) {
        loadingBubble.remove();
        appendMessage("Maaf, gagal terhubung ke server. Coba lagi ya.", "bot");
    }
}

chatForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const message = chatInput.value;
    chatInput.value = "";
    sendMessage(message);
});

// Hook hero demo box: mengirim langsung ke chat & buka panel
const heroDemoForm = document.getElementById("hero-demo-form");
if (heroDemoForm) {
    heroDemoForm.addEventListener("submit", (e) => {
        e.preventDefault();
        const input = document.getElementById("hero-demo-input");
        const message = input.value;
        input.value = "";
        toggleChat(true);
        sendMessage(message);
    });
}