import json


def extract_unique_dids(input_file, output_txt):
    unique_dids = set()

    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    data = json.loads(line)
                    # Access the list of interactors
                    interactors = data.get('interactors', [])

                    for person in interactors:
                        did = person.get('did')
                        if did:
                            unique_dids.add(did)

                except json.JSONDecodeError:
                    continue  # Skip malformed lines

        # Write the unique DIDs to a text file
        with open(output_txt, 'w', encoding='utf-8') as f_out:
            for did in sorted(unique_dids):  # Sorted makes it easier to read
                f_out.write(f"{did}\n")

        print(f"Extraction complete!")
        print(f"Found {len(unique_dids)} unique DIDs.")

    except FileNotFoundError:
        print("Error: The input file was not found.")


# Usage
extract_unique_dids('/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/v2/cleaned_output.jsonl', 'unique_dids.txt')