import asyncio
import time
from pydantic import BaseModel, Field
from youtube_transcript_api import YouTubeTranscriptApi
from deep_translator import GoogleTranslator

from tiaga.context.text import truncate_text
from tiaga.tools_manager.base import Tool, Tool_kind, ToolInvocation, ToolResult


# ── Schema ─────────────────────────────────────────────────────

class YouTubeTranscriptParams(BaseModel):
    link: str = Field(..., description="YouTube video URL or video ID")


# ── Helpers ────────────────────────────────────────────────────

def _extract_video_id(link: str) -> str:
    if "youtu.be/" in link:
        return link.split("youtu.be/")[-1].split("?")[0].split("&")[0]
    if "v=" in link:
        return link.split("v=")[-1].split("&")[0]
    return link.strip()


def _chunk_text(text: str, max_size: int = 4500) -> list[str]:
    chunks, start = [], 0
    while start < len(text):
        end = min(start + max_size, len(text))
        if end < len(text):
            while end > start and text[end] != " ":
                end -= 1
        chunks.append(text[start:end].strip())
        start = end
    return chunks


def _get_transcript(video_id: str) -> str:
    ytt = YouTubeTranscriptApi()
    result = ytt.fetch(video_id, languages=["hi", "en"])
    return " ".join(snippet.text for snippet in result)


def _translate(text: str) -> str:
    translator = GoogleTranslator(source="auto", target="en")
    chunks = _chunk_text(text)
    translated = []

    for chunk in chunks:
        translated.append(translator.translate(chunk))

    return " ".join(translated)


# ── Tool ───────────────────────────────────────────────────────

class YouTubeTranscriptTool(Tool):
    name = "youtube_transcript"
    description = "Fetch and translate YouTube video transcript to English."
    tool_kind = Tool_kind.NETWORK
    schema = YouTubeTranscriptParams

    async def execute(self, invocation: ToolInvocation):
        params = YouTubeTranscriptParams(**invocation.params)

        try:
            video_id = _extract_video_id(params.link)

            raw_text = await asyncio.to_thread(_get_transcript, video_id)

            if not raw_text:
                return ToolResult.error_result("No transcript found.")

            translated = await asyncio.to_thread(_translate, raw_text)

        except Exception as e:
            return ToolResult.error_result(f"Transcript error: {e}")

        output = translated
        display_output = None
        is_truncated = False

        maybe_truncated = truncate_text(
            output,
            model="gpt-4o-mini",
            max_tokens=240,
            suffix="\n...[truncated for display]",
        )

        if maybe_truncated != output:
            display_output = maybe_truncated
            is_truncated = True

        return ToolResult.success_result(
            output=output,
            display_output=display_output,
            truncated=is_truncated,
            metadata={
                "video_id": video_id,
                "length": len(output),
            },
        )