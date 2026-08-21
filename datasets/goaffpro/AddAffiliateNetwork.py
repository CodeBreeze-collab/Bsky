import json


def update_jsonl(input_filename, output_filename):
    with open(input_filename, 'r', encoding='utf-8') as infile, \
            open(output_filename, 'w', encoding='utf-8') as outfile:

        for line in infile:
            # Skip empty lines
            if not line.strip():
                continue

            # Parse the JSON string into a Python dictionary
            data = json.loads(line)

            # Check if 'source_file' exists and contains 'goaffpro'
            if 'source_file' in data and 'goaffpro' in data['source_file']:
                data['affiliate_network'] = 'goaffpro'

            # Convert the dictionary back to a JSON string and write to the new file
            outfile.write(json.dumps(data) + '\n')

    print(f"Successfully processed {input_filename} and saved to {output_filename}")


# --- Example Usage ---
# Replace 'input.jsonl' and 'output.jsonl' with your actual file names
input_file = '/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/goaffpro/stores-consolidated-categories.jsonl'
output_file = '/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/goaffpro/stores-consolidated-categories-aff-network.jsonl'

update_jsonl(input_file, output_file)