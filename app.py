import os
import uuid
import json
import time
from flask import Flask, session, redirect, request, render_template
from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")

# ---------- Spotify OAuth Helper ----------
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
    session.clear()
    session["solo_mode"] = True
    session["session_id"] = str(uuid.uuid4())
    return redirect("/login")

@app.route("/login")
def login():
    session_id = session.get("session_id") or str(uuid.uuid4())
    session["session_id"] = session_id
    sp_oauth = make_sp_oauth(session_id)
    auth_url = sp_oauth.get_authorize_url(state=session_id)
    return redirect(auth_url)

@app.route("/callback")
def callback():
    try:
        code = request.args.get("code")
        session_id = session.get("session_id", str(uuid.uuid4()))
        session["session_id"] = session_id
        sp_oauth = make_sp_oauth(session_id)
        token_info = sp_oauth.get_access_token(code)
        session["token_info"] = token_info

        sp = Spotify(auth=token_info["access_token"])
        top_tracks = sp.current_user_top_tracks(limit=20)["items"]

        session["track_uris"] = [track["uri"] for track in top_tracks]
        session["track_names"] = [
            f"{t['name']} by {t['artists'][0]['name']}" for t in top_tracks
        ]
        session["time_range"] = "medium_term"

        return redirect("/top-tracks")
    except Exception as e:
        print("❌ ERROR in /callback:", str(e))
        return "❌ An error occurred during login."

@app.route("/top-tracks", methods=["GET", "POST"])
def top_tracks():
    token_info = session.get("token_info")
    if not token_info:
        return redirect("/login")

    time_range = request.values.get("time_range", "medium_term")
    session["time_range"] = time_range

    track_limit = int(request.values.get("track_limit", 20))
    track_limit = min(max(track_limit, 1), 50)

    session_id = session.get("session_id", "solo")
    sp_oauth = make_sp_oauth(session_id)

    if token_info["expires_at"] < int(time.time()):
        token_info = sp_oauth.refresh_access_token(token_info["refresh_token"])
        session["token_info"] = token_info

    sp = Spotify(auth=token_info["access_token"])
    tracks = sp.current_user_top_tracks(limit=track_limit, time_range=time_range)["items"]

    session["track_uris"] = [track["uri"] for track in tracks]
    session["track_names"] = [
        f"{track['name']} by {track['artists'][0]['name']}" for track in tracks
    ]

    return render_template("top_tracks.html",
                           track_names=session["track_names"],
                           time_range=time_range,
                           track_limit=track_limit)

@app.route("/create-playlist", methods=["GET", "POST"])
def create_playlist():
    if request.method == "GET":
        return "GET method received ✅"

    token_info = session.get("token_info")
    if not token_info:
        return redirect("/login")

    session_id = session.get("session_id", "solo")
    sp_oauth = make_sp_oauth(session_id)

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
