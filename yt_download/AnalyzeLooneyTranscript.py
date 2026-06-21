import os
import json
from enum import Enum
from google import genai
from pydantic import BaseModel
from typing import List, Dict

TRANSCRIPTS_DIR = '/Users/hdon/Desktop/Video_Segments/transcripts/'
ANALYSIS_DIR = '/Users/hdon/Desktop/Video_Segments/transcripts/Looney_Hateful_Content/'

os.makedirs(ANALYSIS_DIR, exist_ok=True)


# --- FIX: Removed extra parentheses ---
class MatchCategory(str, Enum):
    STALKING = "stalking"
    RUMORS_GOSSIP = "rumors/gossip"
    VEHICLE = "vehicle"
    HOUSE_MOVE = "house/move"
    FINANCIAL = "financial"
    NEGATIVITY = "general negativity"
    KARMA_ENEMIES = "karma/enemies"
    LIES = "lying, spreading lies"


class FoundSegment(BaseModel):
    start_time: float
    end_time: float
    text: str
    reason: str
    match_type: MatchCategory


class AnalysisResponse(BaseModel):
    matches: List[FoundSegment]


def load_transcript(file_path: str) -> str:
    try:
        with open(file_path, 'r') as f:
            data: List[Dict] = json.load(f)
        return "\n".join([f"[{item['start']:.2f}s] {item['text']}" for item in data])
    except Exception as e:
        return f"Error loading file: {e}"


def get_gemini_segments(transcript: str, query: str) -> List[FoundSegment]:
    client = genai.Client()
    prompt = (
        f"Analyze this transcript. Find all segments matching: '{query}'.\n"
        f"For each match, assign the most relevant category from the provided schema.\n\n"
        f"TRANSCRIPT:\n{transcript}"
    )

    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
        config={
            'response_mime_type': 'application/json',
            'response_schema': AnalysisResponse,
        }
    )
    return response.parsed.matches


def merge_segments(segments: List[FoundSegment], threshold: float = 2.0) -> List[Dict]:
    if not segments: return []

    sorted_segs = sorted(segments, key=lambda x: x.start_time)

    merged = []
    current_start = sorted_segs[0].start_time
    current_end = sorted_segs[0].end_time
    current_text = [sorted_segs[0].text]
    # Use .value to ensure we store the string, not the Enum object
    current_categories = {sorted_segs[0].match_type.value}

    for next_seg in sorted_segs[1:]:
        if next_seg.start_time <= current_end + threshold:
            current_end = max(current_end, next_seg.end_time)
            current_text.append(next_seg.text)
            current_categories.add(next_seg.match_type.value)
        else:
            merged.append({
                "start": round(current_start, 2),
                "end": round(current_end, 2),
                "text": " ".join(current_text).strip(),
                "matches": sorted(list(current_categories))
            })
            current_start = next_seg.start_time
            current_end = next_seg.end_time
            current_text = [next_seg.text]
            current_categories = {next_seg.match_type.value}

    merged.append({
        "start": round(current_start, 2),
        "end": round(current_end, 2),
        "text": " ".join(current_text).strip(),
        "matches": sorted(list(current_categories))
    })
    return merged


def main():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("❌ Error: GEMINI_API_KEY environment variable is not set.")
        return

    QUERY = (
        "Identify moments involving: stalking, following, rumors, spreading lies, "
        "gossiping, bullying, vehicles, housing/moving, money/finance, karma/enemies, "
        "or general spiteful/negative content."
    )

    files = [f for f in os.listdir(TRANSCRIPTS_DIR) if f.endswith('.json')]

    for filename in files:
        input_path = os.path.join(TRANSCRIPTS_DIR, filename)
        output_path = os.path.join(ANALYSIS_DIR, f"analysis_{filename}")

        print(f"--- Processing: {filename} ---")
        formatted_text = load_transcript(input_path)

        if "Error" in formatted_text:
            print(formatted_text)
            continue

        try:
            raw_segments = get_gemini_segments(formatted_text, QUERY)
            final_clips = merge_segments(raw_segments)

            with open(output_path, 'w') as f:
                json.dump(final_clips, f, indent=4)
            print(f"✅ Saved {len(final_clips)} clips to: analysis_{filename}")
        except Exception as e:
            print(f"❌ Failed to process {filename}: {e}")


if __name__ == "__main__":
    main()