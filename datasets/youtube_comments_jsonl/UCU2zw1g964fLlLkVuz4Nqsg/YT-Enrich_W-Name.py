import csv
from googleapiclient.discovery import build

# Configuration
API_KEY = "AIzaSyB6m8GdgJpdra56s8wjs-coi_9NKU6DNrE"
INPUT_FILE = 'commenter_video_counts_UCU2zw1g964fLlLkVuz4Nqsg_w-handle.csv'
OUTPUT_FILE = 'commenter_video_counts_enriched.csv'

def get_channel_names(channel_ids):
    youtube = build('youtube', 'v3', developerKey=API_KEY)
    names = {}
    # The API allows batching up to 50 IDs per request
    for i in range(0, len(channel_ids), 50):
        batch = channel_ids[i:i+50]
        response = youtube.channels().list(part="snippet", id=",".join(batch)).execute()
        for item in response.get('items', []):
            names[item['id']] = item['snippet']['title']
    return names

# Read current CSV
ids_to_lookup = []
rows = []
with open(INPUT_FILE, 'r') as f:
    reader = csv.DictReader(f)
    for row in reader:
        ids_to_lookup.append(row['commenter_id'])
        rows.append(row)

# Fetch names
channel_names = get_channel_names(ids_to_lookup)

# Write enriched CSV
with open(OUTPUT_FILE, 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['commenter_id', 'channel_name', 'channel_url', 'unique_video_count'])
    for row in rows:
        name = channel_names.get(row['commenter_id'], 'Unknown')
        writer.writerow([row['commenter_id'], name, row['channel_url'], row['unique_video_count']])

print("Enrichment complete.")