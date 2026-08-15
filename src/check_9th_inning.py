import os
import json
import statsapi
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from datetime import datetime, date
import pickle
import sys

print("🚀 Script starting...", flush=True)

# Initialize Slack client
slack_token = os.getenv("SLACK_BOT_TOKEN")
channel_id = os.getenv("SLACK_CHANNEL_ID")

print(f"✓ Token exists: {bool(slack_token)}", flush=True)
print(f"✓ Channel ID exists: {bool(channel_id)}", flush=True)

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
        print(f"⚠️ Could not load alerted games: {e}", flush=True)
    return {}

def save_alerted_games(alerted_games):
    """Save alerted games to file"""
    try:
        with open(ALERTED_GAMES_FILE, 'wb') as f:
            pickle.dump(alerted_games, f)
        print(f"✅ Saved alerted games: {len(alerted_games)} games tracked", flush=True)
    except Exception as e:
        print(f"⚠️ Could not save alerted games: {e}", flush=True)

def load_last_summary_time():
    """Load timestamp of last summary sent"""
    try:
        if os.path.exists(LAST_SUMMARY_FILE):
            with open(LAST_SUMMARY_FILE, 'rb') as f:
                return pickle.load(f)
    except Exception as e:
        print(f"⚠️ Could not load last summary time: {e}", flush=True)
    return None

def save_last_summary_time(timestamp):
    """Save timestamp of last summary sent"""
    try:
        with open(LAST_SUMMARY_FILE, 'wb') as f:
            pickle.dump(timestamp, f)
    except Exception as e:
        print(f"⚠️ Could not save last summary time: {e}", flush=True)

def should_send_summary():
    """Check if enough time has passed since last summary"""
    from datetime import timedelta
    last_summary = load_last_summary_time()
    now = datetime.now()
    
    if last_summary is None:
        print(f"⏰ First summary - sending now", flush=True)
        return True
    
    time_since_last = now - last_summary
    should_send = time_since_last >= timedelta(minutes=SUMMARY_INTERVAL_MINUTES)
    
    if should_send:
        print(f"⏰ Summary interval elapsed ({SUMMARY_INTERVAL_MINUTES} min)", flush=True)
    else:
        remaining = SUMMARY_INTERVAL_MINUTES - int(time_since_last.total_seconds() / 60)
        print(f"⏰ Next summary in {remaining} minutes", flush=True)
    
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

def get_inning_arrow(state):
    """Return arrow based on inning state"""
    if state.lower() == 'top':
        return '⬆️'
    elif state.lower() == 'bottom':
        return '⬇️'
    else:
        return '↔️'

def send_9th_inning_alert(game, inning, state, status):
    """Send REAL-TIME Slack alert for 9th inning (in progress only)"""
    try:
        away_team = game.get('away_name', 'Away Team')
        home_team = game.get('home_name', 'Home Team')
        away_score = game.get('away_score', 0)
        home_score = game.get('home_score', 0)
        
        # Only send 9th inning alert (skip if game is final)
        if status in ['Final', 'Game Over']:
            print(f"Skipping alert - game already final", flush=True)
            return
        
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "🚨 9th Inning 🚨",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"{away_team} vs {home_team}"
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"{away_team}\n{away_score}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"{home_team}\n{home_score}"
                    }
                ]
            },
            {
                "type": "divider"
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"Inning:\n*9th* ({state})"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"Status:\nIn Progress"
                    }
                ]
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Updated {datetime.now().strftime('%I:%M %p EDT')}"
                    }
                ]
            }
        ]
        
        response = client.chat_postMessage(
            channel=channel_id,
            blocks=blocks
        )
        
        print(f"✅ 9th Inning alert sent!", flush=True)
    
    except SlackApiError as e:
        print(f"❌ Slack API error: {e}", flush=True)

def send_games_summary(final_games, in_progress_games):
    """Send PERIODIC (every 30 min) summary of all games with weather"""
    try:
        print(f"📊 Sending summary: {len(final_games)} final, {len(in_progress_games)} in progress", flush=True)
        
        if not final_games and not in_progress_games:
            print("⚠️ No games to summarize", flush=True)
            return
        
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "⚾ MLB Games Update",
                    "emoji": True
                }
            }
        ]
        
        # FINAL GAMES SECTION
        if final_games:
            final_lines = []
            for game in final_games:
                away_team = game.get('away_team', 'Away')
                home_team = game.get('home_team', 'Home')
                away_score = game.get('away_score', 0)
                home_score = game.get('home_score', 0)
                weather_emoji = get_weather_emoji(game.get('weather_conditions'))
                
                game_line = f"{away_team} ({away_score}) vs {home_team} ({home_score}) {weather_emoji}"
                final_lines.append(game_line)
            
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*FINAL*\n" + "\n".join(final_lines)
                }
            })
        
        # IN PROGRESS GAMES SECTION
        if in_progress_games:
            in_progress_lines = []
            for game in in_progress_games:
                inning_num = game.get('inning', 'N/A')
                arrow = get_inning_arrow(game.get('state', ''))
                away_team = game.get('away_team', 'Away')
                home_team = game.get('home_team', 'Home')
                away_score = game.get('away_score', 0)
                home_score = game.get('home_score', 0)
                weather_emoji = get_weather_emoji(game.get('weather_conditions'))
                delay_info = f" {game.get('delay_indicator')}" if game.get('delay_indicator') else ""
                
                game_line = f"*{inning_num}* {arrow} {away_team} ({away_score}) vs {home_team} ({home_score}) {weather_emoji}{delay_info}"
                in_progress_lines.append(game_line)
            
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*IN PROGRESS*\n" + "\n".join(in_progress_lines)
                }
            })
        
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"Summary updated {datetime.now().strftime('%I:%M %p EDT')} (30-min interval)"
                }
            ]
        })
        
        response = client.chat_postMessage(
            channel=channel_id,
            blocks=blocks
        )
        
        print(f"✅ PERIODIC summary sent!", flush=True)
    
    except SlackApiError as e:
        print(f"❌ Slack API error sending summary: {e}", flush=True)

def send_slack_alert_error(error_msg):
    """Send error alert to Slack"""
    try:
        client.chat_postMessage(
            channel=channel_id,
            blocks=[
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"❌ Error checking MLB games\n{error_msg}"
                    }
                }
            ]
        )
    except SlackApiError as e:
        print(f"❌ Failed to send error alert: {e}", flush=True)

def check_9th_inning_games():
    """Fetch MLB games and alert only when 9th inning is reached"""
    print("📋 Starting game check...", flush=True)
    try:
        # Load previously alerted games
        alerted_games = load_alerted_games()
        print(f"📋 Loaded {len(alerted_games)} previously alerted games", flush=True)
        
        # Get TODAY'S games
        today = str(date.today())
        print(f"📅 Checking games for: {today}", flush=True)
        
        schedule = statsapi.schedule(start_date=today, end_date=today)
        print(f"📅 Found {len(schedule)} total games", flush=True)
        
        if not schedule:
            print("No games found for today", flush=True)
            return
        
        print(f"\n{'='*80}", flush=True)
        print(f"MLB GAMES STATUS REPORT - {len(schedule)} games found for {today}", flush=True)
        print(f"{'='*80}\n", flush=True)
        
        # Filter for in-progress and final games
        active_games = [g for g in schedule if g['status'] in ['In Progress', 'Final', 'Game Over']]
        print(f"Active Games: {len(active_games)}\n", flush=True)
        
        if not active_games:
            print("No games currently in progress or final", flush=True)
            return
        
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
                
                print(f"📊 {away_team} @ {home_team} - {status}", flush=True)
                
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
                status_detail = game_data.get('gameData', {}).get('status', {}).get('detailedState', '')
                delay_indicator = get_delay_indicator(status_detail)
                
                print(f"   Inning: {current_inning} ({inning_state})", flush=True)
                
                # Check if game has reached 9th inning and hasn't been alerted yet
                if current_inning == 9 and game_pk not in alerted_games:
                    print(f"   ⚠️  9TH INNING ALERT TRIGGERED!", flush=True)
                    new_alerts.append({
                        'game': game,
                        'inning': current_inning,
                        'state': inning_state,
                        'status': status,
                        'weather_conditions': weather_conditions,
                        'weather_temp': weather_temp,
                        'wind_speed': wind_speed
                    })
                    # Mark as alerted
                    alerted_games[game_pk] = {
                        'alerted_at_inning': current_inning,
                        'away_team': away_team,
                        'home_team': home_team,
                        'alerted_timestamp': datetime.now().isoformat(),
                        'status_at_alert': status
                    }
                
                # Separate into in-progress and final
                game_info = {
                    'away_team': away_team,
                    'home_team': home_team,
                    'away_score': away_score,
                    'home_score': home_score,
                    'inning': current_inning,
                    'state': inning_state,
                    'status': status,
                    'weather_conditions': weather_conditions,
                    'weather_temp': weather_temp,
                    'wind_speed': wind_speed,
                    'delay_indicator': delay_indicator
                }
                
                if status in ['Final', 'Game Over']:
                    final_games.append(game_info)
                else:
                    in_progress_games.append(game_info)
            
            except Exception as game_error:
                print(f"   ⚠️ Error processing game: {game_error}", flush=True)
                continue
        
        # Save updated alerted games
        save_alerted_games(alerted_games)
        
        # Send REAL-TIME alerts for 9th inning ONLY
        print(f"\n📢 Processing {len(new_alerts)} new alerts...", flush=True)
        for alert in new_alerts:
            send_9th_inning_alert(alert['game'], alert['inning'], alert['state'], alert['status'])
        
        # Send SUMMARY only every 30 minutes
        print(f"\n📊 Checking if summary should be sent...", flush=True)
        if should_send_summary():
            send_games_summary(final_games, in_progress_games)
            save_last_summary_time(datetime.now())
        else:
            print("⏭️ Skipping summary (not yet time for periodic update)", flush=True)
        
        print(f"\n✅ Check complete!", flush=True)
    
    except Exception as e:
        print(f"❌ Error checking games: {e}", flush=True)
        import traceback
        traceback.print_exc()
        send_slack_alert_error(str(e))

if __name__ == "__main__":
    print("🎬 Script initialized", flush=True)
    check_9th_inning_games()
    print("🎬 Script finished", flush=True)
