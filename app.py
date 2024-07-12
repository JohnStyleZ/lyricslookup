from flask import Flask, render_template, request, redirect, url_for
import requests
import logging
import hashlib

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.DEBUG)

def verify_nonce(result, target):
    if len(result) != len(target):
        return False

    for i in range(len(result)):
        if result[i] > target[i]:
            return False
        elif result[i] < target[i]:
            break
    
    return True

def solve_challenge(prefix, target_hex):
    nonce = 0
    target = bytes.fromhex(target_hex)

    while True:
        token = f"{prefix}:{nonce}".encode()
        hash_result = hashlib.sha256(token).digest()

        if verify_nonce(hash_result, target):
            break
        
        nonce += 1

    return nonce

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/submit-lyrics', methods=['POST'])
def submit_lyrics():
    track_name = request.form.get('trackName')
    artist_name = request.form.get('artistName')
    album_name = request.form.get('albumName')
    duration = request.form.get('duration')
    plain_lyrics = request.form.get('plainLyrics')
    synced_lyrics = request.form.get('syncedLyrics')

    if not (track_name and artist_name and album_name and duration):
        return "All fields are required", 400

    # Request a challenge
    challenge_response = requests.post("https://lrclib.net/api/request-challenge")
    if challenge_response.status_code != 200:
        logging.error("Failed to request challenge: %s", challenge_response.text)
        return "Failed to request challenge", 500
    
    challenge_data = challenge_response.json()
    prefix = challenge_data['prefix']
    target_hex = challenge_data['target']
    logging.error(challenge_data)
    # Solve the proof-of-work challenge
    nonce = solve_challenge(prefix, target_hex)
    publish_token = f"{prefix}:{nonce}"
    logging.error(publish_token)

    # Publish new lyrics
    headers = {"X-Publish-Token": publish_token}
    payload = {
        "trackName": track_name,
        "artistName": artist_name,
        "albumName": album_name,
        "duration": float(duration),
        "plainLyrics": plain_lyrics,
        "syncedLyrics": synced_lyrics
    }
    
    publish_response = requests.post("https://lrclib.net/api/publish", headers=headers, json=payload)
    
    if publish_response.status_code == 201:
        return redirect(url_for('submit_lyrics'))
    else:
        return f"Failed to publish lyrics: {publish_response.text}", 400

@app.route('/search', methods=['GET', 'POST'])
def search_lyrics():
    if request.method == 'POST':
        query = request.form['query']
        
        search_params = {'q': query}
        
        # Search in LRCLIB
        lrclib_response = requests.get("https://lrclib.net/api/search", params=search_params)
        if lrclib_response.status_code != 200:
            logging.error("LRCLIB search request failed: %s", lrclib_response.text)
            return "Search failed", 500
        
        lrclib_data = lrclib_response.json()
        lrclib_results = []
        if lrclib_data:
            for result in lrclib_data:
                lrclib_results.append({
                    'id': result['id'],
                    'title': result['trackName'],
                    'artist': result['artistName'],
                    'album': result['albumName'],
                    'duration': result['duration'],
                    'instrumental': result['instrumental'],
                    'plainLyrics': result['plainLyrics'],
                    'syncedLyrics': result['syncedLyrics']
                })

        # Search in Musixmatch
        musixmatch_response = requests.get(f"https://api.musixmatch.com/ws/1.1/track.search?q_track_artist={query}&apikey=6b37529ae367388dfd64690afdfd7601")
        if musixmatch_response.status_code != 200:
            logging.error("Musixmatch search request failed: %s", musixmatch_response.text)
            return "Search failed", 500
        
        musixmatch_data = musixmatch_response.json()
        musixmatch_results = []
        if musixmatch_data['message']['body']['track_list']:
            for track in musixmatch_data['message']['body']['track_list']:
                musixmatch_results.append({
                    'id': track['track']['track_id'],
                    'title': track['track']['track_name'],
                    'artist': track['track']['artist_name'],
                    'album': track['track']['album_name'],
                    'source': 'musixmatch'
                })

        # Merge results from both APIs
        search_results = lrclib_results + musixmatch_results

        # Fetch top artists from search results
        top_artists = get_top_artists(search_results)
        
        # Fetch albums for each top artist
        albums = []
        for artist in top_artists:
            artist_albums = fetch_albums(artist)
            albums.extend(artist_albums)
        
        return render_template('search_results.html', results=search_results, query=query, albums=albums)
    
    return render_template('index.html')

@app.route('/lyrics/<int:song_id>')
def get_lyrics(song_id):
    # Retrieve the source from the query string to determine the API to fetch from
    source = request.args.get('source')
    title = request.args.get('title')
    artist = request.args.get('artist')

    if source == 'musixmatch' and title and artist:
        # Fetch lyrics from lrc.cx
        lrc_cx_response = requests.get(f"https://api.lrc.cx/api/v1/lyrics/single?title={title}&artist={artist}")
        if lrc_cx_response.status_code == 200:
            lyrics_text = lrc_cx_response.text
            return render_template('lyrics.html', 
                                   artist=artist,
                                   song_title=title,
                                   lyrics=lyrics_text,
                                   lyrics_with_timecodes=lyrics_text)
        else:
            return "Lyrics not found in lrc.cx", 404
    else:
        # Fetch lyrics from LRCLIB
        response = requests.get(f'https://lrclib.net/api/get/{song_id}')
        if response.status_code == 404:
            return "Lyrics not found", 404
        elif response.status_code != 200:
            logging.error("Failed to fetch lyrics: %s", response.text)
            return "Failed to fetch lyrics", 500
        
        data = response.json()
        return render_template('lyrics.html', 
                               artist=data['artistName'],
                               song_title=data['trackName'],
                               lyrics=data['syncedLyrics'],
                               lyrics_with_timecodes=data['syncedLyrics'])

@app.route('/artist/<artist>')
def artist_songs(artist):
    # Pagination handling
    page = request.args.get('page', 1, type=int)
    per_page = 10  # Number of songs per page
    
    # Search in LRCLIB
    lrclib_search_params = {'q': artist, 'page': page, 'per_page': per_page}
    lrclib_response = requests.get("https://lrclib.net/api/search", params=lrclib_search_params)
    if lrclib_response.status_code != 200:
        logging.error(f"Failed to fetch artist data from LRCLIB API: {lrclib_response.status_code}")
        return render_template('error.html', message="Failed to fetch artist data from LRCLIB API.")
    
    lrclib_data = lrclib_response.json()
    lrclib_songs = []
    if lrclib_data:
        for result in lrclib_data:
            lrclib_songs.append({
                'id': result['id'],
                'title': result['trackName'],
                'artist': result['artistName'],
                'album': result['albumName'],
                'duration': result['duration'],
                'instrumental': result['instrumental'],
                'plainLyrics': result['plainLyrics'],
                'syncedLyrics': result['syncedLyrics']
            })

    # Search in Musixmatch
    musixmatch_response = requests.get(f"https://api.musixmatch.com/ws/1.1/track.search?q_artist={artist}&apikey=6b37529ae367388dfd64690afdfd7601&page_size={per_page}&page={page}")
    if musixmatch_response.status_code != 200:
        logging.error(f"Failed to fetch artist data from Musixmatch API: {musixmatch_response.status_code}")
        return render_template('error.html', message="Failed to fetch artist data from Musixmatch API.")
    
    musixmatch_data = musixmatch_response.json()
    musixmatch_songs = []
    if musixmatch_data['message']['body']['track_list']:
        for track in musixmatch_data['message']['body']['track_list']:
            musixmatch_songs.append({
                'id': track['track']['track_id'],
                'title': track['track']['track_name'],
                'artist': track['track']['artist_name'],
                'album': track['track']['album_name'],
                'source': 'musixmatch'
            })

    # Merge results from both APIs
    songs = lrclib_songs + musixmatch_songs

    return render_template('artist_songs.html', songs=songs, artist=artist, page=page)

def get_top_artists(results):
    # Function to extract top artists from search results
    artists = set()
    for result in results:
        artists.add(result['artist'])
        if len(artists) >= 3:
            break
    return list(artists)

def fetch_albums(artist):
    # Example function to fetch albums data from an external API (replace with actual implementation)
    # For demonstration, using mock data
    return ['Album 1', 'Album 2', 'Album 3']

if __name__ == '__main__':
    app.run(debug=True, port=10000)
