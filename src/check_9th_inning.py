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
            
            print()
    
    except Exception as e:
        print(f"❌ Error checking games: {e}")
        send_slack_alert_error(str(e))

def send_slack_alert(game, inning, state, status):
    """Send Slack alert for 9th inning final game"""
    try:
        away_team = game.get('away_name', 'Away Team')
        home_team = game.get('home_name', 'Home Team')
        
        # Get score if available
        away_score = game.get('away_score', '?')
        home_score = game.get('home_score', '?')
        
        message = f"🚨 GAME FINAL - 9th INNING 🚨\n{away_team} ({away_score}) @ {home_team} ({home_score})"
        
        response = client.chat_postMessage(
            channel=channel_id,
            text=message,
            blocks=[
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"🚨 *GAME FINAL - 9TH INNING* 🚨\n*{away_team}* ({away_score}) @ *{home_team}* ({home_score})\nInning: {inning} ({state})\nStatus: {status}"
                    }
                }
            ]
        )
        
        print(f"✅ Slack alert sent!")
    
    except SlackApiError as e:
        print(f"❌ Slack API error: {e}")

def send_slack_alert_error(error_msg):
    """Send error alert to Slack"""
    try:
        client.chat_postMessage(
            channel=channel_id,
            text=f"❌ Error checking MLB games: {error_msg}"
        )
    except SlackApiError as e:
        print(f"❌ Failed to send error alert: {e}")

if __name__ == "__main__":
    check_9th_inning_games()
