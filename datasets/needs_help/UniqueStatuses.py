import json
import os


def get_unique_statuses(directory):
    unique_statuses = set()
    files_checked = 0

    if not os.path.exists(directory):
        print(f"Error: Directory '{directory}' does not exist.")
        return

    for filename in os.listdir(directory):
        if filename.endswith(".json"):
            files_checked += 1
            file_path = os.path.join(directory, filename)

            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                    # Case 1: The file is a list of animal objects
                    if isinstance(data, list):
                        for item in data:
                            status = item.get("final_status")
                            if status:
                                unique_statuses.add(status)

                    # Case 2: The file is a single animal object
                    elif isinstance(data, dict):
                        status = data.get("final_status")
                        if status:
                            unique_statuses.add(status)

            except Exception as e:
                print(f"Could not read {filename}: {e}")

    print(f"\n--- Analysis Complete ---")
    print(f"Files scanned: {files_checked}")
    print(f"Unique 'final_status' values found ({len(unique_statuses)} total):")
    print("-" * 30)

    for status in sorted(list(unique_statuses)):
        print(f"- {status}")


if __name__ == "__main__":
    # Update this path to where your files are located
    path_to_jsons = '/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/needs_help/04-02-2026'
    get_unique_statuses(path_to_jsons)