#!/usr/bin/env python3
"""
Notebook source ingestion for project-bound NotebookLM notebooks.
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Optional


sys.path.insert(0, str(Path(__file__).parent))

from notebook_manager import NotebookLibrary


class NotebookSourceManager:
    def _resolve_notebook_url(
        self,
        notebook_url: str | None,
        notebook_id: str | None,
    ) -> str:
        if notebook_url:
            return notebook_url

        if notebook_id:
            notebook = NotebookLibrary().get_notebook(notebook_id)
            if not notebook:
                raise RuntimeError(f"Notebook not found: {notebook_id}")
            return str(notebook["url"])

        active = NotebookLibrary().get_active_notebook()
        if not active:
            raise RuntimeError("未提供 notebook_url / notebook_id，且当前没有 active notebook。")
        return str(active["url"])

    @staticmethod
    def _with_add_source(url: str) -> str:
        return f"{url}&addSource=true" if "?" in url else f"{url}?addSource=true"

    @staticmethod
    def _extract_source_count(text: str) -> Optional[int]:
        match = re.search(r"(\d+)\s+source(?:s)?", text)
        return int(match.group(1)) if match else None

    @staticmethod
    def _body_text(page) -> str:
        return page.evaluate("() => document.body.innerText")

    def _open_notebook(self, page, notebook_url: str) -> int:
        page.goto(self._with_add_source(notebook_url), wait_until="domcontentloaded", timeout=30000)
        page.wait_for_url(re.compile(r"^https://notebooklm\.google\.com/notebook/"), timeout=20000)
        page.wait_for_timeout(3000)
        return self._extract_source_count(self._body_text(page)) or 0

    def _wait_for_source_added(self, page, baseline_count: int, markers: list[str], timeout_seconds: int = 120) -> None:
        deadline = time.time() + timeout_seconds
        lowered_markers = [marker.lower() for marker in markers if marker]
        while time.time() < deadline:
            text = self._body_text(page)
            count = self._extract_source_count(text) or 0
            lowered_text = text.lower()
            if count > baseline_count:
                return
            if lowered_markers and any(marker in lowered_text for marker in lowered_markers):
                return
            time.sleep(2)
        raise RuntimeError("等待 NotebookLM 完成 source 导入超时。")

    def upload_file(
        self,
        *,
        file_path: str,
        notebook_url: str | None = None,
        notebook_id: str | None = None,
        source_name: str | None = None,
        headless: bool = True,
    ) -> dict:
        from patchright.sync_api import sync_playwright
        from auth_manager import AuthManager
        from browser_utils import BrowserFactory

        auth = AuthManager()
        if not auth.is_authenticated():
            raise RuntimeError("NotebookLM 还没有完成项目内认证。请先执行 auth_manager.py setup。")

        target_url = self._resolve_notebook_url(notebook_url, notebook_id)
        source_path = Path(file_path).expanduser().resolve()
        if not source_path.exists():
            raise RuntimeError(f"待上传文件不存在：{source_path}")

        playwright = None
        context = None
        try:
            playwright = sync_playwright().start()
            context = BrowserFactory.launch_persistent_context(playwright, headless=headless)
            page = context.new_page()
            baseline = self._open_notebook(page, target_url)
            upload_button = page.get_by_text("Upload files", exact=True).first
            upload_triggered = False
            try:
                with page.expect_file_chooser(timeout=5000) as chooser_info:
                    upload_button.click(timeout=5000)
                chooser_info.value.set_files(str(source_path))
                upload_triggered = True
            except Exception:
                pass

            if not upload_triggered:
                page.wait_for_timeout(1000)
                file_input = page.query_selector("input[type=file]")
                if not file_input:
                    raise RuntimeError("未找到 NotebookLM 的文件上传输入框。")
                file_input.set_input_files(str(source_path))
            markers = [source_name or source_path.name, source_path.stem]
            self._wait_for_source_added(page, baseline, markers)
            return {
                "status": "uploaded",
                "notebook_url": target_url,
                "file_path": str(source_path),
                "source_name": source_name or source_path.name,
            }
        finally:
            if context:
                try:
                    context.close()
                except Exception:
                    pass
            if playwright:
                try:
                    playwright.stop()
                except Exception:
                    pass

    def upload_url(
        self,
        *,
        source_url: str,
        notebook_url: str | None = None,
        notebook_id: str | None = None,
        headless: bool = True,
    ) -> dict:
        from patchright.sync_api import sync_playwright
        from auth_manager import AuthManager
        from browser_utils import BrowserFactory

        auth = AuthManager()
        if not auth.is_authenticated():
            raise RuntimeError("NotebookLM 还没有完成项目内认证。请先执行 auth_manager.py setup。")

        target_url = self._resolve_notebook_url(notebook_url, notebook_id)
        playwright = None
        context = None
        try:
            playwright = sync_playwright().start()
            context = BrowserFactory.launch_persistent_context(playwright, headless=headless)
            page = context.new_page()
            baseline = self._open_notebook(page, target_url)
            page.get_by_text("Websites", exact=True).first.click(timeout=5000)
            page.locator("textarea[aria-label='Enter URLs']").first.fill(source_url)
            page.get_by_text("Insert", exact=True).first.click(timeout=5000)
            self._wait_for_source_added(page, baseline, [source_url])
            return {
                "status": "uploaded",
                "notebook_url": target_url,
                "source_url": source_url,
            }
        finally:
            if context:
                try:
                    context.close()
                except Exception:
                    pass
            if playwright:
                try:
                    playwright.stop()
                except Exception:
                    pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage NotebookLM notebook sources")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    upload_file_parser = subparsers.add_parser("upload-file", help="Upload a file source")
    upload_file_parser.add_argument("--file-path", required=True, help="Local file path")
    upload_file_parser.add_argument("--notebook-url", help="NotebookLM notebook URL")
    upload_file_parser.add_argument("--notebook-id", help="Notebook ID from library")
    upload_file_parser.add_argument("--source-name", help="Display name for wait heuristics")
    upload_file_parser.add_argument("--show-browser", action="store_true", help="Show browser during upload")
    upload_file_parser.add_argument("--json", action="store_true", help="Output JSON result")

    upload_url_parser = subparsers.add_parser("upload-url", help="Upload a website/YouTube URL")
    upload_url_parser.add_argument("--source-url", required=True, help="URL to import")
    upload_url_parser.add_argument("--notebook-url", help="NotebookLM notebook URL")
    upload_url_parser.add_argument("--notebook-id", help="Notebook ID from library")
    upload_url_parser.add_argument("--show-browser", action="store_true", help="Show browser during upload")
    upload_url_parser.add_argument("--json", action="store_true", help="Output JSON result")

    args = parser.parse_args()
    manager = NotebookSourceManager()

    if args.command == "upload-file":
        result = manager.upload_file(
            file_path=args.file_path,
            notebook_url=args.notebook_url,
            notebook_id=args.notebook_id,
            source_name=args.source_name,
            headless=not args.show_browser,
        )
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"✅ Uploaded file source: {result['source_name']}")
        return

    if args.command == "upload-url":
        result = manager.upload_url(
            source_url=args.source_url,
            notebook_url=args.notebook_url,
            notebook_id=args.notebook_id,
            headless=not args.show_browser,
        )
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"✅ Uploaded URL source: {result['source_url']}")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
