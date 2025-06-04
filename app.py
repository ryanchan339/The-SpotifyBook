import os
import uuid
import json
import time
from collections import Counter
from flask import Flask, session, redirect, request, render_template
from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")

SESSION_STORE = "sessions.json"

# ---------- Session File Helpers ----------
def load_sessions():
    if not os.path.exists(SESSION_STORE):
        return {}
    with open(SESSION_STORE, "r") as f:
        return json.load(f)

def save_sessions(sessions):
    with open(SESSION_STORE, "w") as f:
        json.dump(sessions, f, indent=2)

# ---------- Per-Session Spotify OAuth ----------
def make_sp_oauth(session_id):
    return SpotifyOAuth(
        client_id=os.getenv("SPOTIPY_CLIENT_ID"),
        client_secret=os.getenv("SPOTIPY_CLIENT_SECRET"),
        redirect_uri=os.getenv("SPOTIPY_REDIRECT_URI"),
        scope="user-top-read playlist-modify-public playlist-modify-private",
        cache_path=f".cache-{session_id}"
    )

# ---------- Routes ----------
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/solo")
def solo():
    # Clear any previous group session
    session.clear()
    # Set a flag so we know it's solo mode
    session["solo_mode"] = True
    return redirect("/login")

@app.route("/new-session")
def new_session():
    session_id = str(uuid.uuid4())
    sessions = load_sessions()
    sessions[session_id] = []
    save_sessions(sessions)
    return redirect(f"/join/{session_id}")

@app.route("/join/<session_id>")
def join(session_id):
    session["session_id"] = session_id
    return redirect("/login")

@app.route("/login")
def login():
    sid = request.args.get("session_id")

    if sid:
        session["session_id"] = sid
    elif "session_id" not in session:
        sid = str(uuid.uuid4())
        session["session_id"] = sid
        sessions = load_sessions()
        sessions[sid] = []
        save_sessions(sessions)

    session_id = session["session_id"]
    sp_oauth = make_sp_oauth(session_id)  # ✅ create a new OAuth object per session
    auth_url = sp_oauth.get_authorize_url(state=session_id)
    return redirect(auth_url)


@app.route("/callback")
def callback():
    code = request.args.get("code")
    state = request.args.get("state")

    session_id = session.get("session_id") or state
    session["session_id"] = session_id

    sp_oauth = make_sp_oauth(session_id)
    token_info = sp_oauth.get_access_token(code)
    session["token_info"] = token_info

    sp = Spotify(auth=token_info["access_token"])
    profile = sp.current_user()
    top_tracks = sp.current_user_top_tracks(limit=20, time_range="medium_term")["items"]
    track_uris = [track["uri"] for track in top_tracks]

    # ✅ If solo mode: store in session and redirect to top-tracks display
    if session.get("solo_mode"):
        session["track_uris"] = track_uris
        session["track_names"] = [
            f"{t['name']} by {t['artists'][0]['name']}" for t in top_tracks
        ]
        return redirect("/top-tracks")

    # Group session logic (unchanged)
    sessions = load_sessions()
    if session_id in sessions:
        sessions[session_id].append({
            "user": profile["display_name"],
            "tracks": track_uris
        })
        save_sessions(sessions)

    return redirect(f"/summary/{session_id}")


@app.route("/summary/<session_id>")
def summary(session_id):
    sessions = load_sessions()
    group = sessions.get(session_id, [])
    return render_template("summary.html", users=group, session_id=session_id)

@app.route("/merge/<session_id>", methods=["POST"])
def merge(session_id):
    token_info = session.get("token_info")
    if not token_info:
        return redirect("/login")

    session_id = session.get("session_id")
    sp_oauth = make_sp_oauth(session_id)

    # Refresh token if needed
    if token_info["expires_at"] < int(time.time()):
        token_info = sp_oauth.refresh_access_token(token_info["refresh_token"])
        session["token_info"] = token_info

    try:
        sp = Spotify(auth=token_info["access_token"])
        user_id = sp.current_user()["id"]

        sessions = load_sessions()
        group = sessions.get(session_id, [])

        if len(group) < 2:
            return "❌ Need at least two users to merge."

        all_tracks = [track for user in group for track in user["tracks"]]
        track_counts = Counter(all_tracks)
        merged_uris = [track for track, _ in track_counts.most_common(30)]

        playlist = sp.user_playlist_create(
            user=user_id,
            name=f"Merged Playlist ({len(group)} users)",
            public=True
        )
        sp.playlist_add_items(playlist["id"], merged_uris)

        playlist_url = playlist["external_urls"]["spotify"]
        return render_template("playlist_created.html", playlist_url=playlist_url)

    except Exception as e:
        return f"❌ Unexpected error: {str(e)}"

@app.route("/choose-range")
def choose_range():
    return render_template("choose_range.html")

@app.route("/top-tracks", methods=["POST"])
def top_tracks():
    token_info = session.get("token_info")
    if not token_info:
        return redirect("/login")

    time_range = request.form.get("time_range", "medium_term")
    session["time_range"] = time_range

    session_id = session["session_id"]
    sp_oauth = make_sp_oauth(session_id)

    if token_info["expires_at"] < int(time.time()):
        token_info = sp_oauth.refresh_access_token(token_info["refresh_token"])
        session["token_info"] = token_info

    sp = Spotify(auth=token_info["access_token"])
    tracks = sp.current_user_top_tracks(limit=10, time_range=time_range)["items"]

    session["track_uris"] = [track["uri"] for track in tracks]
    session["track_names"] = [
        f"{track['name']} by {track['artists'][0]['name']}" for track in tracks
    ]

    return render_template("top_tracks.html",
                           track_names=session["track_names"],
                           time_range=time_range)

@app.route("/create-playlist", methods=["GET", "POST"])
def create_playlist():
    if request.method == "GET":
        return "GET method received ✅"
    token_info = session.get("token_info")
    if not token_info:
        return redirect("/login")

    session_id = session.get("session_id", "solo")
    sp_oauth = make_sp_oauth(session_id)

    import time
    if token_info["expires_at"] < int(time.time()):
        token_info = sp_oauth.refresh_access_token(token_info["refresh_token"])
        session["token_info"] = token_info

    sp = Spotify(auth=token_info["access_token"])
    user_id = sp.current_user()["id"]
    track_uris = session.get("track_uris", [])

    playlist_name = request.form.get("playlist_name", "My Top Tracks")

    if not track_uris:
        return "❌ No tracks to add. Go back and fetch top tracks first."

    playlist = sp.user_playlist_create(
        user=user_id,
        name=playlist_name,
        public=True,
        description="Created with SpotifyBook"
    )
    sp.playlist_add_items(playlist_id=playlist["id"], items=track_uris)

    playlist_url = playlist["external_urls"]["spotify"]
    return render_template("playlist_created.html", playlist_url=playlist_url)


if __name__ == "__main__":
    app.run(debug=True)
