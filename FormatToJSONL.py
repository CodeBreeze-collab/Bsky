import json


def fix_jsonl_format(input_file, output_file):
    count = 0
    with open(input_file, 'r', encoding='utf-8') as f_in, \
            open(output_file, 'w', encoding='utf-8') as f_out:

        for line_number, line in enumerate(f_in, 1):
            line = line.strip()
            if not line:
                continue  # Skip empty lines

            try:
                # Validate that this line is actually valid JSON
                data = json.loads(line)

                # Write it out as a single compact line
                json.dump(data, f_out)
                f_out.write('\n')
                count += 1

            except json.JSONDecodeError as e:
                print(f"Skipping line {line_number} due to error: {e}")

    print(f"Process complete. Processed {count} valid JSON lines.")


# Run the fix
fix_jsonl_format('/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/v2/profile_audits/interactions.jsonl', 'cleaned_output.jsonl')