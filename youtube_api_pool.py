import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional


DEFAULT_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]


class YouTubeApiDependencyError(RuntimeError):
    pass


@dataclass
class YouTubeUploadJob:
    job_id: str
    video_path: str
    title: str
    description: str = ""
    privacy_status: str = "private"
    tags: List[str] = field(default_factory=list)
    category_id: str = "10"
    manifest_path: str = ""
    tracklist_path: str = ""


@dataclass
class YouTubeUploadResult:
    job_id: str
    video_path: str
    title: str
    privacy_status: str
    success: bool
    video_id: str = ""
    watch_url: str = ""
    studio_url: str = ""
    upload_status: str = ""
    processing_status: str = ""
    processing_failure_reason: str = ""
    channel_title: str = ""
    started_at: str = ""
    finished_at: str = ""
    error: str = ""
    manifest_path: str = ""
    tracklist_path: str = ""


def export_youtube_results_csv(results: List[YouTubeUploadResult], file_path: Path) -> None:
    with open(file_path, "w", encoding="utf-8-sig", newline="") as handle:
        handle.write(
            "Job ID,Title,Video Path,Privacy,Success,Video ID,Upload Status,Processing Status,"
            "Failure Reason,Channel,Watch URL,Studio URL,Started At,Finished At,Manifest Path,Tracklist Path,Error\n"
        )
        for item in results:
            row = [
                item.job_id,
                item.title,
                item.video_path,
                item.privacy_status,
                "Yes" if item.success else "No",
                item.video_id,
                item.upload_status,
                item.processing_status,
                item.processing_failure_reason,
                item.channel_title,
                item.watch_url,
                item.studio_url,
                item.started_at,
                item.finished_at,
                item.manifest_path,
                item.tracklist_path,
                item.error,
            ]
            handle.write(",".join(_csv_escape(value) for value in row) + "\n")


def export_youtube_results_json(results: List[YouTubeUploadResult], file_path: Path) -> None:
    payload = {
        "exported_at": datetime.now().isoformat(),
        "results": [asdict(item) for item in results],
    }
    with open(file_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)


def _csv_escape(value: object) -> str:
    text = str(value or "")
    return '"' + text.replace('"', '""') + '"'


def _import_google_deps():
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError
        from googleapiclient.http import MediaFileUpload
    except ImportError as error:
        raise YouTubeApiDependencyError(
            "Thiếu dependency Google API. Cài thêm: google-api-python-client google-auth-oauthlib google-auth-httplib2"
        ) from error
    return {
        "Request": Request,
        "Credentials": Credentials,
        "InstalledAppFlow": InstalledAppFlow,
        "build": build,
        "HttpError": HttpError,
        "MediaFileUpload": MediaFileUpload,
    }


class YouTubeUploadPool:
    def __init__(self, client_secrets_path: Path, token_path: Path, scopes: Optional[List[str]] = None):
        self.client_secrets_path = Path(client_secrets_path)
        self.token_path = Path(token_path)
        self.scopes = scopes or list(DEFAULT_SCOPES)

    def get_client_secrets_metadata(self) -> Dict[str, str]:
        metadata = {
            "client_id": "",
            "project_id": "",
            "client_type": "",
            "path": str(self.client_secrets_path),
        }
        if not self.client_secrets_path.exists():
            return metadata
        try:
            with open(self.client_secrets_path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except Exception:
            return metadata

        if not isinstance(payload, dict):
            return metadata

        client_type = "installed" if isinstance(payload.get("installed"), dict) else "web"
        oauth_data = payload.get(client_type, {})
        if not isinstance(oauth_data, dict):
            oauth_data = {}

        metadata["client_type"] = client_type
        metadata["client_id"] = str(oauth_data.get("client_id", "") or "")
        metadata["project_id"] = str(oauth_data.get("project_id", "") or "")
        return metadata

    def dependencies_ready(self) -> bool:
        try:
            _import_google_deps()
            return True
        except YouTubeApiDependencyError:
            return False

    def authenticate_interactive(self, force_consent: bool = False):
        deps = _import_google_deps()
        creds = None

        if self.token_path.exists() and not force_consent:
            creds = deps["Credentials"].from_authorized_user_file(str(self.token_path), self.scopes)

        if creds and creds.expired and creds.refresh_token:
            creds.refresh(deps["Request"]())
            self._save_credentials(creds)

        if creds and creds.valid:
            return self.get_channel_info()

        if not self.client_secrets_path.exists():
            raise FileNotFoundError(f"Không tìm thấy OAuth client secrets file:\n{self.client_secrets_path}")

        flow = deps["InstalledAppFlow"].from_client_secrets_file(str(self.client_secrets_path), self.scopes)
        try:
            creds = flow.run_local_server(
                port=0,
                access_type="offline",
                prompt="consent" if force_consent else "select_account",
            )
        except Exception as error:
            error_text = str(error)
            if "access_denied" in error_text.lower():
                raise RuntimeError(self._build_access_denied_message(error_text)) from error
            raise
        self._save_credentials(creds)
        return self.get_channel_info()

    def _build_access_denied_message(self, raw_error: str) -> str:
        metadata = self.get_client_secrets_metadata()
        project_id = metadata.get("project_id") or "(không đọc được project_id)"
        client_id = metadata.get("client_id") or "(không đọc được client_id)"
        lines = [
            "Google đã từ chối OAuth login với lỗi 403 access_denied.",
            "",
            "Nguyên nhân thường gặp nhất:",
            "1. OAuth app đang ở chế độ Testing nhưng tài khoản Google hiện tại chưa được thêm vào Test users.",
            "2. YouTube Data API v3 chưa được enable trong đúng project Google Cloud.",
            "3. OAuth consent screen chưa cấu hình/scopes chưa khai báo đúng.",
            "4. Tài khoản Google Workspace bị admin chặn app bên thứ ba hoặc chặn scope YouTube.",
            "",
            f"Project ID: {project_id}",
            f"Client ID: {client_id}",
            "",
            "Cách xử lý:",
            "- Mở đúng project ở Google Cloud Console.",
            "- Kiểm tra OAuth consent screen > Audience/Test users và thêm đúng email bạn đang đăng nhập.",
            "- Kiểm tra Data Access / Scopes có youtube.upload và youtube.readonly.",
            "- Kiểm tra APIs & Services > Enabled APIs có YouTube Data API v3.",
            "- Xóa token cũ và authenticate lại sau khi sửa xong.",
            "",
            "Raw error:",
            raw_error,
        ]
        return "\n".join(lines)

    def get_channel_info(self) -> Dict[str, str]:
        service = self._build_service()
        response = service.channels().list(part="snippet", mine=True).execute()
        items = response.get("items", [])
        if not items:
            raise RuntimeError("Không lấy được thông tin channel từ YouTube API.")
        snippet = items[0].get("snippet", {})
        return {
            "channel_id": items[0].get("id", ""),
            "channel_title": snippet.get("title", ""),
        }

    def process_jobs(
        self,
        jobs: List[YouTubeUploadJob],
        max_workers: int = 2,
        poll_interval: int = 15,
        timeout_seconds: int = 1800,
        callback: Optional[Callable[[Dict[str, object]], None]] = None,
    ) -> List[YouTubeUploadResult]:
        if not jobs:
            return []

        results: List[YouTubeUploadResult] = []
        max_workers = max(1, min(max_workers, len(jobs)))

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {
                executor.submit(self._process_single_job, job, poll_interval, timeout_seconds, callback): job
                for job in jobs
            }
            for future in as_completed(future_map):
                job = future_map[future]
                try:
                    result = future.result()
                except Exception as error:
                    result = YouTubeUploadResult(
                        job_id=job.job_id,
                        video_path=job.video_path,
                        title=job.title,
                        privacy_status=job.privacy_status,
                        success=False,
                        error=str(error),
                        started_at=datetime.now().isoformat(),
                        finished_at=datetime.now().isoformat(),
                        manifest_path=job.manifest_path,
                        tracklist_path=job.tracklist_path,
                    )
                    if callback:
                        callback({"job_id": job.job_id, "stage": "error", "message": str(error)})
                results.append(result)
        return sorted(results, key=lambda item: item.job_id)

    def _process_single_job(
        self,
        job: YouTubeUploadJob,
        poll_interval: int,
        timeout_seconds: int,
        callback: Optional[Callable[[Dict[str, object]], None]],
    ) -> YouTubeUploadResult:
        service = self._build_service()
        channel_info = self.get_channel_info()
        started_at = datetime.now().isoformat()

        if callback:
            callback({"job_id": job.job_id, "stage": "uploading", "message": f"Uploading {Path(job.video_path).name}"})

        video_id = self._upload_video(service, job, callback)

        if callback:
            callback({"job_id": job.job_id, "stage": "processing", "message": f"Polling processing for {video_id}"})

        poll_data = self._poll_processing(service, video_id, poll_interval, timeout_seconds, callback, job.job_id)

        result = YouTubeUploadResult(
            job_id=job.job_id,
            video_path=job.video_path,
            title=job.title,
            privacy_status=job.privacy_status,
            success=poll_data["processing_status"] in {"succeeded", ""} and poll_data["upload_status"] not in {"failed", "rejected"},
            video_id=video_id,
            watch_url=f"https://www.youtube.com/watch?v={video_id}",
            studio_url=f"https://studio.youtube.com/video/{video_id}/edit",
            upload_status=poll_data["upload_status"],
            processing_status=poll_data["processing_status"],
            processing_failure_reason=poll_data["processing_failure_reason"],
            channel_title=channel_info.get("channel_title", ""),
            started_at=started_at,
            finished_at=datetime.now().isoformat(),
            manifest_path=job.manifest_path,
            tracklist_path=job.tracklist_path,
        )
        self._update_manifest(job, result)
        if callback:
            callback({"job_id": job.job_id, "stage": "done", "message": f"Done {video_id}", "result": asdict(result)})
        return result

    def _upload_video(self, service, job: YouTubeUploadJob, callback=None) -> str:
        deps = _import_google_deps()
        media = deps["MediaFileUpload"](job.video_path, chunksize=-1, resumable=True)
        request = service.videos().insert(
            part="snippet,status",
            body={
                "snippet": {
                    "title": job.title,
                    "description": job.description,
                    "tags": job.tags,
                    "categoryId": job.category_id,
                },
                "status": {
                    "privacyStatus": job.privacy_status,
                },
            },
            media_body=media,
        )

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status and callback:
                callback(
                    {
                        "job_id": job.job_id,
                        "stage": "upload_progress",
                        "message": f"{job.title}: {status.progress() * 100:.1f}%",
                    }
                )
        return response["id"]

    def _poll_processing(self, service, video_id, poll_interval, timeout_seconds, callback, job_id):
        deadline = time.time() + timeout_seconds
        last_state = {"upload_status": "", "processing_status": "", "processing_failure_reason": ""}

        while time.time() < deadline:
            response = service.videos().list(part="status,processingDetails,snippet", id=video_id).execute()
            items = response.get("items", [])
            if not items:
                raise RuntimeError(f"Không tìm thấy video sau khi upload: {video_id}")

            item = items[0]
            status = item.get("status", {})
            processing = item.get("processingDetails", {})
            upload_status = status.get("uploadStatus", "")
            processing_status = processing.get("processingStatus", "")
            failure_reason = processing.get("processingFailureReason", "")

            current = {
                "upload_status": upload_status,
                "processing_status": processing_status,
                "processing_failure_reason": failure_reason,
            }
            last_state = current

            if callback:
                progress = processing.get("processingProgress", {})
                progress_msg = ""
                if progress:
                    parts_total = progress.get("partsTotal") or 0
                    parts_processed = progress.get("partsProcessed") or 0
                    if parts_total:
                        progress_msg = f" ({parts_processed}/{parts_total})"
                callback(
                    {
                        "job_id": job_id,
                        "stage": "poll",
                        "message": f"{video_id}: upload={upload_status}, processing={processing_status}{progress_msg}",
                    }
                )

            if upload_status in {"failed", "rejected"}:
                return current
            if processing_status in {"succeeded", "failed", "terminated"}:
                return current
            if upload_status == "processed" and not processing_status:
                return current

            time.sleep(poll_interval)

        return last_state

    def _update_manifest(self, job: YouTubeUploadJob, result: YouTubeUploadResult) -> None:
        if not job.manifest_path:
            return
        manifest_path = Path(job.manifest_path)
        if not manifest_path.exists():
            return

        try:
            with open(manifest_path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            history = payload.get("youtube_upload_history", [])
            history.append(asdict(result))
            payload["youtube_upload_history"] = history
            payload["latest_youtube_upload"] = asdict(result)
            with open(manifest_path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def _build_service(self):
        deps = _import_google_deps()
        credentials = self._load_credentials()
        return deps["build"]("youtube", "v3", credentials=credentials, cache_discovery=False)

    def _load_credentials(self):
        deps = _import_google_deps()
        if not self.token_path.exists():
            raise RuntimeError("Chưa có token OAuth. Hãy authenticate trước.")
        creds = deps["Credentials"].from_authorized_user_file(str(self.token_path), self.scopes)
        if creds.expired and creds.refresh_token:
            creds.refresh(deps["Request"]())
            self._save_credentials(creds)
        if not creds.valid:
            raise RuntimeError("OAuth token không hợp lệ. Hãy authenticate lại.")
        return creds

    def _save_credentials(self, creds) -> None:
        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.token_path, "w", encoding="utf-8") as handle:
            handle.write(creds.to_json())
