#!/bin/zsh

# 1. Load environment variables
if [ -f "$HOME/.zshrc" ]; then
    source "$HOME/.zshrc"
fi

# 🌟 PARSE COMMAND LINE ARGUMENTS
AUDIT_ONLY=false
PURGE_ONLY=false

if [ "$1" = "--audit-only" ]; then
    AUDIT_ONLY=true
elif [ "$1" = "--purge-only" ]; then
    PURGE_ONLY=true
fi

if [ -z "$BLUESKY_APP_PASSWORD_v_search" ]; then
    echo "❌ Error: Environment variables are missing."
    exit 1
fi

# Dynamically calculate today's date format (e.g., 06-15-2026)
TODAY="06-15-2026" #$(date +"%m-%d-%Y")

LOG_DIR=$(pwd)
mkdir -p "${LOG_DIR}/unfollow-jsonl"

echo "🚀 Starting Bluesky processing sequentially..."
if [ "$AUDIT_ONLY" = true ]; then
    echo "🔍 MODE: --audit-only active. Profiles will be cached, but NO ONE will be unfollowed."
elif [ "$PURGE_ONLY" = true ]; then
    echo "💥 MODE: --purge-only active. Skipping audits and executing UNFOLLOWS from existing files."
else
    echo "⚡ MODE: Full Run. The script will AUDIT non-followers, then immediately UNFOLLOW them."
fi
echo "------------------------------------------------------------"
echo "💡 Today's Date String: ${TODAY}"
echo "------------------------------------------------------------"


# --- ACCOUNT 1: New England Top News ---
echo "🧵 [1/4] Starting New England Top News..."
(
  if [ "$PURGE_ONLY" = false ]; then
      echo "🧹 Cleaning up old audit caches..."
      rm -f "follows_cache_newenglandtopnews.bsky.social.jsonl" "cursor_newenglandtopnews.bsky.social.txt" "${LOG_DIR}/unfollow-jsonl/old_follows_to_purge_newenglandtopnews_${TODAY}.jsonl"

      echo "📡 [1/2] Auditing non-followers..."
      BLUESKY_APP_PASSWORD="$BLUESKY_APP_PASSWORD_ne_news" python WriteNotFollowingSimple.py \
        --handle "newenglandtopnews.bsky.social" \
        --subject "newenglandtopnews.bsky.social" \
        --output "${LOG_DIR}/unfollow-jsonl/old_follows_to_purge_newenglandtopnews_${TODAY}.jsonl"
  else
      echo "⏭️ [1/2] --purge-only is active. Skipping audit step & retaining existing files."
  fi

  if [ "$AUDIT_ONLY" = false ]; then
      echo "🛑 [2/2] Executing unfollow purge..."
      python UnfollowAccountsFromJSONL.py \
        --handle "newenglandtopnews.bsky.social" \
        --input "${LOG_DIR}/unfollow-jsonl/old_follows_to_purge_newenglandtopnews_${TODAY}.jsonl" \
        --state-file "processed_dids_ne_news.txt" \
        --delay 10.0 --limit 1000 --api-key "$BLUESKY_APP_PASSWORD_ne_news"
  else
      echo "⏭️ [2/2] --audit-only is active. Skipping purge step."
  fi
) > purge_ne_news.log 2>&1
echo "✅ New England finished. Logs written to: ${LOG_DIR}/purge_ne_news.log"
echo "------------------------------------------------------------"


# --- ACCOUNT 2: Vegan Search Engine ---
echo "🧵 [2/4] Starting Vegan Search Engine..."
(
  if [ "$PURGE_ONLY" = false ]; then
      echo "🧹 Cleaning up old audit caches..."
      rm -f "follows_cache_vegansearchengine.bsky.social.jsonl" "cursor_vegansearchengine.bsky.social.txt" "${LOG_DIR}/unfollow-jsonl/old_follows_to_purge_vse_${TODAY}.jsonl"

      echo "📡 [1/2] Auditing non-followers..."
      BLUESKY_APP_PASSWORD="$BLUESKY_APP_PASSWORD_v_search" python WriteNotFollowingSimple.py \
        --handle "vegansearchengine.bsky.social" \
        --subject "vegansearchengine.bsky.social" \
        --output "${LOG_DIR}/unfollow-jsonl/old_follows_to_purge_vse_${TODAY}.jsonl"
  else
      echo "⏭️ [1/2] --purge-only is active. Skipping audit step & retaining existing files."
  fi

  if [ "$AUDIT_ONLY" = false ]; then
      echo "🛑 [2/2] Executing unfollow purge..."
      python UnfollowAccountsFromJSONL.py \
        --handle "vegansearchengine.bsky.social" \
        --input "${LOG_DIR}/unfollow-jsonl/old_follows_to_purge_vse_${TODAY}.jsonl" \
        --state-file "processed_dids_vse.txt" \
        --delay 10.0 --limit 1000 --api-key "$BLUESKY_APP_PASSWORD_v_search"
  else
      echo "⏭️ [2/2] --audit-only is active. Skipping purge step."
  fi
) > purge_vse.log 2>&1
echo "✅ Vegan Search finished. Logs written to: ${LOG_DIR}/purge_vse.log"
echo "------------------------------------------------------------"


# --- ACCOUNT 3: West Coast News ---
echo "🧵 [3/4] Starting West Coast News..."
(
  if [ "$PURGE_ONLY" = false ]; then
      echo "🧹 Cleaning up old audit caches..."
      rm -f "follows_cache_westcoastnews.bsky.social.jsonl" "cursor_westcoastnews.bsky.social.txt" "${LOG_DIR}/unfollow-jsonl/old_follows_to_purge_westcoastnews_${TODAY}.jsonl"

      echo "📡 [1/2] Auditing non-followers..."
      BLUESKY_APP_PASSWORD="$BLUESKY_APP_PASSWORD_s_news" python WriteNotFollowingSimple.py \
        --handle "westcoastnews.bsky.social" \
        --subject "westcoastnews.bsky.social" \
        --output "${LOG_DIR}/unfollow-jsonl/old_follows_to_purge_westcoastnews_${TODAY}.jsonl"
  else
      echo "⏭️ [1/2] --purge-only is active. Skipping audit step & retaining existing files."
  fi

  if [ "$AUDIT_ONLY" = false ]; then
      echo "🛑 [2/2] Executing unfollow purge..."
      python UnfollowAccountsFromJSONL.py \
        --handle "westcoastnews.bsky.social" \
        --input "${LOG_DIR}/unfollow-jsonl/old_follows_to_purge_westcoastnews_${TODAY}.jsonl" \
        --state-file "processed_dids_s_news.txt" \
        --delay 10.0 --limit 1000 --api-key "$BLUESKY_APP_PASSWORD_s_news"
  else
      echo "⏭️ [2/2] --audit-only is active. Skipping purge step."
  fi
) > purge_s_news.log 2>&1
echo "✅ West Coast finished. Logs written to: ${LOG_DIR}/purge_s_news.log"
echo "------------------------------------------------------------"


# --- ACCOUNT 4: Texas Top News ---
echo "🧵 [4/4] Starting Texas Top News..."
(
  if [ "$PURGE_ONLY" = false ]; then
      echo "🧹 Cleaning up old audit caches..."
      rm -f "follows_cache_texastopnews.bsky.social.jsonl" "cursor_texastopnews.bsky.social.txt" "${LOG_DIR}/unfollow-jsonl/old_follows_to_purge_texastopnews_${TODAY}.jsonl"

      echo "📡 [1/2] Auditing non-followers..."
      BLUESKY_APP_PASSWORD="$BLUESKY_APP_PASSWORD_texas_news" python WriteNotFollowingSimple.py \
        --handle "texastopnews.bsky.social" \
        --subject "texastopnews.bsky.social" \
        --output "${LOG_DIR}/unfollow-jsonl/old_follows_to_purge_texastopnews_${TODAY}.jsonl"
  else
      echo "⏭️ [1/2] --purge-only is active. Skipping audit step & retaining existing files."
  fi

  if [ "$AUDIT_ONLY" = false ]; then
      echo "🛑 [2/2] Executing unfollow purge..."
      python UnfollowAccountsFromJSONL.py \
        --handle "texastopnews.bsky.social" \
        --input "${LOG_DIR}/unfollow-jsonl/old_follows_to_purge_texastopnews_${TODAY}.jsonl" \
        --state-file "processed_dids_texas_news.txt" \
        --delay 10.0 --limit 50 --api-key "$BLUESKY_APP_PASSWORD_texas_news"
  else
      echo "⏭️ [2/2] --audit-only is active. Skipping purge step."
  fi
) > purge_texas_news.log 2>&1
echo "✅ Texas finished. Logs written to: ${LOG_DIR}/purge_texas_news.log"
echo "------------------------------------------------------------"

echo "🏁 All tasks have successfully finished!"