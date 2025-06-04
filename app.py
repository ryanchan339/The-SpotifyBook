import uuid
import json
import os
from flask import Flask, session, redirect, request, render_template
from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv

# ──────────────────────────────────────────────────────────────────────────────
# Load .env (locally) or use the environment variables you set on Render
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")  # Must be set in .env or on Render

# Path to your JSON file that stores all session data
SESSION_STORE = "sessions.json"


def load_sessions():
    """Return the dict stored in sessions.json, or {} if it doesn't exist."""
    if not os.path.exists(SESSION_STORE):
        return {}
    with open(SESSION_STORE, "r") as f:
        return json.load(f)


def save_sessions(sessions):
    """Save the `sessions` dict back to sessions.json."""
    with open(SESSION_STORE, "w") as f:
        json.dump(sessions, f)


def make_sp_oauth(cache_path):
    """
    Build and return a SpotifyOAuth that uses `cache_path` for its token cache.
    (We do NOT pass auth_args here because this Spotipy version does not support them.)
    """
    return SpotifyOAuth(
        client_id=os.getenv("SPOTIPY_CLIENT_ID"),
        client_secret=os.getenv("SPOTIPY_CLIENT_SECRET"),
        redirect_uri=os.getenv("SPOTIPY_REDIRECT_URI"),
        scope="user-top-read playlist-modify-public playlist-modify-private",
        cache_path=cache_path
    )


# ──────────────────────────────────────────────────────────────────────────────
@app.route("/new-session")
def new_session():
    """
    Create a brand-new session ID, store it in sessions.json as an empty list,
    then redirect to /join/<session_id> so that session["session_id"] gets set.
    """
    session_id = str(uuid.uuid4())
    sessions = load_sessions()
    sessions[session_id] = []
    save_sessions(sessions)
    return redirect(f"/join/{session_id}")


@app.route("/join/<session_id>")
def join(session_id):
    """
    When someone visits /join/<session_id>, store that ID in Flask's session cookie
    and then send them to /login to begin Spotify OAuth.
    """
    session["session_id"] = session_id
    return redirect("/login")


@app.route("/")
def index():
    """
    A simple homepage. You can include a "Start New Session" button here
    (pointing to /new-session) and a brief instruction for joining an existing
    session via a shared link.
    """
    return render_template("index.html")


@app.route("/login")
def login():
    """
    1. If ?session_id=... is in the URL, save it in session["session_id"].
    2. If session["session_id"] still does not exist, create a new UUID, store
       in session and sessions.json, and redirect back to /login?session_id=<new>.
    3. Now that session["session_id"] definitely exists, build a cache_path
       and create a SpotifyOAuth using that cache_path.
    4. Call get_authorize_url(state=session_id, show_dialog=True) to force a
       fresh Spotify login prompt (so your friend cannot reuse your cookie).
    5. Redirect to Spotify’s OAuth URL.
    """
    # 1. Check if the URL included ?session_id=<...>
    sid = request.args.get("session_id")
    if sid:
        session["session_id"] = sid

    # 2. If there’s still no session["session_id"], create it now
    elif "session_id" not in session:
        sid = str(uuid.uuid4())
        session["session_id"] = sid

        # Initialize an empty list for this new session
        sessions = load_sessions()
        sessions[sid] = []
        save_sessions(sessions)

        # Redirect to /login?session_id=<new_uuid> so the next request sees it
        return redirect(f"/login?session_id={sid}")

    # 3. At this point, session["session_id"] definitely exists
    session_id = session["session_id"]

    # 4. Build a SpotifyOAuth that uses a cache file named ".cache-<session_id>"
    cache_path = f".cache-{session_id}"
    sp_oauth = make_sp_oauth(cache_path)

    # 5. Generate the Spotify authorize URL, passing state=session_id,
    #    and force a fresh login with show_dialog=True
    auth_url = sp_oauth.get_authorize_url(state=session_id, show_dialog=True)
    return redirect(auth_url)


@app.route("/callback")
def callback():
    """
    Spotify redirects back here as /callback?code=<auth_code>&state=<session_id>.
    1. Read code and state (session_id).
    2. Re-create the same cache_path and SpotifyOAuth used in /login.
    3. Exchange code for an access token.
    4. Fetch the user's profile + top tracks.
    5. Append the user’s display_name + track_uris to sessions.json under that session_id.
    6. Redirect to /summary/<session_id>.
    """
    # 1. Pull code and state from Spotify’s redirect
    code = request.args.get("code")
    state_session_id = request.args.get("state")
    session_id = state_session_id or session.get("session_id")
    if not session_id:
        return "❌ Error: Missing session ID. Please start or join a session first."

    # 2. Re-create the same cache_path and SpotifyOAuth used during /login
    cache_path = f".cache-{session_id}"
    sp_oauth = make_sp_oauth(cache_path)

    # 3. Exchange the code for a token
    token_info = sp_oauth.get_access_token(code)
    session["token_info"] = token_info
    session["session_id"] = session_id  # ensure it’s stored in the cookie

    # 4. Use Spotipy to fetch the current user’s profile & top tracks
    sp = Spotify(auth=token_info["access_token"])
    profile = sp.current_user()
    top_tracks_data = sp.current_user_top_tracks(limit=20, time_range="medium_term")
    track_uris = [t["uri"] for t in top_tracks_data["items"]]

    # 5. Append this user’s data (display_name + track_uris) to sessions.json
    all_sessions = load_sessions()
    if session_id in all_sessions:
        all_sessions[session_id].append({
            "user": profile["display_name"],
            "tracks": track_uris
        })
        save_sessions(all_sessions)

    # 6. Redirect the user to the summary page for that session
    return redirect(f"/summary/{session_id}")


@app.route("/choose-range")
def choose_range():
    """
    (Optional) If you want a separate page to choose time_range before
    fetching top tracks, render it here. Currently not used by the login/merge flow.
    """
    return render_template("choose_range.html")


@app.route("/top-tracks", methods=["POST"])
def top_tracks():
    """
    Expects a form POST with 'time_range' (short_term / medium_term / long_term).
    Reads session["token_info"], fetches that user’s top tracks for that range,
    stores track_uris and track_names in session, then renders top_tracks.html.
    """
    token_info = session.get("token_info")
    if not token_info:
        return redirect("/login")

    time_range = request.form.get("time_range", "medium_term")
    session["time_range"] = time_range

    sp = Spotify(auth=token_info["access_token"])
    tracks = sp.current_user_top_tracks(limit=10, time_range=time_range)["items"]

    # Save URIs and names so we can create a playlist later
    session["track_uris"] = [track["uri"] for track in tracks]
    session["track_names"] = [
        f"{track['name']} by {track['artists'][0]['name']}"
        for track in tracks
    ]

    return render_template("top_tracks.html",
                           track_names=session["track_names"],
                           time_range=time_range)


@app.route("/create-playlist", methods=["POST"])
def create_playlist():
    """
    Creates a playlist named by the form field 'playlist_name', adds all URIs
    from session["track_uris"], then renders playlist_created.html with the final URL.
    """
    token_info = session.get("token_info")
    if not token_info:
        return redirect("/login")

    sp = Spotify(auth=token_info["access_token"])
    user_id = sp.current_user()["id"]
    track_uris = session.get("track_uris", [])

    playlist_name = request.form.get("playlist_name", "My Top Tracks")
    if not track_uris:
        return "No tracks found in session. Go back and fetch top tracks first."

    playlist = sp.user_playlist_create(
        user=user_id,
        name=playlist_name,
        public=True,
        description="Created with Flask + Spotify"
    )
    sp.playlist_add_items(playlist_id=playlist["id"], items=track_uris)
    playlist_url = playlist["external_urls"]["spotify"]

    return render_template("playlist_created.html", playlist_url=playlist_url)


@app.route("/summary/<session_id>")
def summary(session_id):
    """
    Renders summary.html, passing `users=group` (a list of {user, tracks})
    and `session_id=session_id` into the template.
    """
    sessions = load_sessions()
    group = sessions.get(session_id, [])
    return render_template("summary.html", users=group, session_id=session_id)


@app.route("/merge/<session_id>", methods=["POST"])
def merge(session_id):
    """
    Reads session["token_info"] for the access token, then merges all track URIs
    from sessions.json[session_id] by frequency (most common first), creates a
    new playlist called "Merged Playlist (<number_of_users> users)", and renders
    playlist_created.html with the new playlist URL.
    """
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
