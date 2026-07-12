import json
import os
from pathlib import Path


def merge_records(dict1, dict2):
    """
    Deeply merges dict2 into dict1.
    - If keys conflict, it prefers the non-empty/truthy value (e.g., preserving actual URLs over '').
    - For nested dictionaries (like extracted_location), it merges recursively.
    - For lists (like associated_posts), it merges elements intelligently to avoid duplicates.
    """
    res = dict1.copy()
    for k, v in dict2.items():
        if k in res:
            if isinstance(res[k], dict) and isinstance(v, dict):
                res[k] = merge_records(res[k], v)
            elif isinstance(res[k], list) and isinstance(v, list):
                if k == 'associated_posts':
                    # Deduplicate and merge nested associated posts based on their post_url
                    sub_posts = {p.get('post_url'): p for p in res[k] if p.get('post_url')}
                    for p in v:
                        p_url = p.get('post_url')
                        if p_url in sub_posts:
                            sub_posts[p_url] = merge_records(sub_posts[p_url], p)
                        else:
                            sub_posts[p_url] = p
                    res[k] = list(sub_posts.values())
                else:
                    # For other lists, combine unique elements
                    res[k] = res[k] + [item for item in v if item not in res[k]]
            else:
                # For basic types, prefer the truthy/populated value (e.g., fill in "" with a valid string)
                if not res[k] and v:
                    res[k] = v
        else:
            res[k] = v
    return res


def merge_jsonl_directories(dir1_path, dir2_path, output_path):
    path1 = Path(dir1_path)
    path2 = Path(dir2_path)
    out_base = Path(output_path)

    # Get the union of all subdirectories (date folders) from both sources
    subdirs1 = {p.name for p in path1.iterdir() if p.is_dir()} if path1.exists() else set()
    subdirs2 = {p.name for p in path2.iterdir() if p.is_dir()} if path2.exists() else set()
    all_subdirs = subdirs1.union(subdirs2)

    filename = "animal_centric_posts-w-loc-2.jsonl"

    print(f"Found {len(all_subdirs)} unique date subdirectories to process.\n")

    for subdir in sorted(all_subdirs):
        merged_data = {}

        file1 = path1 / subdir / filename
        file2 = path2 / subdir / filename

        # 1. Process records from the first directory
        if file1.exists():
            with open(file1, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        data = json.loads(line)
                        url = data.get('post_url')
                        if url:
                            merged_data[url] = data

        # 2. Process and merge records from the second directory
        if file2.exists():
            with open(file2, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        data = json.loads(line)
                        url = data.get('post_url')
                        if url:
                            if url in merged_data:
                                # Merge existing post with new fields
                                merged_data[url] = merge_records(merged_data[url], data)
                            else:
                                # If unique to this file, just insert it
                                merged_data[url] = data

        # 3. Write out the composite JSONL file to the target output structure
        if merged_data:
            target_dir = out_base / subdir
            target_dir.mkdir(parents=True, exist_ok=True)
            target_file = target_dir / filename

            with open(target_file, 'w', encoding='utf-8') as f:
                for post_content in merged_data.values():
                    f.write(json.dumps(post_content, ensure_ascii=False) + '\n')

            print(f"[{subdir}] Successfully compiled {len(merged_data)} unique records.")


if __name__ == "__main__":
    # Source paths provided
    DIR_6 = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/needs_help_v2_/v3_corrected/video_enriched_6"
    DIR_URLS = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/needs_help_v2_/v3_corrected/video_enriched_w_urls"

    # Define your target output folder path here
    TARGET_OUTPUT = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/needs_help_v2_/v3_corrected/composite_output"

    merge_jsonl_directories(DIR_6, DIR_URLS, TARGET_OUTPUT)
    print("\nMerge pipeline processing complete!")