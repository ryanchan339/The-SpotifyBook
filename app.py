import os
import uuid
import time
import requests
from flask import Flask, session, redirect, request, render_template
from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv
from flask import jsonify
from spotipy.oauth2 import SpotifyClientCredentials

client_credentials_manager = SpotifyClientCredentials(
    client_id=os.getenv("SPOTIPY_CLIENT_ID"),
    client_secret=os.getenv("SPOTIPY_CLIENT_SECRET")
)

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

def get_spotify_client():
    token_info = session.get("token_info")
    if not token_info:
        return None

    session_id = session.get("session_id", "solo")
    sp_oauth = make_sp_oauth(session_id)

    if token_info["expires_at"] < int(time.time()):
        token_info = sp_oauth.refresh_access_token(token_info["refresh_token"])
        session["token_info"] = token_info

    return Spotify(auth=token_info["access_token"])

# ---------- Routes ----------
@app.route("/")
def index():
    return render_template("index.html")

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
        tracks = sp.current_user_top_tracks(limit=20)["items"]

        session["track_info"] = [
            {
                "name": track["name"],
                "artist": track["artists"][0]["name"],
                "uri": track["uri"],
                "image": track["album"]["images"][0]["url"],
            }
            for track in tracks
        ]


        session["time_range"] = "medium_term"

        return redirect("/top-tracks")
    except Exception as e:
        print("❌ ERROR in /callback:", str(e))
        return "❌ An error occurred during login."

@app.route("/top-tracks")
def top_tracks():
    return render_template("top_tracks.html")

@app.route("/api/top-tracks")
def api_top_tracks():
    sp = get_spotify_client()
    if not sp:
        return jsonify({"error": "Not logged in"}), 401

    time_range = request.args.get("time_range", "medium_term")
    track_limit = int(request.args.get("limit", 50))

    try:
        tracks = sp.current_user_top_tracks(limit=track_limit, time_range=time_range)["items"]
    except Exception as e:
        print("❌ ERROR in /api/top-tracks:", str(e))
        return jsonify({"error": "Failed to fetch tracks"}), 500

    track_info = [
        {
            "name": t["name"],
            "artist": t["artists"][0]["name"],
            "uri": t["uri"],
            "image": t["album"]["images"][0]["url"] if t["album"]["images"] else None,
        }
        for t in tracks
    ]

    session["track_info"] = track_info  # ✅ Store for create-playlist

    return jsonify(track_info)



@app.route("/top-artists")
def top_artists():
    sp = get_spotify_client()
    if not sp:
        return redirect("/login")

    artists = sp.current_user_top_artists(limit=20)["items"]

    artist_info = [
        {
            "name": artist["name"],
            "image": artist["images"][0]["url"] if artist["images"] else None,
            "genres": artist["genres"],
            "spotify_url": artist["external_urls"]["spotify"]
        }
        for artist in artists
    ]

    return render_template("top_artists.html", artist_info=artist_info)

@app.route("/api/top-artists")
def api_top_artists():
    sp = get_spotify_client()
    if not sp:
        return {"error": "Not authenticated"}, 401

    time_range = request.args.get("time_range", "medium_term")

    artists = sp.current_user_top_artists(limit=20, time_range=time_range)["items"]

    result = [
        {
            "name": artist["name"],
            "genres": artist.get("genres", []),
            "image": artist["images"][0]["url"] if artist["images"] else ""
        }
        for artist in artists
    ]

    return result

@app.route("/search")
def search_page():
    return render_template("search.html")


@app.route("/api/search")
def search_api():
    query = request.args.get("q", "")
    if not query:
        return jsonify([])

    try:
        sp = Spotify(client_credentials_manager=client_credentials_manager)
        results = sp.search(q=query, type="track,artist", limit=5)

        response = []

        for track in results.get("tracks", {}).get("items", []):
            response.append({
                "type": "track",
                "name": track["name"],
                "artist": track["artists"][0]["name"],
                "image": track["album"]["images"][0]["url"]
            })

        for artist in results.get("artists", {}).get("items", []):
            response.append({
                "type": "artist",
                "name": artist["name"],
                "image": artist["images"][0]["url"] if artist["images"] else None
            })

        return jsonify(response)

    except Exception as e:
        print("❌ Error in /api/search:", e)
        return jsonify({"error": "Search failed"}), 500



@app.route("/create-playlist", methods=["GET", "POST"])
def create_playlist():
    if request.method == "GET":
        return "GET method received ✅"

    sp = get_spotify_client()
    if not sp:
        return redirect("/login")

    user_id = sp.current_user()["id"]
    track_info = session.get("track_info", [])
    track_uris = [track["uri"] for track in track_info]


    playlist_name = request.form.get("playlist_name", "My Top Tracks")

    if not track_uris:
        return "❌ No tracks to add. Go back and fetch top tracks first."

    playlist = sp.user_playlist_create(
        user=user_id,
        name=playlist_name,
        public=False,
        description="Created with The SpotifyBook"
    )
    sp.playlist_add_items(playlist_id=playlist["id"], items=track_uris)

    playlist_url = playlist["external_urls"]["spotify"]
    return render_template("playlist_created.html", playlist_url=playlist_url)

if __name__ == "__main__":
    app.run(debug=True)
