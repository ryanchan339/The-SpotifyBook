🎵 The SpotifyBook

The SpotifyBook is a solo-mode Flask web application that uses Spotify's OAuth to let users view and interact with their personal music data. You can view your top tracks and top artists over various time ranges and even create a playlist directly from your top songs.

🔧 Features
✅ Spotify OAuth Login

🎶 Top Tracks Viewer (Short, Medium, Long Term)

👨‍🎤 Top Artists Viewer

📀 Create Playlists from your top tracks

🔁 Dynamic updates via API (AJAX)

🧪 Solo session mode using unique session IDs

💡 Simple and clean Flask backend

🚀 Live Demo

📁 Project Structure
cpp
Copy
Edit
├── templates/
│   ├── index.html
│   ├── top_tracks.html
│   ├── top_artists.html
│   ├── playlist_created.html
│   └── new_page.html
├── static/
│   └── (your CSS/JS files if any)
├── app.py
├── .env
└── README.md

🧠 Tech Stack
Python

Flask

Spotipy (Spotify Web API wrapper)

HTML/CSS + JavaScript

dotenv

📌 Notes
This app is built for solo use — no user accounts are stored.

Time range buttons work without full page reloads via /api/top-tracks.

Track/Artist switching happens via full route change (/top-tracks, /top-artists).
