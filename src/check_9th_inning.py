def send_9th_inning_alert(game, inning, state, status):
    """Send REAL-TIME Slack alert for 9th inning (in progress only)"""
    try:
        away_team = game.get('away_name', 'Away Team')
        home_team = game.get('home_name', 'Home Team')
        away_score = game.get('away_score', 0)
        home_score = game.get('home_score', 0)
        
        # Only send 9th inning alert (skip if game is final)
        if status in ['Final', 'Game Over']:
            print(f"Skipping alert - game already final")
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
        
        print(f"✅ 9th Inning alert sent!")
    
    except SlackApiError as e:
        print(f"❌ Slack API error: {e}")
