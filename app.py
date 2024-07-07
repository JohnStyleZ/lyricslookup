from flask import Flask, render_template, request
import requests
from bs4 import BeautifulSoup
import logging

app = Flask(__name__)

# Genius API configuration
GENIUS_API_TOKEN = 'J3JSftf6dhyzhswThz8ot_cVpu4JW2wbBR6p_mm6JMvQzsy1qpvN9ht3_PJgl4Re'
GENIUS_SEARCH_URL = 'https://api.genius.com/search'
GENIUS_HEADERS = {'Authorization': f'Bearer {GENIUS_API_TOKEN}'}

# Configure logging
logging.basicConfig(level=logging.DEBUG)

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/search', methods=['GET', 'POST'])
def search_lyrics():
    if request.method == 'POST':
        query = request.form['query']
        
        search_params = {'q': query}
        response = requests.get(GENIUS_SEARCH_URL, headers=GENIUS_HEADERS, params=search_params)
        data = response.json()
        
        search_results = []
        if 'response' in data and data['response']['hits']:
            for hit in data['response']['hits']:
                result = hit['result']
                search_results.append({
                    'id': result['id'],
                    'title': result['title'],
                    'artist': result['primary_artist']['name'],
                    'image_url': result.get('song_art_image_thumbnail_url', ''),
                    'views': result.get('stats', {}).get('pageviews', 'N/A')
                })
        
        # Fetch top artists from search results
        top_artists = get_top_artists(search_results)
        
        return render_template('search_results.html', results=search_results, query=query)
    
    return render_template('index.html')

@app.route('/lyrics/<int:song_id>')
def get_lyrics(song_id):
    song_url = f'https://api.genius.com/songs/{song_id}'
    response = requests.get(song_url, headers=GENIUS_HEADERS)
    data = response.json()
    
    if 'response' in data and 'song' in data['response']:
        song = data['response']['song']
        lyrics = search_and_scrape_lyrics(song['url']).strip()  # Ensure lyrics are stripped of leading/trailing spaces
        
        # Log fetched lyrics
        logging.debug(f"Lyrics fetched for '{song['title']}' by '{song['primary_artist']['name']}':\n{lyrics}")
        
        # Ensure there's an empty line at the beginning
        if lyrics and lyrics.startswith(' '):
            lyrics = '\n' + lyrics  # Prepend an empty line if lyrics start with a space
        
        return render_template('lyrics.html', 
                               artist=song['primary_artist']['name'],
                               song_title=song['title'],
                               lyrics='\n' + lyrics)
    else:
        logging.error(f"Failed to fetch lyrics for song ID: {song_id}")
        return "Lyrics not found", 404

@app.route('/artist/<artist>')
def artist_songs(artist):
    # Mocked albums data for demonstration
    albums = ['Album 1', 'Album 2', 'Album 3']
    return render_template('artist_songs.html', artist=artist, albums=albums)

def search_and_scrape_lyrics(url):
    page = requests.get(url)
    soup = BeautifulSoup(page.content, 'html.parser')
    
    # Try different possible selectors
    selectors = [
        'div[class^="Lyrics__Container"]',
        '.lyrics',
        'div[class^="SongPageGriddesktop__LyricsWrapper"]'
    ]
    
    for selector in selectors:
        lyrics_containers = soup.select(selector)
        if lyrics_containers:
            lyrics = []
            for container in lyrics_containers:
                for br in container.find_all('br'):
                    br.replace_with('\n')
                lyrics.append(container.get_text())
            lyrics = '\n\n'.join(lyrics).strip()
            if lyrics:
                return lyrics
    
    logging.debug("Lyrics not found with any known selector")
    return "Lyrics not found"

def get_top_artists(results):
    # Function to extract top artists from search results
    artists = {}
    artist_count = 0
    for result in results:
        artist = result['artist']
        if artist not in artists and artist_count < 3:
            artists[artist] = result['image_url']
            artist_count += 1
    return list(artists.keys())

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=10000)
