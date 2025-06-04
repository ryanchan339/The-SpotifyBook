import uuid
import json
import os
from flask import Flask, session, redirect, request, render_template
from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")

sp_oauth = SpotifyOAuth(
    client_id=os.getenv("SPOTIPY_CLIENT_ID"),
    client_secret=os.getenv("SPOTIPY_CLIENT_SECRET"),
    redirect_uri=os.getenv("SPOTIPY_REDIRECT_URI"),
    scope="user-top-read playlist-modify-public playlist-modify-private",
    auth_args={"show_dialog": True}
)

SESSION_STORE = "sessions.json"

def load_sessions():
    if not os.path.exists(SESSION_STORE):
        return {}
    with open(SESSION_STORE, "r") as f:
        return json.load(f)

def save_sessions(sessions):
    with open(SESSION_STORE, "w") as f:
        json.dump(sessions, f)

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


def make_sp_oauth(cache_path):
    """
    Create a SpotifyOAuth object for a given cache_path.
    (We don't pass auth_args here, since this Spotipy version doesn't support it.)
    """
    return SpotifyOAuth(
        client_id=os.getenv("SPOTIPY_CLIENT_ID"),
        client_secret=os.getenv("SPOTIPY_CLIENT_SECRET"),
        redirect_uri=os.getenv("SPOTIPY_REDIRECT_URI"),
        scope="user-top-read playlist-modify-public playlist-modify-private",
        cache_path=cache_path
    )

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/login")
def login():
    # 1. If session_id was passed in the URL, use it:
    sid = request.args.get("session_id")
    if sid:
        session["session_id"] = sid

    # 2. If there’s still no session_id in the Flask cookie, create one now:
    elif "session_id" not in session:
        sid = str(uuid.uuid4())
        session["session_id"] = sid

        # Initialize an empty list for this session in sessions.json
        sessions = load_sessions()
        sessions[sid] = []
        save_sessions(sessions)

        # Redirect to the same route but with ?session_id=<new-id> in the URL
        return redirect(f"/login?session_id={sid}")

    # 3. At this point, session["session_id"] is guaranteed:
    session_id = session["session_id"]

    # 4. Build a SpotifyOAuth that uses a unique cache file per session
    cache_path = f".cache-{session_id}"
    sp_oauth = make_sp_oauth(cache_path)

    # 5. Generate the authorize URL, passing the session_id as 'state'
    auth_url = sp_oauth.get_authorize_url(state=session_id)

    # 6. Manually append '&show_dialog=true' so Spotify forces credential entry
    if "show_dialog=true" not in auth_url:
        auth_url += "&show_dialog=true"

    return redirect(auth_url)




@app.route("/callback")
def callback():
    # 1. Spotify will redirect back with ?code=...&state=<session_id>
    code = request.args.get("code")
    state_session_id = request.args.get("state")

    # 2. Use the same cache_path that we created in /login
    session_id = state_session_id or session.get("session_id")
    if not session_id:
        return "❌ Error: Missing session ID. Please start or join a session first."

    cache_path = f".cache-{session_id}"
    sp_oauth = make_sp_oauth(cache_path)

    # 3. Exchange the code for a token
    token_info = sp_oauth.get_access_token(code)
    session["token_info"] = token_info
    session["session_id"] = session_id  # re-save it just in case

    # 4. Now fetch the user profile & top tracks
    sp = Spotify(auth=token_info["access_token"])
    profile = sp.current_user()
    top_tracks = sp.current_user_top_tracks(limit=20, time_range="medium_term")["items"]
    track_uris = [t["uri"] for t in top_tracks]

    # 5. Add this user’s data under sessions.json[session_id]
    all_sessions = load_sessions()
    if session_id in all_sessions:
        all_sessions[session_id].append({
            "user": profile["display_name"],
            "tracks": track_uris
        })
        save_sessions(all_sessions)

    # 6. Redirect to the summary page for that session
    return redirect(f"/summary/{session_id}")




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

    sp = Spotify(auth=token_info["access_token"])
    tracks = sp.current_user_top_tracks(limit=10, time_range=time_range)["items"]

    # Save tracks in session so we can use them later
    session["track_uris"] = [track["uri"] for track in tracks]
    session["track_names"] = [f"{track['name']} by {track['artists'][0]['name']}" for track in tracks]

    return render_template("top_tracks.html", track_names=session["track_names"], time_range=time_range)


@app.route("/create-playlist", methods=["POST"])
def create_playlist():
    token_info = session.get("token_info")
    if not token_info:
        return redirect("/login")

    sp = Spotify(auth=token_info["access_token"])
    user_id = sp.current_user()["id"]
    track_uris = session.get("track_uris", [])

    # ✅ Get playlist name from form
    playlist_name = request.form.get("playlist_name", "My Top Tracks")

    if not track_uris:
        return "No tracks found in session. Go back and fetch top tracks first."

    # ✅ Create playlist with user's name
    playlist = sp.user_playlist_create(
        user=user_id,
        name=playlist_name,
        public=True,
        description="Created with Flask + Spotify"
    )

    # ✅ Add tracks
    sp.playlist_add_items(playlist_id=playlist["id"], items=track_uris)

    playlist_url = playlist["external_urls"]["spotify"]
    return render_template("playlist_created.html", playlist_url=playlist_url)

@app.route("/summary/<session_id>")
def summary(session_id):
    sessions = load_sessions()
    group = sessions.get(session_id, [])
    return render_template("summary.html", users=group, session_id=session_id)


@app.route("/merge/<session_id>", methods=["POST"])
def merge(session_id):
    token_info = session.get("token_info")
    if not token_info:
        return "❌ Error: No access token found. Try logging in again."

    try:
        sp = Spotify(auth=token_info["access_token"])
        user_id = sp.current_user()["id"]

        sessions = load_sessions()
        group = sessions.get(session_id, [])

        if len(group) < 2:
            return "❌ Error: Need at least two users in the session to merge."

        all_tracks = []
        for user in group:
            all_tracks.extend(user["tracks"])

        if not all_tracks:
            return "❌ Error: No tracks found to merge."

        from collections import Counter
        track_counts = Counter(all_tracks)
        merged_uris = [track for track, count in track_counts.most_common(30)]

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



if __name__ == "__main__":
    app.run(debug=True)
