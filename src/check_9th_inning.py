import os
import json
import statsapi
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from datetime import datetime, date
import pickle

print("🚀 Script starting...", flush=True)

# Initialize Slack client
slack_token = os.getenv("SLACK_BOT_TOKEN")
channel_id = os.getenv("SLACK_CHANNEL_ID")

client = WebClient(token=slack_token)

ALERTED_GAMES_FILE = "alerted_games.pkl"
LAST_SUMMARY_FILE = "last_summary.pkl"
SUMMARY_INTERVAL_MINUTES = 30

def load_alerted_games():
    try:
        if os.path.exists(ALERTED_GAMES_FILE):
            with open(ALERTED_GAMES_FILE, 'rb') as f:
                return pickle.load(f)
    except Exception as e:
        print(f"⚠️ Load error: {e}", flush=True)
    return {}

def save_alerted_games(alerted_games):
    try:
        with open(ALERTED_GAMES_FILE, 'wb') as f:
            pickle.dump(alerted_games, f)
        print(f"✅ Saved {len(alerted_games)} alerted games", flush=True)
    except Exception as e:
        print(f"⚠️ Save error: {e}", flush=True)

def load_last_summary_time():
    try:
        if os.path.exists(LAST_SUMMARY_FILE):
            with open(LAST_SUMMARY_FILE, 'rb') as f:
                return pickle.load(f)
    except Exception as e:
        print(f"⚠️ Load summary error: {e}", flush=True)
    return None

def save_last_summary_time(timestamp):
    try:
        with open(LAST_SUMMARY_FILE, 'wb') as f:
            pickle.dump(timestamp, f)
    except Exception as e:
        print(f"⚠️ Save summary error: {e}", flush=True)

def should_send_summary():
    from datetime import timedelta
    last_summary = load_last_summary_time()
    now = datetime.now()
    
    if last_summary is None:
        print(f"⏰ First summary - sending now", flush=True)
        return True
    
    time_since_last = now - last_summary
    should_send = time_since_last >= timedelta(minutes=SUMMARY_INTERVAL_MINUTES)
    
    if should_send:
        print(f"⏰ Summary interval elapsed", flush=True)
    else:
        remaining = SUMMARY_INTERVAL_MINUTES - int(time_since_last.total_seconds() / 60)
        print(f"⏰ Next summary in {remaining} min", flush=True)
    
    return should_send

def get_weather_emoji(conditions):
    if not conditions:
        return "🌤️"
    conditions = str(conditions).lower()
    if 'rain' in conditions:
        return "🌧️"
    elif 'cloud' in conditions:
        return "☁️"
    elif 'clear' in conditions or 'sunny' in conditions:
        return "☀️"
    elif 'wind' in conditions:
        return "💨"
    elif 'snow' in conditions:
        return "❄️"
    return "🌤️"

def get_delay_indicator(status_detail):
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
    state = str(state).lower()
    if 'top' in state:
        return '⬆️'
    elif 'bottom' in state:
        return '⬇️'
    return '↔️'

def send_9th_inning_alert(away_team, home_team, away_score, home_score, inning_state):
    try:
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
                        "text": f"Inning:\n*9th* ({inning_state})"
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
        
        client.chat_postMessage(channel=channel_id, blocks=blocks)
        print(f"✅ 9th Inning alert sent!", flush=True)
    
    except Exception as e:
        print(f"❌ Alert error: {e}", flush=True)

def send_games_summary(final_games, in_progress_games):
    try:
        print(f"📊 Sending: {len(final_games)} final, {len(in_progress_games)} in progress", flush=True)
        
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
        
        if final_games:
            final_lines = [f"{g['away']} ({g['away_score']}) vs {g['home']} ({g['home_score']}) {get_weather_emoji(g['weather'])}" for g in final_games]
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*FINAL*\n" + "\n".join(final_lines)
                }
            })
        
        if in_progress_games:
            in_progress_lines = []
            for g in in_progress_games:
                arrow = get_inning_arrow(g['state'])
                delay = f" {g['delay']}" if g['delay'] else ""
                line = f"*{g['inning']}* {arrow} {g['away']} ({g['away_score']}) vs {g['home']} ({g['home_score']}) {get_weather_emoji(g['weather'])}{delay}"
                in_progress_lines.append(line)
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
                    "text": f"Summary updated {datetime.now().strftime('%I:%M %p EDT')}"
                }
            ]
        })
        
        client.chat_postMessage(channel=channel_id, blocks=blocks)
        print(f"✅ Summary sent!", flush=True)
    
    except Exception as e:
        print(f"❌ Summary error: {e}", flush=True)

def check_9th_inning_games():
    print("📋 Starting check...", flush=True)
    try:
        alerted_games = load_alerted_games()
        today = str(date.today())
        print(f"📅 Date: {today}", flush=True)
        
        schedule = statsapi.schedule(start_date=today, end_date=today)
        print(f"📅 Total games: {len(schedule)}", flush=True)
        
        active_games = [g for g in schedule if g['status'] in ['In Progress', 'Final', 'Game Over']]
        print(f"📊 Active games: {len(active_games)}", flush=True)
        
        if not active_games:
            print("No active games", flush=True)
            return
        
        in_progress = []
        final = []
        new_alerts = []
        
        for game in active_games:
            try:
                game_id = game['game_id']
                away = game['away_name']
                home = game['home_name']
                status = game['status']
                away_score = game['away_score']
                home_score = game['home_score']
                
                print(f"📊 {away} @ {home}", flush=True)
                
                # Get detailed info
                game_data = statsapi.get('game', {'gamePk': game_id})
                linescore = game_data.get('liveData', {}).get('linescore', {})
                inning = linescore.get('currentInning', 'N/A')
                inning_state = linescore.get('inningState', 'Unknown')
                
                weather_data = game_data.get('gameData', {}).get('weather', {})
                weather = weather_data.get('condition', 'Unknown')
                
                status_detail = game_data.get('gameData', {}).get('status', {}).get('detailedState', '')
                delay = get_delay_indicator(status_detail)
                
                print(f"   Inning: {inning} ({inning_state})", flush=True)
                
                # Check for 9th inning alert
                if inning == 9 and game_id not in alerted_games and status == 'In Progress':
                    print(f"   ⚠️ 9TH INNING!", flush=True)
                    new_alerts.append((away, home, away_score, home_score, inning_state))
                    alerted_games[game_id] = True
                
                # Add to summary
                game_info = {
                    'away': away,
                    'home': home,
                    'away_score': away_score,
                    'home_score': home_score,
                    'inning': inning,
                    'state': inning_state,
                    'weather': weather,
                    'delay': delay
                }
                
                if status in ['Final', 'Game Over']:
                    final.append(game_info)
                else:
                    in_progress.append(game_info)
            
            except Exception as e:
                print(f"   Error: {e}", flush=True)
                continue
        
        save_alerted_games(alerted_games)
        
        # Send alerts
        for away, home, away_score, home_score, inning_state in new_alerts:
            send_9th_inning_alert(away, home, away_score, home_score, inning_state)
        
        # Send summary
        if should_send_summary():
            if final or in_progress:
                send_games_summary(final, in_progress)
                save_last_summary_time(datetime.now())
            else:
                print("⚠️ No games to summarize", flush=True)
        
        print(f"✅ Check complete!", flush=True)
    
    except Exception as e:
        print(f"❌ Error: {e}", flush=True)
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_9th_inning_games()
