#!/bin/bash

set -euo pipefail

mkdir -p logs

cleanup() {
    echo
    echo "Stopping all child processes..."
    trap - EXIT INT TERM
    kill 0 2>/dev/null || true
}

trap cleanup EXIT INT TERM

timestamp=$(date +"%Y%m%d-%H%M%S")

# NE
(
    echo "=== Started $(date) ==="
    python3 bsky_follow_tool_db.py ne_news-follower-config.json
    python3 BskyFollower3.py ne_news_to-follow-config_following_profiles.jsonl
) >"logs/ne-${timestamp}.log" 2>&1 &

# S
(
    echo "=== Started $(date) ==="
    python3 bsky_follow_tool.py s_news-follower-config.json
    python3 BskyFollower3.py s_news_to-follow-config.json
) >"logs/s-${timestamp}.log" 2>&1 &

# DT
(
    echo "=== Started $(date) ==="
    python3 bsky_follow_tool.py dt_news_to-follow-config.json
    python3 BskyFollower3.py dt_news-follower-config.json
) >"logs/dt-${timestamp}.log" 2>&1 &

wait

echo "All jobs completed!"