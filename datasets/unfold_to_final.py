import json


def unfold_to_final_jsonl(input_json_path, output_jsonl_path):
    with open(input_json_path, 'r', encoding='utf-8') as f:
        consolidated_data = json.load(f)

    with open(output_jsonl_path, 'w', encoding='utf-8') as f_out:
        for animal in consolidated_data:
            # Extract the "Final" parameters that apply to all posts for this animal
            global_context = {
                "animal_id": animal.get("animal_id"),
                "final_status": animal.get("final_status"),
                "final_description": animal.get("final_description"),
                "consolidated_status_rationale": animal.get("status_rationale"),
                "animal_name": animal.get("name"),
                "animal_species": animal.get("species")
            }

            for post in animal.get("post_details", []):
                # Merge the individual post data with the global animal context
                final_line = {**post, **global_context}

                # Write as a single line in the .jsonl
                f_out.write(json.dumps(final_line) + '\n')


# Usage
input_json_dir_path = '/bsky/datasets/needs_help/04-02-2026-old/'
unfold_to_final_jsonl('%sunique_animals_report-all-v2.json' % input_json_dir_path,
                      '%sfinal_enriched_posts.jsonl' % input_json_dir_path)