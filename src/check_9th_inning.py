import os
import requests
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from datetime import datetime, date
import pickle

print("🚀 MLS Script starting...", flush=True)

# Initialize Slack client
slack_token = os.getenv("SLACK_BOT_TOKEN")
channel_id = os.getenv("SLACK_CHANNEL_ID")

client = WebClient(token=slack_token)

ALERTED_GAMES_FILE = "alerted_games_mls.pkl"

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

def get_status_indicator(status_detail):
    """Get status indicator for delayed/postponed games"""
    if not status_detail:
        return None
    status_lower = str(status_detail).lower()
    if 'delay' in status_lower:
        return "⏸️ DELAYED"
    elif 'postponed' in status_lower:
        return "❌ POSTPONED"
    elif 'suspended' in status_lower:
        return "🛑 SUSPENDED"
    return None

def send_90th_minute_alert(away_team, home_team, away_score, home_score, minute, stoppage_time, final_games, in_progress_games):
    try:
        stoppage_display = f"+{stoppage_time}'" if stoppage_time else ""
        
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "🚨 90th Minute 🚨",
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
                        "text": f"Minute:\n*{minute}'* {stoppage_display}"
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
                status_ind = f" {g['status']}" if g['status'] else ""
                line = f"⚽ *{g['minute']}'* *{g['away']}* ({g['away_score']}) vs *{g['home']}* ({g['home_score']}) {get_weather_emoji(g['weather'])}{status_ind}"
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
        print(f"✅ 90th Minute alert sent for {away_team} vs {home_team}!", flush=True)
    
    except Exception as e:
        print(f"❌ Alert error: {e}", flush=True)

def get_mls_games():
    """Fetch today's MLS games from ESPN API"""
    print("📡 Fetching MLS games from ESPN API...", flush=True)
    try:
        # ESPN MLS scoreboard endpoint
        url = "https://site.api.espn.com/apis/site/v2/sports/soccer/mls/scoreboard"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        events = data.get('events', [])
        print(f"✅ ESPN API response received: {len(events)} events", flush=True)
        return events
    except Exception as e:
        print(f"❌ Failed to fetch MLS games: {e}", flush=True)
        return []

def parse_minute(status_text):
    """Extract minute from status text"""
    try:
        if not status_text:
            return 0
        
        status_lower = str(status_text).lower()
        
        # Look for minute indicator
        if "'" in status_text:
            minute_str = status_text.split("'")[0].strip()
            return int(minute_str)
        
        return 0
    except Exception as e:
        print(f"⚠️ Error parsing minute: {e}", flush=True)
        return 0

def check_90th_minute_games():
    print("📋 Starting MLS check...", flush=True)
    try:
        alerted_games = load_alerted_games()
        today = str(date.today())
        print(f"📅 Date: {today}", flush=True)
        
        events = get_mls_games()
        print(f"📊 Total events: {len(events)}", flush=True)
        
        if not events:
            print("ℹ️ No MLS games found", flush=True)
            return
        
        new_alerts = []
        final_games = []
        in_progress_games = []
        
        for event in events:
            try:
                event_id = event.get('id', '')
                
                # Get competitors (teams)
                competitors = event.get('competitors', [])
                if len(competitors) < 2:
                    continue
                
                away_team = competitors[1].get('team', {}).get('displayName', 'Unknown')
                home_team = competitors[0].get('team', {}).get('displayName', 'Unknown')
                away_score = competitors[1].get('score', 0)
                home_score = competitors[0].get('score', 0)
                
                # Get status
                status = event.get('status', {})
                status_type = status.get('type', '')
                status_detail = status.get('details', '')
                
                # Parse minute
                minute = parse_minute(status_detail)
                
                # Get stoppage time (usually displayed as "+X")
                stoppage_time = 0
                if '+' in str(status_detail):
                    try:
                        stoppage_str = str(status_detail).split('+')[1].split("'")[0].strip()
                        stoppage_time = int(stoppage_str)
                    except:
                        stoppage_time = 0
                
                # Get status indicator (delayed/postponed)
                status_indicator = get_status_indicator(status_detail)
                
                print(f"📊 {away_team} @ {home_team} (Status: {status_type}, Minute: {minute})", flush=True)
                
                # Check for 90th minute alert
                if minute == 90 and status_type == 'STATUS_IN_PROGRESS':
                    alert_key = f"{event_id}_90th"
                    
                    if alert_key not in alerted_games:
                        print(f"   ⚠️ 90TH MINUTE ALERT!", flush=True)
                        new_alerts.append((away_team, home_team, away_score, home_score, minute, stoppage_time))
                        alerted_games[alert_key] = True
                    else:
                        print(f"   ℹ️ Already alerted for 90th minute", flush=True)
                
                # Build game info
                game_info = {
                    'away': away_team,
                    'home': home_team,
                    'away_score': away_score,
                    'home_score': home_score,
                    'minute': minute if minute > 0 else 'N/A',
                    'weather': '🌤️',  # Default weather
                    'status': status_indicator
                }
                
                # Categorize by status
                if status_type in ['STATUS_FINAL', 'STATUS_FINAL_PEN']:
                    final_games.append(game_info)
                elif status_type == 'STATUS_IN_PROGRESS':
                    in_progress_games.append(game_info)
                elif status_indicator:  # Delayed/Postponed
                    game_info['minute'] = status_indicator
                    in_progress_games.append(game_info)
            
            except Exception as e:
                print(f"   ❌ Error: {e}", flush=True)
                import traceback
                traceback.print_exc()
                continue
        
        save_alerted_games(alerted_games)
        
        # ONLY send alerts - nothing else
        if new_alerts:
            print(f"⚽ Sending {len(new_alerts)} 90th minute alerts", flush=True)
            for away, home, away_score, home_score, minute, stoppage in new_alerts:
                send_90th_minute_alert(away, home, away_score, home_score, minute, stoppage, final_games, in_progress_games)
        else:
            print(f"ℹ️ No new 90th minute alerts - no Slack message sent", flush=True)
        
        print(f"✅ MLS check complete!", flush=True)
    
    except Exception as e:
        print(f"❌ Error: {e}", flush=True)
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_90th_minute_games()
