document.addEventListener("DOMContentLoaded", () => {
    fetchStreamData();
});

async function fetchStreamData() {
    try {
        const response = await fetch("/api/videos");
        const videos = await response.json();
        
        const grid = document.getElementById("video-grid");
        grid.innerHTML = ""; // Clear loader text

        if (videos.length === 0) {
            grid.innerHTML = "<p class='loading'>No videos have been uploaded to the database yet.</p>";
            return;
        }

        videos.forEach(video => {
            const card = document.createElement("div");
            card.className = "card";
            card.innerHTML = `
                <h3>${video.title}</h3>
                <iframe src="https://www.youtube.com/embed/${video.youtube_id}" allowfullscreen></iframe>
                <p style="font-size: 12px; color: #718096; margin-top: 8px;">Uploaded by: ${video.uploaded_by}</p>
            `;
            grid.appendChild(card);
        });
    } catch (error) {
        console.error("Error connecting to Python database API:", error);
    }
}
