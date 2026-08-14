import os
import json
import statsapi
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from datetime import datetime

# Initialize Slack client
slack_token = os.getenv("SLACK_BOT_TOKEN")
channel_id = os.getenv("SLACK_CHANNEL_ID")
client = WebClient(token=slack_token)

# Track alerted games in this run
alerted_games = set()

def check_9th_inning_games():
    """Fetch MLB games and display all innings, alert only for 9th inning finals"""
    try:
        # Get today's games
        schedule = statsapi.schedule(start_date="2026-08-14", end_date="2026-08-14")
        
        if not schedule:
            print("No games found for today")
            return
        
        print(f"\n{'='*80}")
        print(f"MLB GAMES STATUS REPORT - {len(schedule)} games found")
        print(f"{'='*80}\n")
        
        # Filter for in-progress and final games
        active_games = [g for g in schedule if g['status'] in ['In Progress', 'Final', 'Game Over']]
        
        if not active_games:
            print("No games currently in progress or final")
            return
        
        print(f"Active Games: {len(active_games)}\n")
        
        # Check each game
        for game in active_games:
            game_pk = game['game_id']
            away_team = game.get('away_name', 'Away Team')
            home_team = game.get('home_name', 'Home Team')
            status = game.get('status', 'Unknown')
            
            # Get detailed game info
            game_data = statsapi.get('game', {'gamePk': game_pk})
            linescore = game_data.get('liveData', {}).get('linescore', {})
            
            current_inning = linescore.get('currentInning', 'N/A')
            inning_state = linescore.get('inningState', 'Unknown')
            
            # Print game status
            print(f"📊 {away_team} @ {home_team}")
            print(f"   Status: {status}")
            print(f"   Inning: {current_inning} ({inning_state})")
            
            # Check for alert conditions: 9th inning AND (Final or Game Over)
            if current_inning == 9 and status in ['Final', 'Game Over']:
                if game_pk not in alerted_games:
                    print(f"   ⚠️  ALERT TRIGGERED!")
                    send_slack_alert(game, current_inning, inning_state, status)
                    alerted_games.add(game_pk)
            elif current_inning == 9 and status == 'In Progress':
                # Also alert for games in 9th inning but still in progress
                if game_pk not in alerted_games:
                    print(f"   ⚠️  ALERT TRIGGERED! (9TH INNING IN PROGRESS)")
                    send_slack_alert(game, current_inning, inning_state, status)
                    alerted_games.add(game_pk)
            
            print()
    
    except Exception as e:
        print(f"❌ Error checking games: {e}")
        send_slack_alert_error(str(e))

def send_slack_alert(game, inning, state, status):
    """Send Slack alert for 9th inning game"""
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
                            "text": f"Updated {datetime.now().strftime('%I:%M %p')}"
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
                            "text": f"Updated {datetime.now().strftime('%I:%M %p')}"
                        }
                    ]
                }
            ]
        
        response = client.chat_postMessage(
            channel=channel_id,
            blocks=blocks
        )
        
        print(f"✅ Slack alert sent!")
    
    except SlackApiError as e:
        print(f"❌ Slack API error: {e}")

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
