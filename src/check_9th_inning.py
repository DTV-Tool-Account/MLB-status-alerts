import os
import json
import statsapi
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from datetime import datetime, date
import pickle

# Initialize Slack client
slack_token = os.getenv("SLACK_BOT_TOKEN")
channel_id = os.getenv("SLACK_CHANNEL_ID")
client = WebClient(token=slack_token)

# Files to persist data across runs
ALERTED_GAMES_FILE = "alerted_games.pkl"
LAST_SUMMARY_FILE = "last_summary.pkl"

# Summary update interval in minutes
SUMMARY_INTERVAL_MINUTES = 30

def load_alerted_games():
    """Load previously alerted games from file"""
    try:
        if os.path.exists(ALERTED_GAMES_FILE):
            with open(ALERTED_GAMES_FILE, 'rb') as f:
                return pickle.load(f)
    except Exception as e:
        print(f"⚠️ Could not load alerted games: {e}")
    return {}

def save_alerted_games(alerted_games):
    """Save alerted games to file"""
    try:
        with open(ALERTED_GAMES_FILE, 'wb') as f:
            pickle.dump(alerted_games, f)
        print(f"✅ Saved alerted games: {len(alerted_games)} games tracked")
    except Exception as e:
        print(f"⚠️ Could not save alerted games: {e}")

def load_last_summary_time():
    """Load timestamp of last summary sent"""
    try:
        if os.path.exists(LAST_SUMMARY_FILE):
            with open(LAST_SUMMARY_FILE, 'rb') as f:
                return pickle.load(f)
    except Exception as e:
        print(f"⚠️ Could not load last summary time: {e}")
    return None

def save_last_summary_time(timestamp):
    """Save timestamp of last summary sent"""
    try:
        with open(LAST_SUMMARY_FILE, 'wb') as f:
            pickle.dump(timestamp, f)
    except Exception as e:
        print(f"⚠️ Could not save last summary time: {e}")

def should_send_summary():
    """Check if enough time has passed since last summary"""
    from datetime import timedelta
    last_summary = load_last_summary_time()
    now = datetime.now()
    
    if last_summary is None:
        return True
    
    time_since_last = now - last_summary
    should_send = time_since_last >= timedelta(minutes=SUMMARY_INTERVAL_MINUTES)
    
    if should_send:
        print(f"⏰ Summary interval elapsed ({SUMMARY_INTERVAL_MINUTES} min)")
    else:
        remaining = SUMMARY_INTERVAL_MINUTES - int(time_since_last.total_seconds() / 60)
        print(f"⏰ Next summary in {remaining} minutes")
    
    return should_send

def get_weather_emoji(conditions):
    """Return emoji based on weather conditions"""
    if not conditions:
        return "🌤️"
    
    conditions = str(conditions).lower()
    if 'rain' in conditions or 'precipitation' in conditions:
        return "🌧️"
    elif 'cloud' in conditions:
        return "☁️"
    elif 'clear' in conditions or 'sunny' in conditions:
        return "☀️"
    elif 'wind' in conditions:
        return "💨"
    elif 'snow' in conditions:
        return "❄️"
    else:
        return "🌤️"

def get_delay_indicator(status_detail):
    """Check if game is delayed"""
    if not status_detail:
        return None
    
    status_detail = str(status_detail).lower()
    if 'delay' in status_detail:
        return "⏸️ DELAYED"
    elif 'rain' in status_detail:
        return "🌧️ RAIN DELAY"
    elif 'weather' in status_detail:
        return "⛈️ WEATHER DELAY"
    elif 'suspended' in status_detail:
        return "🛑 SUSPENDED"
    
    return None

def check_9th_inning_games():
    """Fetch MLB games and alert only when 9th inning is reached"""
    try:
        # Load previously alerted games
        alerted_games = load_alerted_games()
        print(f"📋 Loaded {len(alerted_games)} previously alerted games")
        
        # Get TODAY'S games
        today = str(date.today())
        print(f"📅 Checking games for: {today}")
        
        schedule = statsapi.schedule(start_date=today, end_date=today)
        
        if not schedule:
            print("No games found for today")
            return
        
        print(f"\n{'='*80}")
        print(f"MLB GAMES STATUS REPORT - {len(schedule)} games found for {today}")
        print(f"{'='*80}\n")
        
        # Filter for in-progress and final games
        active_games = [g for g in schedule if g['status'] in ['In Progress', 'Final', 'Game Over']]
        
        if not active_games:
            print("No games currently in progress or final")
            return
        
        print(f"Active Games: {len(active_games)}\n")
        
        in_progress_games = []
        final_games = []
        new_alerts = []
        
        # Check each game
        for game in active_games:
            try:
                game_pk = game.get('game_id')
                away_team = game.get('away_name', 'Away Team')
                home_team = game.get('home_name', 'Home Team')
                status = game.get('status', 'Unknown')
                away_score = game.get('away_score', 0)
                home_score = game.get('home_score', 0)
                
                # Get detailed game info
                game_data = statsapi.get('game', {'gamePk': game_pk})
                linescore = game_data.get('liveData', {}).get('linescore', {})
                
                current_inning = linescore.get('currentInning', 'N/A')
                inning_state = linescore.get('inningState', 'Unknown')
                
                # Get weather data
                weather = game_data.get('gameData', {}).get('weather', {})
                weather_conditions = weather.get('condition', 'Unknown')
                weather_temp = weather.get('temp', 'N/A')
                weather_wind = weather.get('wind', {})
                wind_speed = weather_wind.get('speed', 'N/A')
                
                # Get game status details (for delays)
                status_detail = game_data.get('gameData', {}).get('status
