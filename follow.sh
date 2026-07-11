#!/bin/bash

set -e  # Stop if any command fails

echo "Running NE follower tool..."
python3 bsky_follow_tool_db.py ne_news-follower-config.json
python3 BskyFollower3.py ne_news_to-follow-config_following_profiles.jsonl

echo "Running S follower tool..."
python3 bsky_follow_tool.py s_news-follower-config.json
python3 BskyFollower3.py s_news_to-follow-config.json

echo "Running DT follower tool..."
python3 bsky_follow_tool.py dt_news_to-follow-config.json
python3 BskyFollower3.py dt_news-follower-config.json

echo "All tasks completed!"