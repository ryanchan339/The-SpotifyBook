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

🛠️ Setup Instructions
1. Clone the Repo
bash
Copy
Edit
git clone https://github.com/yourusername/The-SpotifyBook.git
cd The-SpotifyBook
2. Create a .env file
Inside the root directory, create a .env file with the following:

env
Copy
Edit
SPOTIPY_CLIENT_ID=your_spotify_client_id
SPOTIPY_CLIENT_SECRET=your_spotify_client_secret
SPOTIPY_REDIRECT_URI=http://localhost:5000/callback
FLASK_SECRET_KEY=your_random_secret_key
You can get these credentials from: https://developer.spotify.com/dashboard

3. Install Dependencies
bash
Copy
Edit
pip install -r requirements.txt
4. Run the Flask App
bash
Copy
Edit
python app.py
Then open http://localhost:5000 in your browser.

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
