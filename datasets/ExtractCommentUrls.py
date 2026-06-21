import json


def print_comment_urls(file_path):
    comment_count = 0

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip():
                    continue

                data = json.loads(line)
                result = data.get('result', {})

                # Get the base post URL and the list of comments
                post_url = result.get('url')
                comments = result.get('latestComments', [])

                if post_url and comments:
                    # Ensure the post URL ends with a slash for formatting
                    if not post_url.endswith('/'):
                        post_url += '/'

                    for comment in comments:
                        comment_id = comment.get('id')
                        if comment_id:
                            # Construct the specific deep-link to the comment
                            full_comment_url = f"{post_url}c/{comment_id}/"
                            print(full_comment_url)
                            comment_count += 1

        if comment_count == 0:
            print("No comments found in the file.")

    except FileNotFoundError:
        print(f"Error: The file '{file_path}' was not found.")
    except json.JSONDecodeError:
        print("Error: Failed to parse JSON. Ensure the file is in .jsonl format.")


# Run the function
print_comment_urls('instagram_post_results.jsonl')