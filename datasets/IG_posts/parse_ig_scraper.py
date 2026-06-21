import json

DATASETS_IG_POSTS_ = '/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/IG_posts/'
file_path = '%sdataset_instagram-scraper_2026-04-07_21-31-14-986.json' % DATASETS_IG_POSTS_


def extract_commenter_usernames(file_path):
    unique_usernames = set()

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            posts = json.load(f)

        for post in posts:
            # Get the list of top-level comments for this post
            comments = post.get('latestComments', [])

            for comment in comments:
                # Extract the username of the person who made the comment
                username = comment.get('ownerUsername')
                if username:
                    unique_usernames.add(username)

        # Output the results
        if not unique_usernames:
            print("No comment usernames found in the JSON file.")
        else:
            print(f"--- Found {len(unique_usernames)} unique commenters ---")
            for user in sorted(unique_usernames):
                print(user)

    except FileNotFoundError:
        print(f"Error: The file '{file_path}' was not found.")
    except json.JSONDecodeError:
        print("Error: Failed to decode JSON. Check the file format.")


if __name__ == "__main__":
    extract_commenter_usernames(file_path)