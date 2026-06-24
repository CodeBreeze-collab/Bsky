#!/bin/zsh

# Exit immediately if a command exits with a non-zero status
set -e

# =====================================================================
# Configuration & Paths (Dynamic Environment Matching)
# =====================================================================
if [[ -n "$BSKY_DATE" ]]; then
    CURRENT_DATE="$BSKY_DATE"
else
    CURRENT_DATE=$(date +"%m-%d-%Y")
fi

BASE_DIR="/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/needs_help/$CURRENT_DATE"

# Python script paths
SCRIPT1_PATH="./BlueskyRescueCheckerV3.py"
SCRIPT2_PATH="./IdentifyPetsFixed.py"
SCRIPT3_PATH="./unique-per-animal.py"

# Explicitly mapping to your v2 datasets directory layout
if [[ -f "./GCSUploader.py" ]]; then
    SCRIPT4_PATH="./GCSUploader.py"
elif [[ -f "../v2/datasets/GCSUploader.py" ]]; then
    SCRIPT4_PATH="../v2/datasets/GCSUploader.py"
else
    # Fallback to absolute path to guarantee it never drops
    SCRIPT4_PATH="/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/v2/datasets/GCSUploader.py"
fi

# Data file pipeline targets
CLEANED_OUTPUT_FILE="$BASE_DIR/bluesky_rescue_posts_output-w-post-date.jsonl"
AGGREGATED_OUTPUT_FILE="$BASE_DIR/aggregated_rescue_profiles.json"
ANIMAL_CENTRIC_OUTPUT_FILE="$BASE_DIR/animal_centric_posts-w-loc-2.jsonl"

# GCS Cloud Target Configurations
GCS_BUCKET="summary-334d4-data"
GCS_DESTINATION_PATH="pet_adoptions_v2/$CURRENT_DATE/animal_centric_posts-w-loc-2.jsonl"
GCS_CREDS_JSON="/Users/hdon/Downloads/Google-Cloud-Storage-summary-334d4-238ba52b87b7-API-Key.json"

# Log management
LOG_FILE="$BASE_DIR/pipeline_execution.log"

log_message() {
    local msg="$1"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $msg" | tee -a "$LOG_FILE"
}

mkdir -p "$BASE_DIR"
touch "$LOG_FILE"

log_message "🚀 Starting Animal Rescue Data Pipeline Processing Engine..."
log_message "📅 Target Date Directory: $CURRENT_DATE"

log_message "🔧 CONFIG CHECK — Variables in use:"
log_message "   BSKY_DATE        = ${BSKY_DATE:-<not set, using today>}"
log_message "   BSKY_HANDLE      = ${BSKY_HANDLE:-<not set>}"
log_message "   BSKY_INPUT_FILE  = ${BSKY_INPUT_FILE:-<not set>}"
log_message "   BSKY_DAYS        = ${BSKY_DAYS:-<not set>}"
log_message "   GEMINI_API_KEY   = ${GEMINI_API_KEY:+<set>}${GEMINI_API_KEY:-<NOT SET>}"
log_message "   BASE_DIR         = $BASE_DIR"
log_message "   SCRIPT1_PATH     = $SCRIPT1_PATH"
log_message "   SCRIPT2_PATH     = $SCRIPT2_PATH"
log_message "   SCRIPT3_PATH     = $SCRIPT3_PATH"
log_message "   SCRIPT4_PATH     = $SCRIPT4_PATH"
log_message "   GCS_BUCKET       = $GCS_BUCKET"
log_message "   GCS_DEST_PATH    = $GCS_DESTINATION_PATH"
log_message "   GCS_CREDS_JSON   = $GCS_CREDS_JSON"

ARGS=(--output-file "$CLEANED_OUTPUT_FILE")
[[ -n "$BSKY_HANDLE" ]]     && ARGS+=(--handle "$BSKY_HANDLE")
[[ -n "$BSKY_INPUT_FILE" ]] && ARGS+=(--input-file "$BSKY_INPUT_FILE")
[[ -n "$BSKY_DAYS" ]]       && ARGS+=(--days "$BSKY_DAYS")
[[ -n "$BSKY_DATE" ]]       && ARGS+=(--date "$BSKY_DATE")

# =====================================================================
# STEP 1: Fetch and Filter Raw Posts from Bluesky
# =====================================================================
log_message "────────── STEP 1: Running BlueskyRescueCheckerV3.py ──────────"
python3 "$SCRIPT1_PATH" "${ARGS[@]}"

if [[ -f "$CLEANED_OUTPUT_FILE" && -s "$CLEANED_OUTPUT_FILE" ]]; then
    log_message "✅ Step 1 completed successfully. Raw feed saved to: $CLEANED_OUTPUT_FILE"
else
    log_message "⚠️ Pipeline Halted: Step 1 succeeded, but no matching rescue posts were found."
    exit 0
fi

# =====================================================================
# STEP 2: Profile Deduplication and AI Aggregation (Gemini)
# =====================================================================
log_message "────────── STEP 2: Running IdentifyPetsFixed.py ──────────"
if [[ -n "$GEMINI_API_KEY" ]]; then
    python3 "$SCRIPT2_PATH" \
        --input-file "$CLEANED_OUTPUT_FILE" \
        --output-file "$AGGREGATED_OUTPUT_FILE" \
        --batch-size 15

    if [[ -f "$AGGREGATED_OUTPUT_FILE" && -s "$AGGREGATED_OUTPUT_FILE" ]]; then
        log_message "✅ Step 2 completed successfully. Structured profiles aggregated into: $AGGREGATED_OUTPUT_FILE"
    else
        log_message "❌ Error: Step 2 compilation failed or returned empty structures."
        exit 1
    fi
else
    log_message "❌ Error: GEMINI_API_KEY environment variable missing."
    exit 1
fi

# =====================================================================
# STEP 3: Flat Profile Serialization
# =====================================================================
log_message "────────── STEP 3: Running unique-per-animal.py ──────────"
if [[ -f "$AGGREGATED_OUTPUT_FILE" ]]; then
    python3 "$SCRIPT3_PATH" \
        --input-file "$AGGREGATED_OUTPUT_FILE" \
        --output-file "$ANIMAL_CENTRIC_OUTPUT_FILE"

    if [[ -f "$ANIMAL_CENTRIC_OUTPUT_FILE" && -s "$ANIMAL_CENTRIC_OUTPUT_FILE" ]]; then
        log_message "✅ Step 3 completed successfully. Final flat dataset generated: $ANIMAL_CENTRIC_OUTPUT_FILE"
    else
        log_message "❌ Error: Step 3 pipeline run produced an empty trace."
        exit 1
    fi
else
    log_message "❌ Error: Pipeline break. Step 3 input file was missing."
    exit 1
fi

# =====================================================================
# STEP 4: Upload Final Dataset to Google Cloud Storage (GCS)
# =====================================================================
log_message "────────── STEP 4: Running GCSUploader.py ──────────"
if [[ -f "$ANIMAL_CENTRIC_OUTPUT_FILE" ]]; then
    log_message "☁️ Syncing assets to cloud architecture bucket: $GCS_BUCKET..."
    log_message "📍 Target path: $GCS_DESTINATION_PATH"

    python3 "$SCRIPT4_PATH" \
        -b "$GCS_BUCKET" \
        -s "$ANIMAL_CENTRIC_OUTPUT_FILE" \
        -d "$GCS_DESTINATION_PATH" \
        -c "$GCS_CREDS_JSON"

    log_message "✅ Step 4 completed successfully. Storage sync verified."
else
    log_message "❌ Error: Pipeline break. Step 4 input file was missing."
    exit 1
fi

log_message "🎉 Complete Pipeline finished with zero defects. Cloud target updated successfully."