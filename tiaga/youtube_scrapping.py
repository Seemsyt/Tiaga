import time
from langchain_core.tools import tool
from youtube_transcript_api import YouTubeTranscriptApi
from deep_translator import GoogleTranslator


# ── Helpers ────────────────────────────────────────────────────────────────────

def _extract_video_id(link: str) -> str:
    """Extract the video ID from various YouTube URL formats."""
    # Handle: youtu.be/ID, ?v=ID, &v=ID
    if "youtu.be/" in link:
        return link.split("youtu.be/")[-1].split("?")[0].split("&")[0]
    if "v=" in link:
        vid = link.split("v=")[-1]
        return vid.split("&")[0]
    # Assume raw ID was passed
    return link.strip()


def _chunk_text(text: str, max_size: int = 4500) -> list[str]:
    """Split text into chunks without cutting mid-word."""
    chunks, start = [], 0
    while start < len(text):
        end = min(start + max_size, len(text))
        if end < len(text):
            # walk back to nearest space
            while end > start and text[end] != " ":
                end -= 1
        chunks.append(text[start:end].strip())
        start = end
    return chunks


def _get_transcript(link: str) -> str:
    """Fetch raw transcript text from a YouTube video."""
    video_id = _extract_video_id(link)
    yyt = YouTubeTranscriptApi()
    result = yyt.fetch(video_id, languages=["hi", "en"])
    return " ".join(snippet.text for snippet in result)  # space between snippets


def _translate_to_english(text: str) -> str:
    """Translate text to English in chunks, return full string."""
    translator = GoogleTranslator(source="auto", target="en")
    chunks = _chunk_text(text)
    translated_parts = []

    for i, chunk in enumerate(chunks):
        print(f"  [transcript] translating chunk {i + 1}/{len(chunks)}…")
        translated_parts.append(translator.translate(chunk))

    return " ".join(translated_parts)


# ── Tool ───────────────────────────────────────────────────────────────────────

@tool
def get_youtube_transcript(link: str) -> str:
    """
    Fetch and translate the transcript of a YouTube video to English.

    Supports Hindi and English source videos. Use this when the user
    asks to summarise, explain, or ask questions about a YouTube video.

    Args:
        link: Full YouTube URL (e.g. https://www.youtube.com/watch?v=...) 
              or a bare video ID.

    Returns:
        The full translated transcript as a plain English string.
    """
    try:
        print(f"  [transcript] fetching transcript for: {link}")
        raw_text = _get_transcript(link)

        print(f"  [transcript] got {len(raw_text)} chars, translating…")
        translated = _translate_to_english(raw_text)

        print(f"  [transcript] done — {len(translated)} chars")
        return translated

    except Exception as e:
        return f"Failed to get transcript: {e}"