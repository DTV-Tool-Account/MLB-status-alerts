#!/usr/bin/env python3
"""
MLS 90th Minute Alert Monitor
Monitors MLS games via ESPN API, sends Slack alerts when games enter 90th minute
"""

import os
import pickle
import sys
from datetime import datetime
import requests
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# Initialize
print("🚀 MLS Script starting...", flush=True)
SLACK_BOT_TOKEN = os.getenv('SLACK_BOT_TOKEN')
SLACK_CHANNEL_ID = os.getenv('SLACK_CHANNEL_ID')

if not SLACK_BOT_TOKEN or not SLACK_CHANNEL_ID:
    print("❌ Missing SLACK_BOT_TOKEN or SLACK_CHANNEL_ID", flush=True)
    sys.exit(1)

client = WebClient(token=SLACK_BOT_TOKEN)
ALERTED_GAMES_FILE = 'alerted_games_mls.pkl'
LAST_SUMMARY_FILE = 'last_summary_mls.pkl'

def load_pickle(filename):
    """Load pickle file, return empty dict/int if missing"""
    if os.path.exists(filename):
        with open(filename, 'rb') as f:
            return pickle.load(f)
    return {} if 'alerted' in filename else 0

def save_pickle(filename, data):
    """Save pickle file"""
    with open(filename, 'wb') as f:
        pickle.dump(data, f)

def get_mls_games():
    """Fetch today's MLS games from ESPN API"""
    print("📡 Fetching MLS games from ESPN API...", flush=True)
    try:
        # ESPN MLS scoreboard endpoint
        url = "https://site.api.espn.com/apis/site/v2/sports/soccer/mls/scoreboard"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        print(f"✅ ESPN API response received: {len(data.get('events', []))} events", flush=True)
        return data.get('events', [])
    except Exception as e:
        print(f"❌ Failed to fetch MLS games: {e}", flush=True)
        return []

def get_game_status(event):
    """Extract game status and minute from event"""
    try:
        status = event.get('status', {})
        status_type = status.get('type', '')
        minute = 0
        
        # Parse minute from status detail
        if 'details' in status:
            detail_text = status.get('details', '')
            if "'" in detail_text:
                try:
                    minute = int(detail_text.split("'")[0].strip())
                except:
                    minute = 0
        
        return status_type, minute
    except Exception as e:
        print(f"⚠️  Error parsing game status: {e}", flush=True)
        return 'unknown', 0

def get_score(event):
    """Extract score from event"""
    try:
        competitors = event.get('competitors', [])
        if len(competitors) >= 2:
            home = competitors[0]
            away = competitors[1]
            home_score = home.get('score', 0)
            away_score = away.get('score', 0)
            return home_score, away_score
        return 0, 0
    except Exception as e:
        print(f"⚠️  Error parsing score: {e}", flush=True)
        return 0, 0

def get_team_names(event):
    """Extract team names from event"""
    try:
        competitors = event.get('competitors', [])
        if len(competitors) >= 2:
            home_name = competitors[0].get('team', {}).get('displayName', 'Unknown')
            away_name = competitors[1].get('team', {}).get('displayName', 'Unknown')
            return home_name, away_name
        return 'Unknown', 'Unknown'
    except Exception as e:
        print(f"⚠️  Error parsing team names: {e}", flush=True)
        return 'Unknown', 'Unknown'

def get_weather_emoji(event):
    """Get weather emoji (basic for MLS)"""
    try:
        weather = event.get('weather', {})
        if weather:
            description = weather.get('description', '').lower()
            if 'rain' in description:
                return '🌧️'
            elif 'cloud' in description:
                return '☁️'
            elif 'sunny' in description or 'clear' in description:
                return '☀️'
        return '🌫️'
    except:
        return '🌫️'

def send_90th_minute_alert(home_team, away_team, home_score, away_score, minute):
    """Send Slack alert for 90th minute"""
    print(f"🔔 Sending 90th minute alert: {away_team} @ {home_team}", flush=True)
    try:
        message = f"""
🚨 **90'** {away_team} ({away_score}) @ {home_team} ({home_score})
Final whistle incoming! ⏱️
"""
        client.chat_postMessage(
            channel=SLACK_CHANNEL_ID,
            text=message.strip()
        )
        print("✅ Alert sent!", flush=True)
    except SlackApiError as e:
        print(f"❌ Slack error: {e.response['error']}", flush=True)

def send_games_summary(games):
    """Send summary of all MLS games"""
    print(f"📊 Sending MLS summary for {len(games)} games", flush=True)
    try:
        final_games = []
        in_progress = []
        
        for game in games:
            try:
                home_team, away_team = get_team_names(game)
                home_score, away_score = get_score(game)
                status_type, minute = get_game_status(game)
                weather = get_weather_emoji(game)
                
                game_display = f"{minute if minute > 0 else ''} {away_team} ({away_score}) @ {home_team} ({home_score})"
                
                if status_type == 'STATUS_FINAL':
                    final_games.append(f"{game_display.strip()} {weather}")
                elif status_type in ['STATUS_IN_PROGRESS', 'STATUS_LIVE']:
                    in_progress.append(f"{game_display.strip()} {weather}")
            except Exception as e:
                print(f"⚠️  Error processing game: {e}", flush=True)
                continue
        
        # Build message
        message_parts = ["⚽ **MLS Games Update**"]
        
        if final_games:
            message_parts.append("\n**FINAL**")
            for game in final_games:
                message_parts.append(game)
        
        if in_progress:
            message_parts.append("\n**IN PROGRESS**")
            for game in in_progress:
                message_parts.append(game)
        
        if not final_games and not in_progress:
            message_parts.append("\nNo games today")
        
        message = "\n".join(message_parts)
        message += f"\n_Updated {datetime.now().strftime('%I:%M %p %Z')}_"
        
        client.chat_postMessage(
            channel=SLACK_CHANNEL_ID,
            text=message
        )
        print("✅ Summary sent!", flush=True)
    except SlackApiError as e:
        print(f"❌ Slack error: {e.response['error']}", flush=True)

def main():
    """Main execution"""
    print("Starting MLS 90th minute check...", flush=True)
    
    # Load tracking files
    alerted_games = load_pickle(ALERTED_GAMES_FILE)
    last_summary = load_pickle(LAST_SUMMARY_FILE)
    
    # Fetch games
    games = get_mls_games()
    if not games:
        print("ℹ️  No games found", flush=True)
        return
    
    # Process each game
    for game in games:
        try:
            game_id = game.get('id', '')
            home_team, away_team = get_team_names(game)
            home_score, away_score = get_score(game)
            status_type, minute = get_game_status(game)
            
            # Alert on 90th minute
            if minute == 90 and game_id not in alerted_games:
                send_90th_minute_alert(home_team, away_team, home_score, away_score, minute)
                alerted_games[game_id] = True
                save_pickle(ALERTED_GAMES_FILE, alerted_games)
        except Exception as e:
            print(f"⚠️  Error processing game {game.get('id', 'unknown')}: {e}", flush=True)
            continue
    
    # Send summary every 30 min
    now = datetime.now().timestamp()
    if now - last_summary > 1800:  # 30 minutes
        send_games_summary(games)
        save_pickle(LAST_SUMMARY_FILE, now)
    
    print("✅ MLS check complete", flush=True)

if __name__ == '__main__':
    main()
