import os
import json
import statsapi
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from datetime import datetime, date, timedelta
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

def check_9th_inning_games():
    """Fetch MLB games, alert on 9th/final, send summary every 30 min"""
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
            game_pk = game['game_id']
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
            
            # Print game status
            print(f"📊 {away_team} @ {home_team}")
            print(f"   Status: {status}")
            print(f"   Inning: {current_inning} ({inning_state})")
            
            # Check if game has reached 9th inning and hasn't been alerted yet
            if current_inning == 9 and game_pk not in alerted_games:
                print(f"   ⚠️  9TH INNING ALERT TRIGGERED!")
                new_alerts.append({
                    'game': game,
                    'inning': current_inning,
                    'state': inning_state,
                    'status': status,
                    'alert_type': '9th_inning'
                })
                # Mark as alerted
                alerted_games[game_pk] = {
                    'alerted_at_inning': current_inning,
                    'away_team': away_team,
                    'home_team': home_team,
                    'alerted_timestamp': datetime.now().isoformat(),
                    'status_at_alert': status
                }
            elif game_pk in alerted_games:
                print(f"   ℹ️ Already alerted for this game")
            
            # Separate into in-progress and final
            game_info = {
                'away_team': away_team,
                'home_team': home_team,
                'away_score': away_score,
                'home_score': home_score,
                'inning': current_inning,
                'state': inning_state,
                'status': status
            }
            
            if status in ['Final', 'Game Over']:
                final_games.append(game_info)
            else:
                in_progress_games.append(game_info)
            
            print()
        
        # Save updated alerted games
        save_alerted_games(alerted_games)
        
        # Send REAL-TIME alerts for 9th inning/final
        for alert in new_alerts:
            send_9th_inning_alert(alert['game'], alert['inning'], alert['state'], alert['status'])
        
        # Send SUMMARY only every 30 minutes
        if should_send_summary():
            send_games_summary(final_games, in_progress_games)
            save_last_summary_time(datetime.now())
        else:
            print("⏭️ Skipping summary (not yet time for periodic update)")
    
    except Exception as e:
        print(f"❌ Error checking games: {e}")
        send_slack_alert_error(str(e))

def get_inning_arrow(state):
    """Return arrow based on inning state"""
    if state.lower() == 'top':
        return '⬆️'
    elif state.lower() == 'bottom':
        return '⬇️'
    else:
        return '↔️'

def send_9th_inning_alert(game, inning, state, status):
    """Send REAL-TIME Slack alert for 9th inning game"""
    try:
        away_team = game.get('away_name', 'Away Team')
        home_team = game.get('home_name', 'Home Team')
        away_score = game.get('away_score', 0)
        home_score = game.get('home_score', 0)
        
        is_final = status in ['Final', 'Game Over']
        
        if is_final:
            # FINAL GAME - All bold
            blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "🚨 FINAL 🚨",
                        "emoji": True
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*{away_team} vs {home_team}*"
                    }
                },
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": f"*{away_team}*\n*{away_score}*"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*{home_team}*\n*{home_score}*"
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
                            "text": f"*Inning:*\n*9th*"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Status:*\n*Final*"
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
        else:
            # 9TH INNING IN PROGRESS - Bold only 9th inning, rest normal
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
        
        print(f"✅ REAL-TIME alert sent!")
    
    except SlackApiError as e:
        print(f"❌ Slack API error: {e}")

def send_games_summary(final_games, in_progress_games):
    """Send PERIODIC (every 30 min) summary of all games"""
    try:
        if not final_games and not in_progress_games:
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
                away_team = game['away_team']
                home_team = game['home_team']
                away_score = game['away_score']
                home_score = game['home_score']
                
                game_line = f"{away_team} ({away_score}) vs {home_team} ({home_score})"
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
                inning_num = game['inning']
                arrow = get_inning_arrow(game['state'])
                away_team = game['away_team']
                home_team = game['home_team']
                away_score = game['away_score']
                home_score = game['home_score']
                
                game_line = f"*{inning_num}* {arrow} {away_team} ({away_score}) vs {home_team} ({home_score})"
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
        
        print(f"✅ PERIODIC summary sent!")
    
    except SlackApiError as e:
        print(f"❌ Slack API error sending summary: {e}")

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
        print(f"❌ Failed to send error alert: {e}")

if __name__ == "__main__":
    check_9th_inning_games()
