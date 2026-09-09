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
    elif 'postponed' in status_detail:
        return "❌ POSTPONED"
    return None

def get_inning_arrow(state):
    state = str(state).lower()
    if 'top' in state:
        return '⬆️'
    elif 'bottom' in state:
        return '⬇️'
    return '↔️'

def send_9th_inning_alert(away_team, home_team, away_score, home_score, inning_state, final_games, in_progress_games):
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
            }
        ]
        
        # Add Final games section
        if final_games:
            final_lines = [f"✅ *{g['away']}* ({g['away_score']}) vs *{g['home']}* ({g['home_score']}) {get_weather_emoji(g['weather'])}" for g in final_games]
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*FINAL*\n" + "\n".join(final_lines)
                }
            })
        
        # Add In Progress games section
        if in_progress_games:
            in_progress_lines = []
            for g in in_progress_games:
                arrow = get_inning_arrow(g['state'])
                status_ind = f" {g['status']}" if g['status'] else ""
                line = f"⚾ *{g['inning']}* {arrow} *{g['away']}* ({g['away_score']}) vs *{g['home']}* ({g['home_score']}) {get_weather_emoji(g['weather'])}{status_ind}"
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
                    "text": f"Updated {datetime.now().strftime('%I:%M %p EDT')}"
                }
            ]
        })
        
        client.chat_postMessage(channel=channel_id, blocks=blocks)
        print(f"✅ 9th Inning alert sent for {away_team} @ {home_team}!", flush=True)
    
    except Exception as e:
        print(f"❌ Alert error: {e}", flush=True)

def check_9th_inning_games():
    print("📋 Starting check...", flush=True)
    try:
        alerted_games = load_alerted_games()
        today = str(date.today())
        print(f"📅 Date: {today}", flush=True)
        
        schedule = statsapi.schedule(start_date=today, end_date=today)
        print(f"📅 Total games: {len(schedule)}", flush=True)
        
        # Include all active statuses
        active_games = [g for g in schedule if g['status'] in ['In Progress', 'Final', 'Game Over', 'Live', 'Delayed', 'Pre-Game', 'Postponed', 'Suspended']]
        print(f"📊 Active games: {len(active_games)}", flush=True)
        
        if not active_games:
            print("ℹ️ No active games", flush=True)
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
                
                print(f"📊 {away} @ {home} (Status: {status})", flush=True)
                
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
                if inning == 9 and status in ['In Progress', 'Live', 'Delayed']:
                    alert_key = f"{game_id}_9th"
                    
                    if alert_key not in alerted_games:
                        print(f"   ⚠️ 9TH INNING ALERT!", flush=True)
                        new_alerts.append((away, home, away_score, home_score, inning_state))
                        alerted_games[alert_key] = True
                    else:
                        print(f"   ℹ️ Already alerted for 9th inning", flush=True)
                
                # Build game info
                game_info = {
                    'away': away,
                    'home': home,
                    'away_score': away_score,
                    'home_score': home_score,
                    'inning': inning if inning != 'N/A' else delay if delay else 'N/A',
                    'state': inning_state,
                    'weather': weather,
                    'status': delay
                }
                
                # Categorize by status
                if status in ['Final', 'Game Over']:
                    final.append(game_info)
                elif status in ['Postponed', 'Suspended']:
                    game_info['inning'] = delay if delay else status
                    in_progress.append(game_info)
                else:
                    in_progress.append(game_info)
            
            except Exception as e:
                print(f"   ❌ Error: {e}", flush=True)
                import traceback
                traceback.print_exc()
                continue
        
        save_alerted_games(alerted_games)
        
        # ONLY send alerts - nothing else
        if new_alerts:
            print(f"📊 Sending {len(new_alerts)} 9th inning alerts", flush=True)
            for away, home, away_score, home_score, inning_state in new_alerts:
                send_9th_inning_alert(away, home, away_score, home_score, inning_state, final, in_progress)
        else:
            print(f"ℹ️ No new 9th inning alerts - no Slack message sent", flush=True)
        
        print(f"✅ Check complete!", flush=True)
    
    except Exception as e:
        print(f"❌ Error: {e}", flush=True)
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_9th_inning_games()
