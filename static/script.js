let currentTab = 'videos-tab';
let allVideos = [];
let siteSettings = {};

document.addEventListener("DOMContentLoaded", async () => {
    // 1. Set the role based styling theme class
    const body = document.getElementById("app-body");
    body.className = `theme-${userRole}`;

    // 2. Adjust greeting header
    const greeting = document.getElementById("user-greeting");
    const authBtn = document.getElementById("auth-btn");
    
    if (userRole !== "guest") {
        greeting.innerHTML = `Welcome, <strong>${userName}</strong> (${userRole.toUpperCase()})`;
        authBtn.innerText = "Lock Portal";
        authBtn.href = "/logout";
        
        // Show role-specific UI options
        if (userRole === "vip" || userRole === "staff" || userRole === "president" || userRole === "admin") {
            document.getElementById("vip-tab-btn").style.display = "inline-block";
        }
        if (userRole === "staff" || userRole === "president" || userRole === "admin") {
            document.getElementById("chat-tab-btn").style.display = "inline-block";
        }
        if (userRole === "admin") {
            document.getElementById("admin-tab-btn").style.display = "inline-block";
        }
    }

    // 3. Fetch Global Settings from DB (includes Itinerary & Banners)
    await loadSiteSettings();

    // 4. Check for itinerary updates -> Handles the forced 10-second lock
    checkItineraryChanged();

    // 5. Fetch stream video files
    fetchVideos();

    // 6. Handle targeted alerts
    checkPopups();

    // Setup active listeners
    setupForms();
});

// --- SETTINGS & ITINERARY CHANGED ENGINE ---
async function loadSiteSettings() {
    try {
        const response = await fetch("/api/settings");
        siteSettings = await response.json();
        
        // Render Active Dynamic Banner Alert
        const banner = document.getElementById("alert-banner");
        if (siteSettings.banner_active) {
            banner.style.backgroundColor = siteSettings.banner_color;
            document.getElementById("banner-content").innerText = siteSettings.banner_text;
            banner.style.display = "block";
        }

        // Set PDF frame source
        document.getElementById("itinerary-frame").src = siteSettings.itinerary_pdf_url;

        // Auto-fill form values in the Admin panel if they are current admin
        if (userRole === "admin") {
            document.getElementById("m-toggle").checked = siteSettings.maintenance_active;
            document.getElementById("m-msg").value = siteSettings.maintenance_message;
            document.getElementById("m-timer").value = siteSettings.maintenance_timer;
            document.getElementById("b-toggle").checked = siteSettings.banner_active;
            document.getElementById("b-text").value = siteSettings.banner_text;
            document.getElementById("b-color").value = siteSettings.banner_color;
            document.getElementById("itinerary-url-input").value = siteSettings.itinerary_pdf_url;
            
            // Trigger load routines for Admin lists
            loadAdminUsers();
            loadAdminSubmissions();
        }
    } catch (e) {
        console.error("Error setting portal configurations:", e);
    }
}

// Check if itinerary is changed -> runs the forced 10s countdown if a newer PDF timestamp is present!
function checkItineraryChanged() {
    const lastViewed = localStorage.getItem("last_viewed_itinerary");
    const serverUpdated = siteSettings.itinerary_last_updated;

    if (!serverUpdated) return;

    // If local viewed date is empty, or older than the server update timestamp
    if (!lastViewed || new Date(lastViewed) < new Date(serverUpdated)) {
        // Switch to the itinerary tab first
        switchTab('itinerary-tab');
        
        // Open the unescapable modal lock overlay
        const lockModal = document.getElementById("itinerary-lock-modal");
        lockModal.style.display = "flex";

        let countdown = 10;
        const countDisplay = document.getElementById("lock-countdown");
        const dismissBtn = document.getElementById("lock-dismiss-btn");

        const interval = setInterval(() => {
            countdown--;
            countDisplay.innerText = `${countdown} seconds remaining`;
            if (countdown <= 0) {
                clearInterval(interval);
                countDisplay.innerText = "Itinerary fully reviewed!";
                dismissBtn.removeAttribute("disabled");
                dismissBtn.innerText = "Dismiss & Continue";
            }
        }, 1000);
    }
}

function dismissItineraryLock() {
    // Record current review in user's browser storage
    localStorage.setItem("last_viewed_itinerary", new Date().toISOString());
    document.getElementById("itinerary-lock-modal").style.display = "none";
}

// --- TAB ROUTING ---
function switchTab(tabId) {
    // Block switching if the itinerary lock modal is active
    if (document.getElementById("itinerary-lock-modal").style.display === "flex") {
        return;
    }

    currentTab = tabId;
    document.querySelectorAll(".tab-content").forEach(el => el.classList.remove("active"));
    document.querySelectorAll(".tab-btn").forEach(el => el.classList.remove("active"));
    
    document.getElementById(tabId).classList.add("active");
    
    // Find matching button to set active
    const activeBtn = Array.from(document.querySelectorAll(".tab-btn")).find(btn => 
        btn.getAttribute("onclick").includes(tabId)
    );
    if (activeBtn) activeBtn.classList.add("active");

    // Contextual actions
    if (tabId === 'chat-tab') {
        loadChats();
        loadStaffSubmissions();
    }
}

// --- VIDEO DATABASE SEARCH & RENDERING ---
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

    const filtered = allVideos.filter(video => {
        const query = document.getElementById("video-search").value.toLowerCase();
        return video.title.toLowerCase().includes(query) || video.uploaded_by.toLowerCase().includes(query);
    });

    let publicCount = 0;
    let vipCount = 0;

    filtered.forEach(video => {
        const card = document.createElement("div");
        card.className = "card video-card";
        card.innerHTML = `
            <h3>${video.title}</h3>
            <iframe src="https://www.youtube.com/embed/${video.youtube_id}" allowfullscreen></iframe>
            <p class="meta">Captured by: ${video.uploaded_by}</p>
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
    if (vipCount === 0) vipGrid.innerHTML = "<p class='status-msg'>No VIP bonus files posted yet.</p>";
}

function filterVideos() {
    renderVideos();
}

// --- COMMENT THREADS ---
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
        listDiv.innerHTML = "Error loading chat timeline.";
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
        alert("Must log in first to send comments!");
    }
}

// --- MESSENGER & CHAT SYSTEM (STAFF / PRES / ADMIN) ---
async function loadChats() {
    const channel = document.getElementById("chat-channel").value;
    const chatBox = document.getElementById("chat-messages");
    
    try {
        const response = await fetch("/api/chat");
        const messages = await response.json();
        chatBox.innerHTML = "";

        // Filter based on selected channel
        const filtered = messages.filter(m => {
            if (channel === 'global_staff') {
                return m.receiver === 'global_staff';
            } else {
                // Direct message channel to admin
                return (m.receiver === 'admin' || m.sender === 'admin') && m.receiver !== 'global_staff';
            }
        });

        if (filtered.length === 0) {
            chatBox.innerHTML = "<p class='meta'>Empty channel history...</p>";
            return;
        }

        filtered.forEach(m => {
            const div = document.createElement("div");
            // If flagged as a presidential decree, highlight the box in red!
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
        chatBox.innerHTML = "Error rendering chat channels.";
    }
}

// --- POPUP SYSTEM ---
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
    
    // Check for any consecutive alerts
    checkPopups();
}

// --- STAFF DRIVE SUBMISSIONS ---
async function loadStaffSubmissions() {
    const list = document.getElementById("my-submissions-list");
    try {
        const res = await fetch("/api/submissions");
        const data = await res.json();
        list.innerHTML = "";
        
        if (data.length === 0) {
            list.innerHTML = "No drafts uploaded yet.";
            return;
        }

        data.forEach(sub => {
            const div = document.createElement("div");
            div.className = "comment-item";
            div.innerHTML = `
                <strong>${sub.title}</strong><br>
                <a href="${sub.drive_url}" target="_blank">View Folder File</a><br>
                Status: <span style="font-weight: bold; text-transform: uppercase;">${sub.status}</span>
            `;
            list.appendChild(div);
        });
    } catch (e) {
        list.innerHTML = "Failed to load submitted list.";
    }
}

// --- FORM SUBMISSION LISTENER SETUPS ---
function setupForms() {
    // Handle Chat Submissions
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
        }
    });

    // Handle Staff Google Drive Form
    const driveForm = document.getElementById("drive-upload-form");
    if (driveForm) {
        driveForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const title = document.getElementById("drive-video-title").value;
            const driveUrl = document.getElementById("drive-video-url").value;

            const res = await fetch("/api/submissions", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ title, driveUrl })
            });

            if (res.ok) {
                driveForm.reset();
                loadStaffSubmissions();
            }
        });
    }

    // Handle Admin Global Settings Save
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

            if (res.ok) {
                alert("Site configuration options saved globally!");
                window.location.reload();
            }
        });
    }

    // Handle Admin User Creation
    const adminUserForm = document.getElementById("admin-create-user-form");
    if (adminUserForm) {
        adminUserForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const username = document.getElementById("new-user-name").value;
            const password = document.getElementById("new-user-pass").value;
            const role = document.getElementById("new-user-role").value;

            const res = await fetch("/api/admin/users", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ username, password, role })
            });

            if (res.ok) {
                adminUserForm.reset();
                loadAdminUsers();
            } else {
                alert("Error: Username must be unique.");
            }
        });
    }

    // Handle Admin Target Popup Alerts
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

            if (res.ok) {
                adminPopupForm.reset();
                alert("Targeted alert pushed successfully!");
            }
        });
    }
}

// --- ADMIN CONTROL: LOADER CALLS ---

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
                <td><strong>${u.username}</strong></td>
                <td>
                    <span class="pass-text" id="pass-field-${u.id}" onclick="revealPassword('${u.id}', '${u.password}')">•••••••• (Reveal)</span>
                </td>
                <td>
                    <select onchange="updateUserRole(${u.id}, this.value, ${u.is_locked}, '${u.username}', '${u.password}')">
                        <option value="vip" ${u.role === 'vip' ? 'selected' : ''}>VIP</option>
                        <option value="staff" ${u.role === 'staff' ? 'selected' : ''}>Staff</option>
                        <option value="president" ${u.role === 'president' ? 'selected' : ''}>President</option>
                        <option value="admin" ${u.role === 'admin' ? 'selected' : ''}>Admin</option>
                    </select>
                </td>
                <td>
                    <input type="checkbox" ${u.is_locked ? 'checked' : ''} onchange="toggleUserLock(${u.id}, this.checked, '${u.role}', '${u.username}', '${u.password}')">
                </td>
                <td>
                    <button class="nav-btn" style="background-color: var(--accent-red); padding: 4px 10px; font-size: 11px;" onclick="deleteUser(${u.id})">Delete</button>
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

async function updateUserRole(userId, newRole, isLocked, username, password) {
    await fetch(`/api/admin/users/${userId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role: newRole, is_locked: isLocked, username, password })
    });
    loadAdminUsers();
}

async function toggleUserLock(userId, isLocked, role, username, password) {
    await fetch(`/api/admin/users/${userId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role, is_locked: isLocked, username, password })
    });
    loadAdminUsers();
}

async function deleteUser(userId) {
    if (confirm("Are you sure you want to permanently delete this user account?")) {
        await fetch(`/api/admin/users/${userId}`, { method: "DELETE" });
        loadAdminUsers();
    }
}

async function loadAdminSubmissions() {
    const panel = document.getElementById("admin-queue-list");
    try {
        const res = await fetch("/api/submissions");
        const data = await res.json();
        panel.innerHTML = "";

        const pending = data.filter(sub => sub.status === "pending");

        if (pending.length === 0) {
            panel.innerHTML = "<p class='meta'>No staff video submissions pending review.</p>";
            return;
        }

        pending.forEach(sub => {
            const div = document.createElement("div");
            div.className = "card";
            div.style.background = "#0f172a";
            div.innerHTML = `
                <p><strong>Uploader:</strong> ${sub.submitted_by}</p>
                <p><strong>Proposed Title:</strong> ${sub.title}</p>
                <p><a href="${sub.drive_url}" target="_blank" style="color: var(--accent);">📁 View Drive Video</a></p>
                
                <hr style="border-color: var(--border);">
                
                <form onsubmit="publishSubmission(event, ${sub.id}, '${sub.drive_url}')" style="display: flex; flex-direction: column; gap: 8px;">
                    <input type="text" placeholder="Official Video Title" id="pub-title-${sub.id}" value="${sub.title}" required style="padding: 6px; background: #1e293b; border: 1px solid var(--border); color: white;">
                    <input type="text" placeholder="Youtube Video URL" id="pub-yt-url-${sub.id}" required style="padding: 6px; background: #1e293b; border: 1px solid var(--border); color: white;">
                    <label><input type="checkbox" id="pub-vip-${sub.id}"> VIP Only Video</label>
                    <div style="display: flex; gap: 10px; margin-top: 5px;">
                        <button type="submit" style="background: #10b981; color: white; border: none; padding: 6px 12px; border-radius: 4px; cursor: pointer;">Publish to Feed</button>
                        <button type="button" onclick="rejectSubmission(${sub.id})" style="background: var(--accent-red); color: white; border: none; padding: 6px 12px; border-radius: 4px; cursor: pointer;">Reject</button>
                    </div>
                </form>
            `;
            panel.appendChild(div);
        });
    } catch (e) {
        panel.innerHTML = "Error rendering staff upload queue.";
    }
}

async function publishSubmission(event, subId, driveUrl) {
    event.preventDefault();
    const title = document.getElementById(`pub-title-${subId}`).value;
    const ytUrl = document.getElementById(`pub-yt-url-${subId}`).value;
    const isVip = document.getElementById(`pub-vip-${subId}`).checked;

    const res = await fetch("/api/admin/publish-video", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title, youtubeUrl: ytUrl, isVip, submissionId: subId })
    });

    if (res.ok) {
        alert("Video successfully translated and published to feed!");
        loadAdminSubmissions();
        fetchVideos();
    }
}

async function rejectSubmission(subId) {
    if (confirm("Reject this submission draft?")) {
        await fetch(`/api/admin/submissions/reject/${subId}`, { method: "POST" });
        loadAdminSubmissions();
    }
}

function closeBanner() {
    document.getElementById("alert-banner").style.display = "none";
}
