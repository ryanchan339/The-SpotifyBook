import uuid
import json
import os
from flask import Flask, session, redirect, request, render_template
from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")  # set this in your .env or on Render

SESSION_STORE = "sessions.json"

def load_sessions():
    if not os.path.exists(SESSION_STORE):
        return {}
    with open(SESSION_STORE, "r") as f:
        return json.load(f)

def save_sessions(sessions):
    with open(SESSION_STORE, "w") as f:
        json.dump(sessions, f)

def make_sp_oauth(cache_path):
    """
    Build a SpotifyOAuth that uses `cache_path` for this session.
    We do NOT pass auth_args here (older Spotipy versions don’t support that).
    """
    return SpotifyOAuth(
        client_id=os.getenv("SPOTIPY_CLIENT_ID"),
        client_secret=os.getenv("SPOTIPY_CLIENT_SECRET"),
        redirect_uri=os.getenv("SPOTIPY_REDIRECT_URI"),
        scope="user-top-read playlist-modify-public playlist-modify-private",
        cache_path=cache_path
    )



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
    Simple homepage. You might include a "Start New Session" button here
    pointing to /new-session, or instructions for pasting a join link.
    """
    return render_template("index.html")

@app.route("/login")
def login():
    """
    1. Look for ?session_id=... in the URL. If present, save it to session["session_id"].
    2. If session["session_id"] still doesn’t exist, generate a new one, save it,
       store it in sessions.json, and then redirect to /login?session_id=<new>.
    3. At this point, we guarantee session["session_id"] exists. Build a SpotifyOAuth
       using a unique cache_path based on that session ID.
    4. Force Spotify to show the login prompt by passing show_dialog=True to get_authorize_url().
    5. Redirect the user to Spotify’s authorization URL.
    """
    # 1. If the URL includes ?session_id=..., save it in the Flask session
    sid = request.args.get("session_id")
    if sid:
        session["session_id"] = sid

    # 2. If there’s still no session["session_id"], create one now
    elif "session_id" not in session:
        sid = str(uuid.uuid4())
        session["session_id"] = sid

        # Initialize an empty list for this session in sessions.json
        sessions = load_sessions()
        sessions[sid] = []
        save_sessions(sessions)

        # Redirect back to /login with ?session_id=<new-id> so step 1 can pick it up
        return redirect(f"/login?session_id={sid}")

    # 3. Now session["session_id"] definitely exists
    session_id = session["session_id"]

    # 4. Build a SpotifyOAuth that uses a cache file named ".cache-<session_id>"
    cache_path = f".cache-{session_id}"
    sp_oauth = make_sp_oauth(cache_path)

    # 5. Generate the Spotify authorize URL, passing session_id as "state"
    #    Also pass show_dialog=True so Spotify always forces credential entry.
    auth_url = sp_oauth.get_authorize_url(state=session_id, show_dialog=True)

    return redirect(auth_url)



@app.route("/callback")
def callback():
    """
    This is where Spotify redirects after the user authorizes (or denies).
    Spotify calls /callback?code=<code>&state=<session_id>.
    We:
      1. Grab code and state (the session ID).
      2. Recreate the same cache_path and SpotifyOAuth.
      3. Exchange the code for a token.
      4. Fetch the user’s profile + top tracks.
      5. Append that data (display_name + track URIs) into sessions.json under that session_id.
      6. Redirect to /summary/<session_id>.
    """
    # 1. Get the authorization code and state (session_id) from Spotify’s redirect
    code = request.args.get("code")
    state_session_id = request.args.get("state")
    session_id = state_session_id or session.get("session_id")

    if not session_id:
        return "❌ Error: Missing session ID. Please start or join a session first."

    # 2. Reconstruct the same cache_path and SpotifyOAuth used during /login
    cache_path = f".cache-{session_id}"
    sp_oauth = make_sp_oauth(cache_path)

    # 3. Exchange the code for a token
    token_info = sp_oauth.get_access_token(code)
    session["token_info"] = token_info
    session["session_id"] = session_id  # re-save it just in case

    # 4. Use Spotipy to fetch the user’s profile and their top tracks
    sp = Spotify(auth=token_info["access_token"])
    profile = sp.current_user()
    top_tracks_data = sp.current_user_top_tracks(limit=20, time_range="medium_term")
    track_uris = [t["uri"] for t in top_tracks_data["items"]]

    # 5. Append this user’s info (display_name + tracks) to sessions.json
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
    (Optional) If you want a separate page to pick the time range,
    you can render choose_range.html here. Currently not used in this flow.
    """
    return render_template("choose_range.html")



@app.route("/top-tracks", methods=["POST"])
def top_tracks():
    """
    This route expects a form POST with a 'time_range' field.
    It reads session["token_info"] to get the access token, then
    fetches the current user’s top tracks within that time_range,
    stores track URIs and names in Flask’s session, and finally
    renders top_tracks.html with the list of track names.
    """
    token_info = session.get("token_info")
    if not token_info:
        return redirect("/login")

    time_range = request.form.get("time_range", "medium_term")
    session["time_range"] = time_range

    sp = Spotify(auth=token_info["access_token"])
    tracks = sp.current_user_top_tracks(limit=10, time_range=time_range)["items"]

    session["track_uris"] = [track["uri"] for track in tracks]
    session["track_names"] = [
        f"{track['name']} by {track['artists'][0]['name']}" for track in tracks
    ]

    return render_template("top_tracks.html",
                           track_names=session["track_names"],
                           time_range=time_range)



@app.route("/create-playlist", methods=["POST"])
def create_playlist():
    """
    Creates a new playlist in the user’s account with the name provided
    via form field 'playlist_name', then adds all track URIs saved under
    session["track_uris"] to that playlist. Renders playlist_created.html
    with the Spotify playlist URL when done.
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
    Shows the “Playlist Session: <session_id>” page, listing all joined users.
    Passes `users=group` and `session_id=session_id` into summary.html.
    """
    sessions = load_sessions()
    group = sessions.get(session_id, [])
    return render_template("summary.html", users=group, session_id=session_id)



@app.route("/merge/<session_id>", methods=["POST"])
def merge(session_id):
    """
    Reads session["token_info"] to get an access token, then
    merges all track URIs from every user in sessions.json[session_id]
    by frequency (most common first). Creates a new playlist named
    "Merged Playlist (X users)" containing the top‐common tracks and
    renders playlist_created.html with the final playlist URL.
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
        # Take the top 30 most common track URIs
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
