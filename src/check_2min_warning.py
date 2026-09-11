# v2: NFL Final 2 Minutes Monitor - Fixed date filtering and time window
import os
import requests
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from datetime import datetime, date, timezone, timedelta
import pickle

print("🚀 NFL Script starting...", flush=True)

# Initialize Slack client
slack_token = os.getenv("SLACK_BOT_TOKEN")
channel_id = os.getenv("SLACK_CHANNEL_ID")

client = WebClient(token=slack_token)

ALERTED_GAMES_FILE = "alerted_games_nfl.pkl"

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

def parse_time_remaining(status_text):
    """Extract time remaining from status text (e.g., '2:00' or '0:30')"""
    try:
        if not status_text:
            return None, None
        
        status_text = str(status_text).strip()
        
        # Look for time format MM:SS or M:SS
        if ':' in status_text:
            time_part = status_text.split()[0]
            parts = time_part.split(':')
            if len(parts) == 2:
                try:
                    minutes = int(parts[0])
                    seconds = int(parts[1])
                    total_seconds = minutes * 60 + seconds
                    return time_part, total_seconds
                except:
                    return None, None
        
        return None, None
    except Exception as e:
        print(f"⚠️ Error parsing time: {e}", flush=True)
        return None, None

def is_final_2min(status_text, quarter):
    """Check if game is in final ~3 minutes of 4th quarter (more lenient window)"""
    try:
        if quarter != 4:
            return False
        
        if not status_text:
            return False
        
        time_str, total_seconds = parse_time_remaining(status_text)
        
        if total_seconds is None:
            return False
        
        # Final 3 minutes window (180 seconds) to catch more games
        # This prevents missing alerts due to script timing
        if 0 <= total_seconds <= 180:
            return True
        
        return False
    except Exception as e:
        print(f"⚠️ Error checking final 2min: {e}", flush=True)
        return False

def send_final_2min_alert(away_team, home_team, away_score, home_score, time_remaining, final_games, in_progress_games):
    try:
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "🚨 Final 2 Minutes 🚨",
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
                        "text": f"Quarter:\n*4th*"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"Time Remaining:\n*{time_remaining}*"
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
                line = f"🏈 *Q{g['quarter']}* *{g['away']}* ({g['away_score']}) vs *{g['home']}* ({g['home_score']}) {get_weather_emoji(g['weather'])}{status_ind}"
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
        print(f"✅ Final 2 Minutes alert sent for {away_team} vs {home_team}!", flush=True)
    
    except Exception as e:
        print(f"❌ Alert error: {e}", flush=True)

def get_nfl_games():
    """Fetch NFL games from ESPN API"""
    print("📡 Fetching NFL games from ESPN API...", flush=True)
    try:
        url = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        events = data.get('events', [])
        print(f"✅ ESPN API response received: {len(events)} total events (all weeks)", flush=True)
        return events
    except Exception as e:
        print(f"❌ Failed to fetch NFL games: {e}", flush=True)
        return []

def filter_todays_games(events):
    """Filter events to only include today's games"""
    # Get today's date in EDT
    edt = timezone(timedelta(hours=-4))
    today_date = datetime.now(tz=edt).date()
    today_str = today_date.strftime('%Y-%m-%d')
    
    today_games = []
    for event in events:
        try:
            event_date_str = event.get('date', '')
            # Event date format: "2026-09-10T20:20Z" - extract just the date part
            if event_date_str.startswith(today_str):
                today_games.append(event)
                print(f"   ✅ Found today's game: {event_date_str}", flush=True)
            else:
                print(f"   ⏭️  Skipping future game: {event_date_str}", flush=True)
        except Exception as e:
            print(f"   ⚠️  Error filtering game: {e}", flush=True)
            continue
    
    return today_games

def check_final_2min_games():
    print("📋 Starting NFL check...", flush=True)
    try:
        alerted_games = load_alerted_games()
        
        # Get today's date in EDT (UTC-4)
        edt = timezone(timedelta(hours=-4))
        today_date = datetime.now(tz=edt).date()
        today = str(today_date)
        
        print(f"📅 Date: {today}", flush=True)
        
        all_events = get_nfl_games()
        print(f"📊 Total events from API: {len(all_events)}", flush=True)
        
        # Filter to only today's games
        events = filter_todays_games(all_events)
        print(f"📊 Today's games: {len(events)}", flush=True)
        
        if not events:
            print("ℹ️ No NFL games today", flush=True)
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
                
                # Get quarter
                quarter = 0
                if status_detail:
                    try:
                        if 'Q' in status_detail:
                            quarter_str = status_detail.split('Q')[1].split(',')[0].strip()
                            quarter = int(quarter_str)
                    except:
                        quarter = 0
                
                # Get time remaining
                time_remaining, total_seconds = parse_time_remaining(status_detail)
                
                # Get status indicator
                status_indicator = get_status_indicator(status_detail)
                
                print(f"📊 {away_team} @ {home_team} (Status: {status_type}, Q{quarter}, {status_detail})", flush=True)
                
                # Check for final 2 minutes
                if is_final_2min(status_detail, quarter) and status_type == 'STATUS_IN_PROGRESS':
                    alert_key = f"{event_id}_final2min"
                    
                    if alert_key not in alerted_games:
                        print(f"   ⚠️ FINAL 2 MINUTES ALERT! ({time_remaining} remaining)", flush=True)
                        new_alerts.append((away_team, home_team, away_score, home_score, time_remaining))
                        alerted_games[alert_key] = True
                    else:
                        print(f"   ℹ️ Already alerted for this game", flush=True)
                
                # Build game info
                game_info = {
                    'away': away_team,
                    'home': home_team,
                    'away_score': away_score,
                    'home_score': home_score,
                    'quarter': quarter if quarter > 0 else 'N/A',
                    'time': time_remaining if time_remaining else 'N/A',
                    'weather': '🌤️',
                    'status': status_indicator
                }
                
                # Categorize by status
                if status_type in ['STATUS_FINAL', 'STATUS_FINAL_OT']:
                    final_games.append(game_info)
                    print(f"   → Added to FINAL games", flush=True)
                elif status_type == 'STATUS_IN_PROGRESS':
                    in_progress_games.append(game_info)
                    print(f"   → Added to IN PROGRESS games", flush=True)
                elif status_indicator:
                    game_info['quarter'] = status_indicator
                    in_progress_games.append(game_info)
                    print(f"   → Added to IN PROGRESS (delayed)", flush=True)
            
            except Exception as e:
                print(f"   ❌ Error: {e}", flush=True)
                import traceback
                traceback.print_exc()
                continue
        
        save_alerted_games(alerted_games)
        
        # ONLY send alerts - nothing else
        if new_alerts:
            print(f"🏈 Sending {len(new_alerts)} final 2-minute alerts", flush=True)
            for away, home, away_score, home_score, time_rem in new_alerts:
                send_final_2min_alert(away, home, away_score, home_score, time_rem, final_games, in_progress_games)
        else:
            print(f"ℹ️ No new final 2-minute alerts - no Slack message sent", flush=True)
        
        print(f"✅ NFL check complete!", flush=True)
    
    except Exception as e:
        print(f"❌ Error: {e}", flush=True)
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_final_2min_games()
