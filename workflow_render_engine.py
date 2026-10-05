import json
import math
import os
import random
import shutil
import subprocess
import tempfile
import time
import wave
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}


@dataclass
class RenderJobResult:
    output_dir: str
    video_path: str
    preview_tracklist_path: str
    verified_tracklist_path: str
    manifest_path: str
    playlist_entries: int
    total_duration_seconds: float
    seed: Optional[int]
    used_media: List[str]


def seconds_to_duration(seconds: float) -> str:
    total_seconds = max(0, int(seconds))
    hh = total_seconds // 3600
    mm = (total_seconds % 3600) // 60
    ss = total_seconds % 60
    return f"{hh:02d}:{mm:02d}:{ss:02d}"


def command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def run_subprocess(
    cmd: List[str],
    logger: Optional[Callable[[str, str], None]] = None,
    cwd: Optional[Path] = None,
) -> subprocess.CompletedProcess:
    if logger:
        logger(f"▶ {' '.join(cmd[:8])}{' ...' if len(cmd) > 8 else ''}", "debug")
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def probe_media_duration(file_path: Path) -> float:
    result = run_subprocess(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(file_path),
        ]
    )
    return float(result.stdout.strip())


def natural_sort_key(value: str) -> List[object]:
    import re

    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"([0-9]+)", value)]


def ffconcat_path(path: Path) -> str:
    normalized = str(path.resolve()).replace("\\", "/")
    return normalized.replace("'", "'\\''")


def create_track_list(
    audio_files_info: List[Dict[str, object]],
    target_duration: float = 0,
    randomize: bool = False,
    seed: Optional[int] = None,
) -> Tuple[List[Dict[str, object]], float]:
    if not audio_files_info:
        return [], 0.0

    files_to_loop = audio_files_info.copy()
    if randomize:
        rng = random.Random(seed)
        rng.shuffle(files_to_loop)

    playlist_duration = sum(float(item["duration"]) for item in files_to_loop)
    if target_duration <= 0:
        return files_to_loop, playlist_duration

    track_list: List[Dict[str, object]] = []
    total_duration = 0.0
    loops_needed = math.ceil(target_duration / playlist_duration) if playlist_duration > 0 else 1

    for _ in range(loops_needed):
        for item in files_to_loop:
            track_list.append(item)
            total_duration += float(item["duration"])
            if total_duration >= target_duration:
                return track_list, total_duration

    return track_list, total_duration


def save_track_timeline_preview(
    track_list: List[Dict[str, object]],
    file_path: Path,
    original_playlist_duration: float = 0,
) -> None:
    current_time = 0.0
    current_loop_number = 1

    with open(file_path, "w", encoding="utf-8") as handle:
        handle.write("=" * 70 + "\n")
        handle.write("    PREVIEW TRACKLIST - AUDIO/VIDEO TIMELINE\n")
        handle.write("=" * 70 + "\n\n")
        handle.write("Total tracks: {}\n".format(len(track_list)))
        handle.write("Expected total duration: {}\n".format(seconds_to_duration(sum(float(t["duration"]) for t in track_list))))
        if original_playlist_duration > 0:
            handle.write("Original playlist: {}\n".format(seconds_to_duration(original_playlist_duration)))
        handle.write("\n" + "-" * 70 + "\n")
        handle.write(f"{'Start':<12} | {'End':<12} | {'Track Name':<40}\n")
        handle.write("-" * 70 + "\n")

        if original_playlist_duration > 0:
            handle.write(
                f"\n┌─ Loop #1 ({seconds_to_duration(0)} → {seconds_to_duration(original_playlist_duration)}) ─────\n"
            )

        for index, track in enumerate(track_list):
            track_duration = float(track["duration"])
            track_end_time = current_time + track_duration

            if original_playlist_duration > 0 and index > 0:
                expected_loop = int(current_time / original_playlist_duration) + 1
                if expected_loop > current_loop_number:
                    current_loop_number = expected_loop
                    loop_start = (current_loop_number - 1) * original_playlist_duration
                    loop_end = current_loop_number * original_playlist_duration
                    handle.write(
                        f"\n┌─ Loop #{current_loop_number} ({seconds_to_duration(loop_start)} → {seconds_to_duration(loop_end)}) ─────\n"
                    )

            handle.write(
                f"│ {seconds_to_duration(current_time):<10} | {seconds_to_duration(track_end_time):<10} | {track['name']}\n"
            )
            current_time = track_end_time

        handle.write("\n" + "=" * 70 + "\n")
        handle.write(f"End of playlist - Total: {seconds_to_duration(current_time)}\n")
        handle.write("=" * 70 + "\n")


def save_track_timeline_from_video(
    track_list: List[Dict[str, object]],
    video_path: Path,
    file_path: Path,
    original_playlist_duration: float = 0,
) -> None:
    actual_video_duration = probe_media_duration(video_path)
    expected_duration = sum(float(t["duration"]) for t in track_list)
    duration_ratio = actual_video_duration / expected_duration if expected_duration > 0 else 1.0

    track_positions: List[Dict[str, object]] = []
    temp_time = 0.0
    adjusted_loop_duration = original_playlist_duration * duration_ratio if original_playlist_duration > 0 else 0

    for track in track_list:
        adjusted_duration = float(track["duration"]) * duration_ratio
        loop_number = int(temp_time / adjusted_loop_duration) + 1 if adjusted_loop_duration > 0 else 1
        track_positions.append(
            {
                "track": track,
                "start": temp_time,
                "end": temp_time + adjusted_duration,
                "duration": adjusted_duration,
                "loop_number": loop_number,
            }
        )
        temp_time += adjusted_duration

    with open(file_path, "w", encoding="utf-8") as handle:
        handle.write("=" * 70 + "\n")
        handle.write("    DANH SÁCH BÀI HÁT - AUDIO/VIDEO TIMELINE (CHÍNH XÁC)\n")
        handle.write("=" * 70 + "\n\n")
        handle.write(f"Tổng số bài hát: {len(track_list)}\n")
        handle.write(f"Video duration (actual): {seconds_to_duration(actual_video_duration)}\n")
        handle.write(f"Expected duration (from source): {seconds_to_duration(expected_duration)}\n")
        handle.write(f"Duration adjustment ratio: {duration_ratio:.6f}\n")
        if adjusted_loop_duration > 0:
            handle.write(f"Playlist gốc (adjusted): {seconds_to_duration(adjusted_loop_duration)}\n")
        handle.write("\n" + "-" * 70 + "\n")
        handle.write(f"{'Bắt đầu':<12} | {'Kết thúc':<12} | {'Tên bài hát':<40}\n")
        handle.write("-" * 70 + "\n")

        max_loop = max((entry["loop_number"] for entry in track_positions), default=1)
        for loop_number in range(1, max_loop + 1):
            loop_tracks = [entry for entry in track_positions if entry["loop_number"] == loop_number]
            if not loop_tracks:
                continue
            if adjusted_loop_duration > 0:
                loop_start = (loop_number - 1) * adjusted_loop_duration
                loop_end = loop_number * adjusted_loop_duration
                handle.write(
                    f"\n┌─ Lần lặp #{loop_number} ({seconds_to_duration(loop_start)} → {seconds_to_duration(loop_end)}) ───────\n"
                )
            for entry in loop_tracks:
                handle.write(
                    f"│ {seconds_to_duration(entry['start']):<10} | {seconds_to_duration(entry['end']):<10} | {entry['track']['name']}\n"
                )

        handle.write("\n" + "=" * 70 + "\n")
        handle.write(f"Kết thúc playlist - Tổng: {seconds_to_duration(temp_time)}\n")
        handle.write("=" * 70 + "\n")


class AudioVideoRenderEngine:
    def __init__(self, work_root: Path):
        self.work_root = Path(work_root)
        self.work_root.mkdir(parents=True, exist_ok=True)

    def ensure_ffmpeg(self) -> None:
        missing = [name for name in ("ffmpeg", "ffprobe") if not command_exists(name)]
        if missing:
            raise RuntimeError("Thiếu công cụ: {}".format(", ".join(missing)))

    def render_claim_workflow_video(
        self,
        settings: Dict[str, object],
        logger: Optional[Callable[[str, str], None]] = None,
    ) -> RenderJobResult:
        self.ensure_ffmpeg()

        audio_files = [Path(item) for item in settings.get("audio_files", [])]
        if not audio_files:
            raise ValueError("Chưa chọn file audio.")

        output_root = Path(settings["output_dir"])
        output_root.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        compilation_name = str(settings.get("compilation_name") or "Claim_Check_Test")
        safe_name = self._sanitize_filename(compilation_name)
        job_dir = output_root / f"{safe_name}_{timestamp}"
        job_dir.mkdir(parents=True, exist_ok=True)

        temp_dir = Path(tempfile.mkdtemp(prefix="claim_checker_render_"))
        used_media: List[str] = []

        try:
            normalized_tracks = self._normalize_audio_inputs(audio_files, temp_dir, logger)
            playlist_target_seconds = self._target_seconds(settings)
            playlist_seed = settings.get("playlist_seed")
            if playlist_seed in ("", None):
                playlist_seed = None
            if playlist_seed is None and settings.get("randomize_playlist"):
                playlist_seed = int(time.time())

            track_list, total_duration = create_track_list(
                normalized_tracks,
                target_duration=playlist_target_seconds,
                randomize=bool(settings.get("randomize_playlist")),
                seed=int(playlist_seed) if playlist_seed is not None else None,
            )
            if not track_list:
                raise RuntimeError("Không thể tạo playlist từ danh sách audio.")

            combined_audio_path = temp_dir / "combined_audio.wav"
            self._concatenate_wave_files(track_list, combined_audio_path)

            preview_tracklist_path = job_dir / f"{safe_name}_Preview_Tracklist.txt"
            verified_tracklist_path = job_dir / f"{safe_name}_Verified_Tracklist.txt"
            output_video_path = job_dir / f"{safe_name}.mp4"

            original_playlist_duration = sum(float(track["duration"]) for track in normalized_tracks)
            save_track_timeline_preview(
                track_list,
                preview_tracklist_path,
                original_playlist_duration if settings.get("loop_playlist") else 0,
            )

            used_media = self._render_video_background(
                audio_path=combined_audio_path,
                audio_duration=probe_media_duration(combined_audio_path),
                settings=settings,
                output_path=output_video_path,
                temp_dir=temp_dir,
                logger=logger,
            )

            save_track_timeline_from_video(
                track_list,
                output_video_path,
                verified_tracklist_path,
                original_playlist_duration if settings.get("loop_playlist") else 0,
            )

            manifest_path = job_dir / "workflow_manifest.json"
            manifest = {
                "created_at": datetime.now().isoformat(),
                "settings": self._json_safe_settings(settings),
                "audio_files": [str(path) for path in audio_files],
                "playlist_entries": len(track_list),
                "total_duration_seconds": total_duration,
                "total_duration_readable": seconds_to_duration(total_duration),
                "video_path": str(output_video_path),
                "preview_tracklist_path": str(preview_tracklist_path),
                "verified_tracklist_path": str(verified_tracklist_path),
                "used_media": used_media,
                "seed": playlist_seed,
            }
            with open(manifest_path, "w", encoding="utf-8") as handle:
                json.dump(manifest, handle, indent=2, ensure_ascii=False)

            return RenderJobResult(
                output_dir=str(job_dir),
                video_path=str(output_video_path),
                preview_tracklist_path=str(preview_tracklist_path),
                verified_tracklist_path=str(verified_tracklist_path),
                manifest_path=str(manifest_path),
                playlist_entries=len(track_list),
                total_duration_seconds=total_duration,
                seed=int(playlist_seed) if playlist_seed is not None else None,
                used_media=used_media,
            )
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def _normalize_audio_inputs(
        self,
        audio_files: List[Path],
        temp_dir: Path,
        logger: Optional[Callable[[str, str], None]],
    ) -> List[Dict[str, object]]:
        normalized_tracks: List[Dict[str, object]] = []
        cache_dir = temp_dir / "normalized_audio"
        cache_dir.mkdir(parents=True, exist_ok=True)

        for index, audio_file in enumerate(audio_files, start=1):
            output_path = cache_dir / f"{index:03d}_{self._sanitize_filename(audio_file.stem)}.wav"
            if logger:
                logger(f"Chuẩn hóa audio {index}/{len(audio_files)}: {audio_file.name}", "info")
            run_subprocess(
                [
                    "ffmpeg",
                    "-y",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-i",
                    str(audio_file),
                    "-vn",
                    "-ac",
                    "2",
                    "-ar",
                    "48000",
                    "-sample_fmt",
                    "s16",
                    str(output_path),
                ],
                logger=logger,
            )
            duration = self._wave_duration(output_path)
            normalized_tracks.append(
                {
                    "name": audio_file.name,
                    "original": str(audio_file),
                    "normalized": str(output_path),
                    "duration": duration,
                }
            )
        return normalized_tracks

    def _concatenate_wave_files(self, track_list: List[Dict[str, object]], output_path: Path) -> None:
        with wave.open(str(track_list[0]["normalized"]), "rb") as first_input:
            params = first_input.getparams()
            with wave.open(str(output_path), "wb") as output_wave:
                output_wave.setparams(params)
                for track in track_list:
                    with wave.open(str(track["normalized"]), "rb") as input_wave:
                        output_wave.writeframes(input_wave.readframes(input_wave.getnframes()))

    def _render_video_background(
        self,
        audio_path: Path,
        audio_duration: float,
        settings: Dict[str, object],
        output_path: Path,
        temp_dir: Path,
        logger: Optional[Callable[[str, str], None]],
    ) -> List[str]:
        video_type = str(settings.get("video_type") or "Màn Hình Đen")
        resolution = str(settings.get("resolution") or "1920x1080")
        fps = str(settings.get("fps") or "30")
        codec = str(settings.get("codec") or "libx264")
        video_speed = max(float(settings.get("video_speed") or 1.0), 0.01)
        used_media: List[str] = []

        width, height = resolution.split("x")
        scale_pad = f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1"

        if video_type == "Màn Hình Đen":
            cmd = [
                "ffmpeg",
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                f"color=c=black:s={resolution}:r={fps}:d={audio_duration:.3f}",
                "-i",
                str(audio_path),
                "-c:v",
                codec,
                "-pix_fmt",
                "yuv420p",
                "-r",
                fps,
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-movflags",
                "+faststart",
                "-shortest",
                str(output_path),
            ]
            run_subprocess(cmd, logger=logger)
            return used_media

        media_files = [Path(item) for item in settings.get("media_files", [])]
        if not media_files:
            raise ValueError(f"Video type '{video_type}' cần media files.")

        if video_type == "Ảnh Tĩnh":
            image_file = self._select_media_file(media_files, "image", bool(settings.get("random_media")))
            used_media = [str(image_file)]
            cmd = [
                "ffmpeg",
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-loop",
                "1",
                "-i",
                str(image_file),
                "-i",
                str(audio_path),
                "-vf",
                scale_pad,
                "-c:v",
                codec,
                "-pix_fmt",
                "yuv420p",
                "-r",
                fps,
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-movflags",
                "+faststart",
                "-shortest",
                "-t",
                f"{audio_duration:.3f}",
                str(output_path),
            ]
            run_subprocess(cmd, logger=logger)
            return used_media

        if video_type == "Lặp Video":
            video_file = self._select_media_file(media_files, "video", bool(settings.get("random_media")))
            used_media = [str(video_file)]
            vf = f"{scale_pad},setpts=PTS/{video_speed}"
            cmd = [
                "ffmpeg",
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-stream_loop",
                "-1",
                "-i",
                str(video_file),
                "-i",
                str(audio_path),
                "-vf",
                vf,
                "-c:v",
                codec,
                "-pix_fmt",
                "yuv420p",
                "-r",
                fps,
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-movflags",
                "+faststart",
                "-shortest",
                str(output_path),
            ]
            run_subprocess(cmd, logger=logger)
            return used_media

        if video_type == "Trình Chiếu Ảnh":
            slideshow_path, used_media = self._build_slideshow_video(
                media_files=media_files,
                settings=settings,
                temp_dir=temp_dir,
                logger=logger,
            )
            cmd = [
                "ffmpeg",
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-stream_loop",
                "-1",
                "-i",
                str(slideshow_path),
                "-i",
                str(audio_path),
                "-c:v",
                codec,
                "-pix_fmt",
                "yuv420p",
                "-r",
                fps,
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-movflags",
                "+faststart",
                "-shortest",
                str(output_path),
            ]
            run_subprocess(cmd, logger=logger)
            return used_media

        raise ValueError(f"Không hỗ trợ video type: {video_type}")

    def _build_slideshow_video(
        self,
        media_files: List[Path],
        settings: Dict[str, object],
        temp_dir: Path,
        logger: Optional[Callable[[str, str], None]],
    ) -> Tuple[Path, List[str]]:
        resolution = str(settings.get("resolution") or "1920x1080")
        fps = str(settings.get("fps") or "30")
        codec = str(settings.get("codec") or "libx264")
        image_duration = max(float(settings.get("image_duration") or 5.0), 0.5)
        video_speed = max(float(settings.get("video_speed") or 1.0), 0.01)
        random_media = bool(settings.get("random_media"))

        images = [path for path in media_files if path.suffix.lower() in IMAGE_EXTENSIONS]
        if not images:
            raise ValueError("Trình Chiếu Ảnh yêu cầu ít nhất 1 file ảnh.")

        ordered_images = images.copy()
        if random_media:
            random.Random(settings.get("media_seed") or int(time.time())).shuffle(ordered_images)
        else:
            ordered_images.sort(key=lambda item: natural_sort_key(item.name))

        slideshow_file = temp_dir / "slideshow.ffconcat"
        duration_per_image = image_duration / video_speed
        with open(slideshow_file, "w", encoding="utf-8") as handle:
            handle.write("ffconcat version 1.0\n")
            for image_file in ordered_images:
                handle.write(f"file '{ffconcat_path(image_file)}'\n")
                handle.write(f"duration {duration_per_image:.3f}\n")
            handle.write(f"file '{ffconcat_path(ordered_images[-1])}'\n")

        slideshow_video = temp_dir / "slideshow_source.mp4"
        width, height = resolution.split("x")
        vf = f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps},format=yuv420p"
        run_subprocess(
            [
                "ffmpeg",
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-safe",
                "0",
                "-f",
                "concat",
                "-i",
                str(slideshow_file),
                "-vsync",
                "vfr",
                "-vf",
                vf,
                "-c:v",
                codec,
                "-pix_fmt",
                "yuv420p",
                str(slideshow_video),
            ],
            logger=logger,
        )
        return slideshow_video, [str(path) for path in ordered_images]

    def _select_media_file(self, media_files: List[Path], expected_type: str, random_media: bool) -> Path:
        if expected_type == "image":
            candidates = [path for path in media_files if path.suffix.lower() in IMAGE_EXTENSIONS]
        else:
            candidates = [path for path in media_files if path.suffix.lower() in VIDEO_EXTENSIONS]

        if not candidates:
            raise ValueError(f"Không có media phù hợp cho loại '{expected_type}'.")

        if random_media:
            return random.choice(candidates)
        return sorted(candidates, key=lambda item: natural_sort_key(item.name))[0]

    def _target_seconds(self, settings: Dict[str, object]) -> int:
        if not settings.get("loop_playlist"):
            return 0
        hours = int(settings.get("target_hours") or 0)
        minutes = int(settings.get("target_minutes") or 0)
        return hours * 3600 + minutes * 60

    def _wave_duration(self, file_path: Path) -> float:
        with wave.open(str(file_path), "rb") as handle:
            return handle.getnframes() / float(handle.getframerate())

    def _sanitize_filename(self, value: str) -> str:
        invalid = '<>:"/\\|?*'
        sanitized = "".join("_" if char in invalid else char for char in value).strip()
        return sanitized or "output"

    def _json_safe_settings(self, settings: Dict[str, object]) -> Dict[str, object]:
        safe = {}
        for key, value in settings.items():
            if isinstance(value, Path):
                safe[key] = str(value)
            elif isinstance(value, list):
                safe[key] = [str(item) if isinstance(item, Path) else item for item in value]
            else:
                safe[key] = value
        return safe
