let currentTab = 'videos-tab';
let allVideos = [];
let siteSettings = {};

document.addEventListener("DOMContentLoaded", async () => {
    // 1. Role-based theme
    const body = document.getElementById("app-body");
    body.className = `theme-${userRole}`;

    // 2. Personal favorite-color override (on top of the role theme)
    if (typeof userColor === "string" && /^#[0-9a-fA-F]{6}$/.test(userColor)) {
        document.documentElement.style.setProperty("--accent", userColor);
        document.documentElement.style.setProperty("--accent-ink", getContrastColor(userColor));
        document.documentElement.style.setProperty("--accent-soft", userColor + "29");
        document.documentElement.style.setProperty("--accent-line", userColor + "66");
    }

    // 3. Greeting + auth button
    const greeting = document.getElementById("user-greeting");
    const authBtn = document.getElementById("auth-btn");

    if (userRole !== "guest") {
        const niceName = (typeof userDisplayName === "string" && userDisplayName) ? userDisplayName : userName;
        greeting.innerHTML = `Welcome, <strong>${niceName}</strong> (${userRole.toUpperCase()})`;
        authBtn.innerText = "Lock Portal";
        authBtn.href = "/logout";

        if (userRole === "vip" || userRole === "staff" || userRole === "president" || userRole === "admin") {
            document.getElementById("vip-tab-btn").style.display = "inline-block";
        }
        if (userRole === "staff" || userRole === "president" || userRole === "admin") {
            document.getElementById("chat-tab-btn").style.display = "inline-block";
        }
        if (userRole === "admin") {
            document.getElementById("admin-tab-btn").style.display = "inline-block";
        }

        // Admin doesn't upload videos to himself — that card is staff/president only
        const driveSection = document.getElementById("staff-drive-section");
        if (driveSection) {
            driveSection.style.display = (userRole === "staff" || userRole === "president") ? "block" : "none";
        }

        // Video request area is VIP-only
        const requestSection = document.getElementById("vip-request-section");
        if (requestSection) {
            requestSection.style.display = (userRole === "vip") ? "block" : "none";
        }
    }

    await loadSiteSettings();
    checkItineraryChanged();
    fetchVideos();
    checkPopups();
    setupForms();

    if (userRole === "vip") loadMyVideoRequests();
    if (userRole === "staff" || userRole === "president" || userRole === "admin") populateChatChannels();
});

function getContrastColor(hex) {
    hex = hex.replace("#", "");
    const r = parseInt(hex.substr(0, 2), 16);
    const g = parseInt(hex.substr(2, 2), 16);
    const b = parseInt(hex.substr(4, 2), 16);
    const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
    return luminance > 0.6 ? "#12201a" : "#ffffff";
}

// --- SETTINGS / BANNER-POPUP / ITINERARY ---
async function loadSiteSettings() {
    try {
        const response = await fetch("/api/settings");
        siteSettings = await response.json();

        if (siteSettings.banner_active) {
            // Show as a popup first — dismissing it reveals the persistent top banner
            const popup = document.getElementById("banner-popup-modal");
            const popupText = document.getElementById("banner-popup-text");
            popupText.innerText = siteSettings.banner_text;
            popup.querySelector(".popup-box").style.borderColor = siteSettings.banner_color;
            popup.style.display = "flex";
        }

        document.getElementById("itinerary-frame").src = siteSettings.itinerary_pdf_url || "about:blank";

        if (userRole === "admin") {
            document.getElementById("m-toggle").checked = siteSettings.maintenance_active;
            document.getElementById("m-msg").value = siteSettings.maintenance_message || "";
            document.getElementById("m-timer").value = siteSettings.maintenance_timer || "";
            document.getElementById("b-toggle").checked = siteSettings.banner_active;
            document.getElementById("b-text").value = siteSettings.banner_text || "";
            document.getElementById("b-color").value = siteSettings.banner_color || "#4f46e5";
            document.getElementById("itinerary-url-input").value = siteSettings.itinerary_pdf_url || "";

            loadAdminUsers();
            populatePopupTargets();
            loadVideoRequestQueue();
        }
    } catch (e) {
        console.error("Error setting portal configurations:", e);
    }
}

function dismissBannerPopup() {
    document.getElementById("banner-popup-modal").style.display = "none";
    if (siteSettings.banner_active) {
        const banner = document.getElementById("alert-banner");
        banner.style.backgroundColor = siteSettings.banner_color;
        document.getElementById("banner-content").innerText = siteSettings.banner_text;
        banner.style.display = "block";
    }
}

function closeBanner() {
    document.getElementById("alert-banner").style.display = "none";
}

// Non-blocking itinerary review: switches to the tab and briefly holds
// navigation so the PDF is actually visible (never covers it with an overlay).
function checkItineraryChanged() {
    const lastViewed = localStorage.getItem("last_viewed_itinerary");
    const serverUpdated = siteSettings.itinerary_last_updated;

    if (!serverUpdated) return;
    if (lastViewed && new Date(lastViewed) >= new Date(serverUpdated)) return;

    switchTab('itinerary-tab', true);

    const lockBar = document.getElementById("itinerary-lock-bar");
    const countdownEl = document.getElementById("itinerary-lock-countdown");
    lockBar.style.display = "flex";

    document.querySelectorAll(".tab-btn").forEach(btn => btn.classList.add("nav-locked"));
    document.getElementById("video-search").setAttribute("disabled", "disabled");

    let countdown = 10;
    const interval = setInterval(() => {
        countdown--;
        countdownEl.innerText = countdown;
        if (countdown <= 0) {
            clearInterval(interval);
            lockBar.style.display = "none";
            document.querySelectorAll(".tab-btn").forEach(btn => btn.classList.remove("nav-locked"));
            document.getElementById("video-search").removeAttribute("disabled");
            localStorage.setItem("last_viewed_itinerary", new Date().toISOString());
        }
    }, 1000);
}

// --- TAB ROUTING ---
function switchTab(tabId, force) {
    if (!force && document.querySelector(".tab-btn.nav-locked")) return;

    currentTab = tabId;
    document.querySelectorAll(".tab-content").forEach(el => el.classList.remove("active"));
    document.querySelectorAll(".tab-btn").forEach(el => el.classList.remove("active"));

    document.getElementById(tabId).classList.add("active");

    const activeBtn = Array.from(document.querySelectorAll(".tab-btn")).find(btn =>
        btn.getAttribute("onclick") && btn.getAttribute("onclick").includes(tabId)
    );
    if (activeBtn) activeBtn.classList.add("active");

    if (tabId === 'chat-tab') {
        loadChats();
    }
}

// --- VIDEOS ---
async function fetchVideos() {
    try {
        const response = await fetch("/api/videos");
        allVideos = await response.json();
        renderVideos();
    } catch (e) {
        console.error("Error loading videos database:", e);
    }
}

function renderVideos() {
    const generalGrid = document.getElementById("general-video-grid");
    const vipGrid = document.getElementById("vip-video-grid");

    generalGrid.innerHTML = "";
    vipGrid.innerHTML = "";

    const query = document.getElementById("video-search").value.toLowerCase();
    const filtered = allVideos.filter(video => video.title.toLowerCase().includes(query));

    let publicCount = 0;
    let vipCount = 0;

    filtered.forEach(video => {
        const card = document.createElement("div");
        card.className = "card video-card";
        card.innerHTML = `
            <h3>${video.title}</h3>
            <iframe src="https://www.youtube.com/embed/${video.youtube_id}" allowfullscreen></iframe>
            <div class="comments-section">
                <h4>Comments</h4>
                <div class="comments-list" id="comments-list-${video.id}">Loading conversations...</div>
                <form class="comment-form" onsubmit="submitComment(event, ${video.id})">
                    <input type="text" placeholder="Add comment..." required class="comment-input" id="text-${video.id}">
                    <button type="submit">Post</button>
                </form>
            </div>
        `;

        if (video.is_vip_only) {
            vipGrid.appendChild(card);
            vipCount++;
        } else {
            generalGrid.appendChild(card);
            publicCount++;
        }

        loadComments(video.id);
    });

    if (publicCount === 0) generalGrid.innerHTML = "<p class='status-msg'>No public videos found matching that search.</p>";
    if (vipCount === 0) vipGrid.innerHTML = "<p class='status-msg'>No VIP bonus videos posted yet.</p>";
}

function filterVideos() {
    renderVideos();
}

// --- COMMENTS ---
async function loadComments(videoId) {
    const listDiv = document.getElementById(`comments-list-${videoId}`);
    try {
        const response = await fetch(`/api/comments/${videoId}`);
        const comments = await response.json();
        listDiv.innerHTML = "";

        if (comments.length === 0) {
            listDiv.innerHTML = "<p class='meta'>No comments yet.</p>";
            return;
        }

        comments.forEach(c => {
            const item = document.createElement("div");
            item.className = "comment-item";
            item.innerHTML = `<strong>${c.user_name} (${c.role})</strong>: ${c.text}`;
            listDiv.appendChild(item);
        });
    } catch (e) {
        listDiv.innerHTML = "Error loading comments.";
    }
}

async function submitComment(event, videoId) {
    event.preventDefault();
    const textInput = document.getElementById(`text-${videoId}`);

    const response = await fetch("/api/comments", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ videoId: videoId, text: textInput.value })
    });

    if (response.ok) {
        textInput.value = "";
        loadComments(videoId);
    } else {
        alert("Something went wrong posting that comment.");
    }
}

// --- VIP: REQUEST A VIDEO ---
async function submitVideoRequest(event) {
    event.preventDefault();
    const input = document.getElementById("video-request-text");
    const res = await fetch("/api/video-requests", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: input.value })
    });
    const data = await res.json();
    if (res.ok) {
        input.value = "";
        loadMyVideoRequests();
    } else {
        alert(data.error || "Could not send your request.");
    }
}

async function loadMyVideoRequests() {
    const list = document.getElementById("my-video-requests-list");
    if (!list) return;
    try {
        const res = await fetch("/api/video-requests");
        const data = await res.json();
        list.innerHTML = "";
        if (data.length === 0) {
            list.innerHTML = "No requests sent yet.";
            return;
        }
        data.forEach(r => {
            const div = document.createElement("div");
            div.className = "comment-item";
            div.innerHTML = `${r.request_text} <br><span class="meta">Status: ${r.status.toUpperCase()}</span>`;
            list.appendChild(div);
        });
    } catch (e) {
        list.innerHTML = "Could not load your requests.";
    }
}

async function loadVideoRequestQueue() {
    const panel = document.getElementById("admin-video-requests");
    if (!panel) return;
    try {
        const res = await fetch("/api/video-requests");
        const data = await res.json();
        panel.innerHTML = "";
        const pending = data.filter(r => r.status === "pending");
        if (pending.length === 0) {
            panel.innerHTML = "<p class='meta'>No pending video requests.</p>";
            return;
        }
        pending.forEach(r => {
            const div = document.createElement("div");
            div.className = "comment-item";
            div.innerHTML = `
                <strong>${r.requested_by}</strong>: ${r.request_text}
                <div style="margin-top:8px; display:flex; gap:8px;">
                    <button type="button" class="mini-btn" onclick="setRequestStatus(${r.id}, 'fulfilled')">Mark Fulfilled</button>
                    <button type="button" class="mini-btn danger" onclick="setRequestStatus(${r.id}, 'dismissed')">Dismiss</button>
                </div>
            `;
            panel.appendChild(div);
        });
    } catch (e) {
        panel.innerHTML = "Could not load video requests.";
    }
}

async function setRequestStatus(id, status) {
    await fetch(`/api/admin/video-requests/${id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status })
    });
    loadVideoRequestQueue();
}

// --- MESSENGER ---
async function populateChatChannels() {
    const select = document.getElementById("chat-channel");
    try {
        const res = await fetch("/api/directory");
        const people = await res.json();
        people.forEach(p => {
            const opt = document.createElement("option");
            opt.value = p.username;
            opt.innerText = `Direct Message: ${p.display_name || p.username} (${p.role})`;
            select.appendChild(opt);
        });
    } catch (e) {
        console.error("Could not load directory:", e);
    }
}

async function loadChats() {
    const channel = document.getElementById("chat-channel").value;
    const chatBox = document.getElementById("chat-messages");

    try {
        const response = await fetch("/api/chat");
        const messages = await response.json();
        chatBox.innerHTML = "";

        const filtered = messages.filter(m => {
            if (channel === 'global_staff') return m.receiver === 'global_staff';
            return (m.sender === channel || m.receiver === channel) && m.receiver !== 'global_staff';
        });

        if (filtered.length === 0) {
            chatBox.innerHTML = "<p class='meta'>Empty channel history...</p>";
            return;
        }

        filtered.forEach(m => {
            const div = document.createElement("div");
            div.className = `chat-msg ${m.is_flagged_red ? 'decree' : ''}`;
            div.innerHTML = `
                <strong style="color: var(--accent);">${m.sender}</strong>
                <span class="meta">${new Date(m.created_at).toLocaleTimeString()}</span>
                <p style="margin: 5px 0 0 0;">${m.message}</p>
            `;
            chatBox.appendChild(div);
        });
        chatBox.scrollTop = chatBox.scrollHeight;
    } catch (e) {
        chatBox.innerHTML = "Error rendering chat channel.";
    }
}

// --- TARGETED / SITE-WIDE POPUPS ---
async function checkPopups() {
    try {
        const response = await fetch("/api/popups");
        const popups = await response.json();
        if (popups.length > 0) {
            const alertModal = document.getElementById("custom-alert-modal");
            const modalContent = document.getElementById("popup-modal-content");
            modalContent.innerText = popups[0].message;
            alertModal.dataset.popupId = popups[0].id;
            alertModal.style.display = "flex";
        }
    } catch (e) {
        console.error("Popup check failed:", e);
    }
}

async function dismissCustomPopup() {
    const alertModal = document.getElementById("custom-alert-modal");
    const popupId = alertModal.dataset.popupId;

    await fetch(`/api/popups/read/${popupId}`, { method: "POST" });
    alertModal.style.display = "none";
    checkPopups();
}

// --- FORM SETUP ---
function setupForms() {
    document.getElementById("chat-send-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        const input = document.getElementById("chat-input");
        const receiver = document.getElementById("chat-channel").value;

        const res = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ receiver: receiver, message: input.value })
        });

        if (res.ok) {
            input.value = "";
            loadChats();
        } else {
            const data = await res.json();
            alert(data.error || "Message failed to send.");
        }
    });

    const requestForm = document.getElementById("video-request-form");
    if (requestForm) requestForm.addEventListener("submit", submitVideoRequest);

    const addVideoForm = document.getElementById("admin-add-video-form");
    if (addVideoForm) {
        addVideoForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const title = document.getElementById("new-video-title").value;
            const youtubeUrl = document.getElementById("new-video-url").value;
            const isVip = document.getElementById("new-video-vip").checked;

            const res = await fetch("/api/admin/videos", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ title, youtubeUrl, isVip })
            });
            const data = await res.json();
            if (res.ok) {
                addVideoForm.reset();
                fetchVideos();
                alert("Video added to the feed!");
            } else {
                alert(data.error || "Could not add that video.");
            }
        });
    }

    const adminSettingsForm = document.getElementById("admin-settings-form");
    if (adminSettingsForm) {
        adminSettingsForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const payload = {
                maintenance_active: document.getElementById("m-toggle").checked,
                maintenance_message: document.getElementById("m-msg").value,
                maintenance_timer: document.getElementById("m-timer").value,
                banner_active: document.getElementById("b-toggle").checked,
                banner_text: document.getElementById("b-text").value,
                banner_color: document.getElementById("b-color").value,
                itinerary_pdf_url: document.getElementById("itinerary-url-input").value
            };

            const res = await fetch("/api/admin/settings", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            if (res.ok) {
                alert("Site configuration saved!");
                window.location.reload();
            } else {
                alert("Error saving settings: " + (data.error || "unknown error"));
            }
        });
    }

    const adminUserForm = document.getElementById("admin-create-user-form");
    if (adminUserForm) {
        adminUserForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const payload = {
                username: document.getElementById("new-user-name").value,
                password: document.getElementById("new-user-pass").value,
                display_name: document.getElementById("new-user-display").value,
                favorite_color: document.getElementById("new-user-color").value,
                role: document.getElementById("new-user-role").value
            };

            const res = await fetch("/api/admin/users", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            if (res.ok) {
                adminUserForm.reset();
                loadAdminUsers();
                populatePopupTargets();
            } else {
                alert(data.error || "Error: username must be unique.");
            }
        });
    }

    const adminPopupForm = document.getElementById("admin-popup-form");
    if (adminPopupForm) {
        adminPopupForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const target = document.getElementById("popup-target").value;
            const message = document.getElementById("popup-text").value;

            const res = await fetch("/api/admin/popup", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ target, message })
            });
            const data = await res.json();
            if (res.ok) {
                adminPopupForm.reset();
                alert("Targeted alert pushed successfully!");
            } else {
                alert(data.error || "Could not push that alert.");
            }
        });
    }
}

// --- ADMIN: POPUP TARGET DROPDOWN (any individual account, incl. VIP) ---
async function populatePopupTargets() {
    const select = document.getElementById("popup-target");
    if (!select) return;
    const dynamicOptions = select.querySelectorAll("option[data-dynamic]");
    dynamicOptions.forEach(o => o.remove());

    try {
        const res = await fetch("/api/admin/users");
        const users = await res.json();
        users.forEach(u => {
            const opt = document.createElement("option");
            opt.value = u.username;
            opt.dataset.dynamic = "true";
            opt.innerText = `${u.display_name || u.username} (${u.role})`;
            select.appendChild(opt);
        });
    } catch (e) {
        console.error("Could not load user directory for popups:", e);
    }
}

// --- ADMIN: USER MANAGEMENT ---
async function loadAdminUsers() {
    const tbody = document.getElementById("admin-user-table-body");
    try {
        const res = await fetch("/api/admin/users");
        const users = await res.json();
        tbody.innerHTML = "";

        users.forEach(u => {
            const tr = document.createElement("tr");
            if (u.is_locked) tr.className = "locked-user";

            tr.innerHTML = `
                <td>
                    <strong>${u.display_name || u.username}</strong><br>
                    <span class="meta">@${u.username}</span>
                </td>
                <td>
                    <span class="pass-text" id="pass-field-${u.id}" onclick="revealPassword('${u.id}', '${u.password}')">•••••••• (Reveal)</span>
                </td>
                <td>
                    <select onchange="updateUserRole(${u.id}, this.value, ${u.is_locked}, '${u.username}', '${u.password}', '${u.display_name || u.username}', '${u.favorite_color || '#47a68c'}')">
                        <option value="vip" ${u.role === 'vip' ? 'selected' : ''}>VIP</option>
                        <option value="staff" ${u.role === 'staff' ? 'selected' : ''}>Staff</option>
                        <option value="president" ${u.role === 'president' ? 'selected' : ''}>President</option>
                        <option value="admin" ${u.role === 'admin' ? 'selected' : ''}>Admin</option>
                    </select>
                </td>
                <td>
                    <span class="color-dot" style="background:${u.favorite_color || '#47a68c'}"></span>
                </td>
                <td>
                    <input type="checkbox" ${u.is_locked ? 'checked' : ''} onchange="toggleUserLock(${u.id}, this.checked, '${u.role}', '${u.username}', '${u.password}', '${u.display_name || u.username}', '${u.favorite_color || '#47a68c'}')">
                </td>
                <td>
                    <button class="mini-btn danger" onclick="deleteUser(${u.id})">Delete</button>
                </td>
            `;
            tbody.appendChild(tr);
        });
    } catch (e) {
        tbody.innerHTML = "Error loading accounts data.";
    }
}

function revealPassword(userId, passwordText) {
    const el = document.getElementById(`pass-field-${userId}`);
    if (el.innerText.includes("Reveal")) {
        el.innerText = passwordText;
    } else {
        el.innerText = "•••••••• (Reveal)";
    }
}

async function updateUserRole(userId, newRole, isLocked, username, password, displayName, favoriteColor) {
    await fetch(`/api/admin/users/${userId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role: newRole, is_locked: isLocked, username, password, display_name: displayName, favorite_color: favoriteColor })
    });
    loadAdminUsers();
}

async function toggleUserLock(userId, isLocked, role, username, password, displayName, favoriteColor) {
    await fetch(`/api/admin/users/${userId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role, is_locked: isLocked, username, password, display_name: displayName, favorite_color: favoriteColor })
    });
    loadAdminUsers();
}

async function deleteUser(userId) {
    if (confirm("Are you sure you want to permanently delete this user account?")) {
        await fetch(`/api/admin/users/${userId}`, { method: "DELETE" });
        loadAdminUsers();
        populatePopupTargets();
    }
}
