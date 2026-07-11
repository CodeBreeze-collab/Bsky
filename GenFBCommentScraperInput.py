import json
import os


class FosterLeadGenerator:
    def __init__(self, foster_keywords=None):
        # Default keywords + common rescue terminology
        self.foster_keywords = foster_keywords or [
            'foster', 'temporary', 'plea', 'urgent', 'hero',
            'pull', 'save', 'safe', 'opening', 'available'
        ]

    def prepare_comments_scraper_input(self, posts_data_path, output_path='comments_input.json', debug=True):
        if not os.path.exists(posts_data_path):
            print(f"Error: File not found at {posts_data_path}")
            return

        with open(posts_data_path, 'r', encoding='utf-8') as f:
            try:
                posts = json.load(f)
            except json.JSONDecodeError:
                print("Error: Failed to decode JSON. Check if the file is valid.")
                return

        target_post_urls = []

        if debug:
            print(f"--- Debugging {len(posts)} posts ---")

        for i, post in enumerate(posts):
            # 1. Try to find the text in various common Facebook scraper fields
            # Apify often changes these between 'text', 'caption', and 'description'
            raw_text = post.get('text') or post.get('caption') or post.get('description') or post.get('content') or ""
            text = str(raw_text).lower()

            # 2. Try to find the URL
            # Note: Comments scraper specifically needs the URL for the post
            url = post.get('url') or post.get('facebookUrl') or post.get('canonicalUrl')

            # 3. Try to find comment count
            comment_count = post.get('commentsCount') or post.get('comments') or 0

            # Check for keywords
            has_keyword = any(keyword in text for keyword in self.foster_keywords)

            if debug and i < 5:
                print(f"Post {i} Keys found: {list(post.keys())}")
                print(f"Post {i} Snippet: {text[:50]}...")
                print(f"Post {i} Keyword Match: {has_keyword} | Comments: {comment_count}")

            if has_keyword and url:
                # We include it if it matches keyword, even if comments are 0
                # (someone might comment later)
                target_post_urls.append({"url": url})

        # Final structure for Apify Facebook Comments Scraper
        comments_input = {
            "includeNestedComments": True,
            "resultsLimit": 100,
            "startUrls": target_post_urls
        }

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(comments_input, f, indent=4)

        print("\n--- Processing Complete ---")
        print(f"Filtered down to {len(target_post_urls)} high-intent posts.")
        print(f"Input for Comments Scraper saved to: {os.path.abspath(output_path)}")


if __name__ == "__main__":
    # Initialize the class
    generator = FosterLeadGenerator()

    # Path to your downloaded Apify dataset
    DATASET_PATH = '/Users/hdon/Downloads/dataset_facebook-posts-scraper_2026-04-23_03-15-43-025.json'

    # Run the processor
    generator.prepare_comments_scraper_input(DATASET_PATH)