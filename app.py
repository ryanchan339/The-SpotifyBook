from flask import Flask, session, redirect, request, render_template
import os
from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24)

sp_oauth = SpotifyOAuth(
    client_id=os.getenv("SPOTIPY_CLIENT_ID"),
    client_secret=os.getenv("SPOTIPY_CLIENT_SECRET"),
    redirect_uri=os.getenv("SPOTIPY_REDIRECT_URI"),
    scope="user-top-read playlist-modify-public playlist-modify-private"
)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/login")
def login():
    auth_url = sp_oauth.get_authorize_url()
    return redirect(auth_url)



@app.route("/callback")
def callback():
    code = request.args.get("code")
    token_info = sp_oauth.get_access_token(code)
    session["token_info"] = token_info
    return redirect("/choose-range")

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




if __name__ == "__main__":
    app.run(debug=True)
