"""Codec probing service - detects video/audio codecs from MPEG-TS segments"""

import json
import logging
import os
import subprocess
import tempfile
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class CodecProber:
    """Detects codecs from MPEG-TS segments using FFprobe."""

    @staticmethod
    def probe_segment(segment_path: str) -> Optional[Tuple[str, str]]:
        """
        Probe a segment file for video and audio codecs.

        Args:
            segment_path: Path to the .ts file

        Returns:
            Tuple of (video_codec, audio_codec) or None if probing fails
        """
        try:
            # Get video stream info
            video_result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-select_streams",
                    "v:0",
                    "-show_entries",
                    "stream=codec_name,profile,level",
                    "-of",
                    "json",
                    segment_path,
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if video_result.returncode != 0:
                logger.warning(
                    f"[Codec] FFprobe video probe failed: {video_result.stderr}"
                )
                return None

            video_info = json.loads(video_result.stdout)
            if not video_info.get("streams"):
                logger.warning("[Codec] No video stream found")
                return None

            video_stream = video_info["streams"][0]
            video_codec_name = video_stream.get("codec_name", "h264")
            video_profile = video_stream.get("profile")
            video_level = video_stream.get("level")

            # Get audio stream info
            audio_result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-select_streams",
                    "a:0",
                    "-show_entries",
                    "stream=codec_name",
                    "-of",
                    "json",
                    segment_path,
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )

            audio_codec_name = "aac"  # Default
            if audio_result.returncode == 0:
                audio_info = json.loads(audio_result.stdout)
                if audio_info.get("streams"):
                    audio_codec_name = audio_info["streams"][0].get("codec_name", "aac")

            # Convert to HLS codec strings
            video_codec = CodecProber._to_hls_codec(
                video_codec_name, video_profile, video_level
            )
            audio_codec = CodecProber._to_hls_codec(audio_codec_name, None, None)

            logger.info(
                f"[Codec] Probed codecs: video={video_codec}, audio={audio_codec}"
            )
            return (video_codec, audio_codec)

        except subprocess.TimeoutExpired:
            logger.error("[Codec] FFprobe probe timed out")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"[Codec] Failed to parse FFprobe output: {e}")
            return None
        except Exception as e:
            logger.error(f"[Codec] Unexpected error probing segment: {e}")
            return None

    @staticmethod
    def _to_hls_codec(codec: str, profile: Optional[str], level: Optional[int]) -> str:
        """
        Convert FFmpeg codec info to HLS codec string (RFC 6381).

        Format for H.264: avc1.PPCCLL where:
        - PP = profile_idc (hex, lowercase)
        - CC = constraint_set flags (hex, lowercase)
        - LL = level_idc (hex, lowercase)

        Examples:
            H.264 Baseline Level 3.0 → avc1.42e01e
            H.264 Baseline Level 3.1 → avc1.42e01f
            AAC-LC → mp4a.40.2
        """
        if codec == "h264":
            # Map profile names to profile_idc (hex values)
            profile_idc_map = {
                "Baseline": 66,  # 0x42
                "Main": 77,  # 0x4D
                "High": 100,  # 0x64
                "Constrained Baseline": 66,  # 0x42 (same as Baseline)
                "High 10": 110,  # 0x6E
                "High 4:2:2": 122,  # 0x7A
                "High 4:4:4": 144,  # 0x90
            }

            profile_idc = profile_idc_map.get(profile, 66)  # Default to Baseline

            # Determine constraint set flags based on profile
            # Baseline and Constrained Baseline typically use 0xE0
            # Main and High typically use 0x00
            if profile in ("Baseline", "Constrained Baseline"):
                constraint_flags = 0xE0
            else:
                constraint_flags = 0x00

            # FFmpeg returns level*10 (e.g., 30 for Level 3.0, 31 for Level 3.1)
            # Level 3.0 = 0x1E, Level 3.1 = 0x1F, Level 4.0 = 0x28, etc.
            level_value = level if level else 30  # Default to Level 3.0

            # Format as lowercase hex strings
            profile_hex = f"{profile_idc:02x}"
            constraint_hex = f"{constraint_flags:02x}"
            level_hex = f"{level_value:02x}"

            codec_string = f"avc1.{profile_hex}{constraint_hex}{level_hex}"

            logger.info(
                f"[Codec] H.264: profile={profile} ({profile_idc}), "
                f"constraint={constraint_flags:02x}, level={level_value}, "
                f"codec_string={codec_string}"
            )

            return codec_string

        elif codec in ("hevc", "h265"):
            profile_num = {
                "Main": 1,
                "Main10": 2,
            }.get(profile, 1)
            level_num = (level // 30) if level else 3
            return f"hvc1.{profile_num}.L{level_num:02x}.B0"

        elif codec == "aac":
            return "mp4a.40.2"

        elif codec == "opus":
            return "opus"

        elif codec in ("mp3", "mpga"):
            return "mp4a.40.34"

        else:
            # Unknown codec - return lowercase name
            logger.warning(f"[Codec] Unknown codec '{codec}', using as-is")
            return codec.lower()

    @staticmethod
    def probe_from_bytes(segment_data: bytes) -> Optional[Tuple[str, str]]:
        """
        Probe segment data for codecs.

        Args:
            segment_data: Raw bytes of .ts file

        Returns:
            Tuple of (video_codec, audio_codec) or None if probing fails
        """
        try:
            # Write to temp file
            with tempfile.NamedTemporaryFile(suffix=".ts", delete=False) as tmp:
                tmp.write(segment_data)
                temp_path = tmp.name

            # Probe the temp file
            result = CodecProber.probe_segment(temp_path)

            # Cleanup
            try:
                os.unlink(temp_path)
            except:
                pass

            return result

        except Exception as e:
            logger.error(f"[Codec] Error probing from bytes: {e}")
            return None
