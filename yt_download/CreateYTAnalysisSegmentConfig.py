import json
import math
import argparse
import os


def seconds_to_hhmmss(seconds):
    """Converts seconds into HH:MM:SS format."""
    hours = math.floor(seconds / 3600)
    minutes = math.floor((seconds % 3600) / 60)
    secs = math.floor(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def generate_config_from_analysis(analysis_file, output_config_file, target_category, padding=3):
    # Ensure the input file exists
    if not os.path.exists(analysis_file):
        print(f"Error: The input file '{analysis_file}' does not exist.")
        return

    # Load the transcript analysis
    with open(analysis_file, 'r', encoding='utf-8') as f:
        transcript_data = json.load(f)

    raw_segments = []

    # 1. Search for matching segments based on the category string in the "matches" array
    for item in transcript_data:
        matches = item.get('matches', [])

        # Check if the user-specified category is listed in this item's matches
        if target_category.lower() in [m.lower() for m in matches]:
            start_time = max(0, item['start'] - padding)
            # Use item['end'] directly instead of calculating with 'duration'
            end_time = item['end'] + padding
            raw_segments.append([start_time, end_time])

    if not raw_segments:
        print(f"No matching segments found for category: '{target_category}'")
        return

    # 2. Merge overlapping or consecutive timestamps
    raw_segments.sort(key=lambda x: x[0])
    merged_segments = [raw_segments[0]]

    for current in raw_segments[1:]:
        prev = merged_segments[-1]
        if current[0] <= prev[1]:
            prev[1] = max(prev[1], current[1])
        else:
            merged_segments.append(current)

    # 3. Format segments into "HH:MM:SS" strings
    formatted_segments = [
        [seconds_to_hhmmss(seg[0]), seconds_to_hhmmss(seg[1])]
        for seg in merged_segments
    ]

    # 4. Construct the configuration payload
    # Replacing invalid filename characters like '/' for categories like 'karma/enemies'
    safe_category_name = target_category.replace("/", "_")
    config_data = {
        "input_file": "input_video.mp4",
        "output_file": f"{safe_category_name}_segments.mp4",
        "segments": formatted_segments
    }

    # Ensure output directory path exists
    output_dir = os.path.dirname(output_config_file)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    # Save to file
    with open(output_config_file, 'w', encoding='utf-8') as f:
        json.dump(config_data, f, indent=2)

    print(f"Successfully generated config file with {len(formatted_segments)} segments.")
    print(f"Saved to: {output_config_file}")


if __name__ == "__main__":
    # Setup CLI Argument Parser
    parser = argparse.ArgumentParser(description="Generate segment configs from an categorized analysis JSON.")
    parser.add_argument("-i", "--input", required=True, help="Path to the input analysis JSON file")
    parser.add_argument("-o", "--output", required=True, help="Path to save the generated config JSON file")
    parser.add_argument("-c", "--category", required=True,
                        help="The target category match to filter by (e.g., stalking, financial)")
    parser.add_argument("-p", "--padding", type=int, default=3, help="Padding in seconds to add to clips (default: 3)")

    args = parser.parse_args()

    generate_config_from_analysis(
        analysis_file=args.input,
        output_config_file=args.output,
        target_category=args.category,
        padding=args.padding
    )