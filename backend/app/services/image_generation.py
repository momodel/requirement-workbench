from __future__ import annotations

import asyncio
import base64
import json
import mimetypes
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from ..config import AppSettings, DEFAULT_SETTINGS
from ..models import ProviderIssue


@dataclass(slots=True)
class GeneratedImageOutput:
    title: str
    summary: str
    prompt: str
    image_path: Path
    content_type: str
    provider_url: str | None = None
    metadata: dict[str, Any] | None = None


class ApimartImageGenerationService:
    def __init__(self, settings: AppSettings = DEFAULT_SETTINGS):
        self.settings = settings

    def ensure_available(self) -> None:
        missing = []
        if not self.settings.apimart_api_key:
            missing.append("APIMART_API_KEY")
        if not self.settings.apimart_base_url:
            missing.append("APIMART_BASE_URL")
        if not self.settings.apimart_image_model:
            missing.append("APIMART_IMAGE_MODEL")
        if missing:
            raise ProviderIssue(
                provider="APIMART_IMAGE",
                message=f"图像生成未配置：缺少 {', '.join(missing)}。",
                status_code=503,
            )

    async def generate(
        self,
        *,
        project_id: str,
        artifact_id: str,
        title: str,
        summary: str,
        prompt: str,
        size: str | None = None,
        resolution: str | None = None,
        n: int | None = None,
        quality: str | None = None,
        style: str | None = None,
        reference_image_urls: list[str] | None = None,
        extra_parameters: dict[str, Any] | None = None,
        output_dir: Path | None = None,
    ) -> GeneratedImageOutput:
        return await asyncio.to_thread(
            self._generate_sync,
            project_id=project_id,
            artifact_id=artifact_id,
            title=title,
            summary=summary,
            prompt=prompt,
            size=size,
            resolution=resolution,
            n=n,
            quality=quality,
            style=style,
            reference_image_urls=reference_image_urls,
            extra_parameters=extra_parameters,
            output_dir=output_dir,
        )

    def _generate_sync(
        self,
        *,
        project_id: str,
        artifact_id: str,
        title: str,
        summary: str,
        prompt: str,
        size: str | None,
        resolution: str | None,
        n: int | None,
        quality: str | None,
        style: str | None,
        reference_image_urls: list[str] | None,
        extra_parameters: dict[str, Any] | None,
        output_dir: Path | None,
    ) -> GeneratedImageOutput:
        self.ensure_available()
        cleaned_prompt = prompt.strip()
        if not cleaned_prompt:
            raise ProviderIssue(provider="APIMART_IMAGE", message="图像生成 prompt 不能为空。", status_code=422)

        payload: dict[str, Any] = {
            "model": self.settings.apimart_image_model,
            "prompt": cleaned_prompt,
        }
        if n is not None:
            payload["n"] = max(1, min(int(n), 4))
        if size:
            payload["size"] = size
        if resolution:
            payload["resolution"] = resolution
        if quality:
            payload["quality"] = quality
        if style:
            payload["style"] = style
        if reference_image_urls:
            payload["image_urls"] = reference_image_urls
        if extra_parameters:
            payload.update({key: value for key, value in extra_parameters.items() if value is not None})

        task_payload = self._request_json("POST", "/v1/images/generations", payload)
        task_id = self._extract_task_id(task_payload)
        if task_id:
            result_payload = self._poll_task(task_id)
        else:
            result_payload = task_payload

        image_url = self._extract_image_url(result_payload)
        image_b64 = self._extract_image_base64(result_payload)
        image_dir = output_dir or self.settings.projects_dir / project_id / "artifacts" / "visual_mockup" / artifact_id
        image_dir.mkdir(parents=True, exist_ok=True)

        if image_url:
            image_bytes, content_type = self._download_image(image_url)
        elif image_b64:
            image_bytes = base64.b64decode(image_b64)
            content_type = "image/png"
        else:
            raise ProviderIssue(provider="APIMART_IMAGE", message="图像生成完成但没有返回图片 URL 或 base64。", status_code=502)

        extension = mimetypes.guess_extension(content_type.split(";", 1)[0]) or ".png"
        image_path = image_dir / f"image{extension}"
        image_path.write_bytes(image_bytes)
        return GeneratedImageOutput(
            title=title.strip() or "交互视觉稿",
            summary=summary.strip() or "已生成交互视觉稿。",
            prompt=cleaned_prompt,
            image_path=image_path,
            content_type=content_type,
            provider_url=image_url,
            metadata={"request": payload, "task_id": task_id, "provider_result": result_payload},
        )

    def _request_json(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        url = urljoin(self.settings.apimart_base_url.rstrip("/") + "/", path.lstrip("/"))
        request_body: bytes | None = None
        if payload is not None:
            request_body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=request_body,
            headers={
                "Authorization": f"Bearer {self.settings.apimart_api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "requirement-workbench/0.2",
            },
            method=method,
        )
        try:
            with urllib.request.urlopen(
                request,
                timeout=self.settings.image_generation_request_timeout_seconds,
            ) as response:
                raw = response.read().decode("utf-8").strip()
        except urllib.error.HTTPError as exc:
            raw_error = exc.read().decode("utf-8", errors="replace")
            raise ProviderIssue(
                provider="APIMART_IMAGE",
                message=f"图像生成接口返回错误：{raw_error[:1000]}",
                status_code=exc.code if exc.code >= 400 else 502,
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ProviderIssue(
                provider="APIMART_IMAGE",
                message=f"图像生成接口调用失败：{exc}",
                status_code=502,
            ) from exc
        try:
            result = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ProviderIssue(provider="APIMART_IMAGE", message=f"图像生成接口返回了非 JSON 内容：{raw[:500]}", status_code=502) from exc
        if isinstance(result, dict) and result.get("code") not in {None, 0, 200, "0", "200"}:
            raise ProviderIssue(provider="APIMART_IMAGE", message=f"图像生成接口返回错误：{json.dumps(result, ensure_ascii=False)}", status_code=502)
        if not isinstance(result, dict):
            raise ProviderIssue(provider="APIMART_IMAGE", message="图像生成接口返回格式不是对象。", status_code=502)
        return result

    def _poll_task(self, task_id: str) -> dict[str, Any]:
        deadline = time.monotonic() + self.settings.image_generation_timeout_seconds
        latest_payload: dict[str, Any] = {}
        while time.monotonic() < deadline:
            latest_payload = self._request_json("GET", f"/v1/tasks/{task_id}")
            status = str(self._deep_get(latest_payload, ["data", "status"]) or latest_payload.get("status") or "").lower()
            if status in {"succeeded", "success", "completed", "complete", "done"} or self._extract_image_url(latest_payload) or self._extract_image_base64(latest_payload):
                return latest_payload
            if status in {"failed", "error", "cancelled", "canceled"}:
                raise ProviderIssue(provider="APIMART_IMAGE", message=f"图像生成任务失败：{json.dumps(latest_payload, ensure_ascii=False)}", status_code=502)
            time.sleep(self.settings.image_generation_poll_interval_seconds)
        raise ProviderIssue(provider="APIMART_IMAGE", message="图像生成任务超时。", status_code=504)

    def _download_image(self, url: str) -> tuple[bytes, str]:
        try:
            request = urllib.request.Request(
                url,
                headers={"User-Agent": "requirement-workbench/0.2"},
                method="GET",
            )
            with urllib.request.urlopen(
                request,
                timeout=self.settings.image_generation_request_timeout_seconds,
            ) as response:
                content_type = response.headers.get_content_type() or "image/png"
                return response.read(), content_type
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ProviderIssue(provider="APIMART_IMAGE", message=f"下载生成图片失败：{exc}", status_code=502) from exc

    @staticmethod
    def _deep_get(payload: Any, path: list[str]) -> Any:
        current: Any = payload
        for key in path:
            if isinstance(current, list) and key.isdigit():
                index = int(key)
                if index >= len(current):
                    return None
                current = current[index]
                continue
            if not isinstance(current, dict):
                return None
            current = current.get(key)
        return current

    @classmethod
    def _extract_task_id(cls, payload: dict[str, Any]) -> str | None:
        for path in (["task_id"], ["id"], ["data", "task_id"], ["data", "id"]):
            value = cls._deep_get(payload, list(path))
            if isinstance(value, str) and value:
                return value
        return cls._find_first_task_id(payload)

    @classmethod
    def _find_first_task_id(cls, value: Any) -> str | None:
        if isinstance(value, dict):
            raw = value.get("task_id")
            if isinstance(raw, str) and raw:
                return raw
            for child in value.values():
                found = cls._find_first_task_id(child)
                if found:
                    return found
        if isinstance(value, list):
            for child in value:
                found = cls._find_first_task_id(child)
                if found:
                    return found
        return None

    @classmethod
    def _extract_image_url(cls, payload: dict[str, Any]) -> str | None:
        candidates = [
            cls._deep_get(payload, ["data", "result", "images", "0", "url", "0"]),
            cls._deep_get(payload, ["data", "result", "images", "0", "url"]),
            cls._deep_get(payload, ["data", "images", "0", "url", "0"]),
            cls._deep_get(payload, ["data", "0", "url"]),
            cls._deep_get(payload, ["url"]),
        ]
        # _deep_get 不支持 list index，下面用递归扫描兜底。
        for value in candidates:
            if isinstance(value, str) and value.startswith("http"):
                return value
        return cls._find_first_url(payload)

    @classmethod
    def _extract_image_base64(cls, payload: dict[str, Any]) -> str | None:
        return cls._find_first_base64(payload)

    @classmethod
    def _find_first_url(cls, value: Any) -> str | None:
        if isinstance(value, str) and value.startswith("http"):
            return value
        if isinstance(value, dict):
            for child in value.values():
                found = cls._find_first_url(child)
                if found:
                    return found
        if isinstance(value, list):
            for child in value:
                found = cls._find_first_url(child)
                if found:
                    return found
        return None

    @classmethod
    def _find_first_base64(cls, value: Any) -> str | None:
        if isinstance(value, dict):
            for key in ("b64_json", "base64", "image_base64"):
                raw = value.get(key)
                if isinstance(raw, str) and raw:
                    return raw
            for child in value.values():
                found = cls._find_first_base64(child)
                if found:
                    return found
        if isinstance(value, list):
            for child in value:
                found = cls._find_first_base64(child)
                if found:
                    return found
        return None
