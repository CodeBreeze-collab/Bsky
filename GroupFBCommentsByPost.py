import json
import pandas as pd


def process_foster_leads(input_path, output_path='qualified_leads-2.csv'):
    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Keywords that indicate a higher likelihood of fostering/interest
    high_intent_keywords = ['foster', 'application', 'apply', 'info', 'email', 'space', 'home', 'take']

    processed_leads = []

    for item in data:
        comment_text = item.get('text', '')
        if not comment_text:
            continue

        # Determine if it's a high-priority lead
        is_high_priority = any(word in comment_text.lower() for word in high_intent_keywords)

        processed_leads.append({
            'User Comment': comment_text.strip(),
            'Post URL': item.get('facebookUrl'),
            'High Priority': is_high_priority,
            'Post Subject': item.get('postTitle', '').split('\n')[0]  # Get just the name/headline
        })

    # Convert to Dataframe for easy sorting
    df = pd.DataFrame(processed_leads)

    # Sort so high priority leads are at the top
    df = df.sort_values(by='High Priority', ascending=False)

    df.to_csv(output_path, index=False)
    print(f"Extraction complete. {len(df)} comments processed.")
    print(f"High-priority leads found: {df['High Priority'].sum()}")


# Run it on your final dataset
process_foster_leads('/Users/hdon/Downloads/dataset_facebook-comments-scraper_2026-04-23_05-11-28-802.json')