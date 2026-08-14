import os
import json
import statsapi
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# Initialize Slack client
slack_token = os.getenv("SLACK_BOT_TOKEN")
channel_id = os.getenv("SLACK_CHANNEL_ID")
client = WebClient(token=slack_token)

# Track alerted games in this run
alerted_games = set()

def check_9th_inning_games():
    """Fetch MLB games and alert if any are in 9th inning"""
    try:
        # Get today's games
        schedule = statsapi.schedule(start_date="2026-08-14", end_date="2026-08-14")
        
        if not schedule:
            print("No games found for today")
            return
        
        # Filter for in-progress games
        in_progress = [g for g in schedule if g['status'] == 'In Progress']
        
        if not in_progress:
            print("No games currently in progress")
            return
        
        print(f"Found {len(in_progress)} games in progress")
        
        # Check each game for 9th inning
        for game in in_progress:
            game_pk = game['game_id']
            
            # Skip if we already alerted for this game
            if game_pk in alerted_games:
                continue
            
            # Get detailed game info
            game_data = statsapi.get('game', {'gamePk': game_pk})
            linescore = game_data.get('liveData', {}).get('linescore', {})
            
            current_inning = linescore.get('currentInning')
            inning_state = linescore.get('inningState', 'Unknown')
            
            print(f"Game {game_pk}: Inning {current_inning}, State: {inning_state}")
            
            # Alert if 9th inning
            if current_inning == 9:
                send_slack_alert(game, current_inning, inning_state)
                alerted_games.add(game_pk)
    
    except Exception as e:
        print(f"Error checking games: {e}")
        send_slack_alert_error(str(e))

def send_slack_alert(game, inning, state):
    """Send Slack alert for 9th inning game"""
    try:
        away_team = game.get('away_name', 'Away Team')
        home_team = game.get('home_name', 'Home Team')
        
        message = f"🚨 **9th INNING ALERT** 🚨\n{away_team} @ {home_team}\nInning: {inning} ({state})"
        
        response = client.chat_postMessage(
            channel=channel_id,
            text=message,
            blocks=[
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"🚨 *9th INNING ALERT* 🚨\n*{away_team}* @ *{home_team}*\nInning: {inning} ({state})"
                    }
                }
            ]
        )
        
        print(f"Slack alert sent for {away_team} @ {home_team}")
    
    except SlackApiError as e:
        print(f"Slack API error: {e}")

def send_slack_alert_error(error_msg):
    """Send error alert to Slack"""
    try:
        client.chat_postMessage(
            channel=channel_id,
            text=f"❌ Error checking MLB games: {error_msg}"
        )
    except SlackApiError as e:
        print(f"Failed to send error alert: {e}")

if __name__ == "__main__":
    check_9th_inning_games()
