import csv
import json

# Input and output file paths
tsv_file = '/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/rescues/NewHopeRescues_Full_Regions.tsv'
jsonl_file = '/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/rescues/NewHopeRescues_Full_Regions.jsonl'

# Define the column names
columns = ["name", "email", "website", "social", "animal_type", "location", "description"]

with open(tsv_file, 'r', encoding='utf-8') as tsv, open(jsonl_file, 'w', encoding='utf-8') as jsonl:
    reader = csv.reader(tsv, delimiter='\t')
    for row in reader:
        # Skip empty rows
        if not row:
            continue
        # Create a dictionary mapping column names to row values
        data = {col: val for col, val in zip(columns, row)}
        # Write as a JSON object on a single line
        jsonl.write(json.dumps(data) + '\n')

print(f"Converted {tsv_file} to {jsonl_file}")