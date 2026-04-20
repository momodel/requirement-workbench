#!/usr/bin/env python3
"""
Notebook Library Management for NotebookLM
Manages a library of NotebookLM notebooks with metadata
Based on the MCP server implementation
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime


sys.path.insert(0, str(Path(__file__).parent))

from config import DATA_DIR, LIBRARY_FILE


class NotebookLibrary:
    """Manages a collection of NotebookLM notebooks with metadata"""

    def __init__(self):
        """Initialize the notebook library"""
        # Notebook 元数据必须跟认证态共用同一个项目级 data dir，
        # 否则会出现“已经登录成功，但 notebook 库是另一份空目录”的假状态。
        self.data_dir = DATA_DIR
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.library_file = LIBRARY_FILE
        self.notebooks: Dict[str, Dict[str, Any]] = {}
        self.active_notebook_id: Optional[str] = None

        # Load existing library
        self._load_library()

    def _load_library(self):
        """Load library from disk"""
        if self.library_file.exists():
            try:
                with open(self.library_file, 'r') as f:
                    data = json.load(f)
                    self.notebooks = data.get('notebooks', {})
                    self.active_notebook_id = data.get('active_notebook_id')
            except Exception as e:
                print(f"⚠️ Error loading library: {e}")
                self.notebooks = {}
                self.active_notebook_id = None
        else:
            self._save_library()

    def _save_library(self):
        """Save library to disk"""
        try:
            data = {
                'notebooks': self.notebooks,
                'active_notebook_id': self.active_notebook_id,
                'updated_at': datetime.now().isoformat()
            }
            with open(self.library_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"❌ Error saving library: {e}")

    @staticmethod
    def _slugify(value: str) -> str:
        normalized = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
        return normalized or "notebook"

    @staticmethod
    def _extract_notebook_id_from_url(url: str) -> Optional[str]:
        match = re.search(r"/notebook/([^/?#]+)", url)
        return match.group(1).strip() if match else None

    def _build_notebook_id(self, url: str, name: str) -> str:
        base_id = self._extract_notebook_id_from_url(url) or self._slugify(name)
        if base_id not in self.notebooks:
            return base_id

        counter = 2
        while f"{base_id}-{counter}" in self.notebooks:
            counter += 1
        return f"{base_id}-{counter}"

    def register_notebook(
        self,
        url: str,
        name: str,
        description: str,
        topics: List[str],
        content_types: Optional[List[str]] = None,
        use_cases: Optional[List[str]] = None,
        tags: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Add a new notebook to the library

        Args:
            url: NotebookLM notebook URL
            name: Display name for the notebook
            description: What's in this notebook
            topics: Topics covered
            content_types: Types of content (optional)
            use_cases: When to use this notebook (optional)
            tags: Additional tags for organization (optional)

        Returns:
            The created notebook object
        """
        notebook_id = self._build_notebook_id(url, name)

        # Create notebook object
        notebook = {
            'id': notebook_id,
            'url': url,
            'name': name,
            'description': description,
            'topics': topics,
            'content_types': content_types or [],
            'use_cases': use_cases or [],
            'tags': tags or [],
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat(),
            'use_count': 0,
            'last_used': None
        }

        # Add to library
        self.notebooks[notebook_id] = notebook

        # Set as active if it's the first notebook
        if len(self.notebooks) == 1:
            self.active_notebook_id = notebook_id

        self._save_library()
        return notebook

    def add_notebook(
        self,
        url: str,
        name: str,
        description: str,
        topics: List[str],
        content_types: Optional[List[str]] = None,
        use_cases: Optional[List[str]] = None,
        tags: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        return self.register_notebook(
            url=url,
            name=name,
            description=description,
            topics=topics,
            content_types=content_types,
            use_cases=use_cases,
            tags=tags,
        )

    def _click_create_notebook(self, page) -> None:
        candidates = (
            "Create new notebook",
            "Create new",
        )
        for label in candidates:
            try:
                page.get_by_text(label, exact=True).first.click(timeout=5000)
                return
            except Exception:
                continue

        clicked = page.evaluate(
            """
            () => {
              const nodes = [...document.querySelectorAll('button, [role="button"], a, div, span')];
              const match = nodes.find((node) => {
                const text = (node.innerText || node.textContent || '').replace(/\\s+/g, ' ').trim();
                return text === 'Create new notebook' || text === 'Create new';
              });
              if (!match) return false;
              match.click();
              return true;
            }
            """
        )
        if not clicked:
            raise RuntimeError("未找到 Create new notebook 按钮。")

    def _create_notebook_via_browser(self, preferred_name: Optional[str], headless: bool) -> str:
        from patchright.sync_api import sync_playwright

        from auth_manager import AuthManager
        from browser_utils import BrowserFactory

        auth = AuthManager()
        if not auth.is_authenticated():
            raise RuntimeError("NotebookLM 还没有完成项目内认证。请先执行 auth_manager.py setup。")

        playwright = None
        context = None
        try:
            playwright = sync_playwright().start()
            context = BrowserFactory.launch_persistent_context(playwright, headless=headless)
            page = context.new_page()
            page.goto("https://notebooklm.google.com/", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_url(re.compile(r"^https://notebooklm\.google\.com/"), timeout=15000)

            self._click_create_notebook(page)
            page.wait_for_url(re.compile(r"^https://notebooklm\.google\.com/notebook/"), timeout=20000)

            # 这里先只保证 notebook 真创建成功并拿到稳定 URL。
            # 重命名可以后续增强，但不影响项目级 notebook 绑定和查询能力。
            return page.url
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

    def create_notebook(
        self,
        name: str,
        description: str,
        topics: Optional[List[str]] = None,
        content_types: Optional[List[str]] = None,
        use_cases: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        headless: bool = True,
    ) -> Dict[str, Any]:
        notebook_url = self._create_notebook_via_browser(name, headless=headless)
        return self.register_notebook(
            url=notebook_url,
            name=name,
            description=description,
            topics=topics or [],
            content_types=content_types,
            use_cases=use_cases,
            tags=tags,
        )

    def remove_notebook(self, notebook_id: str) -> bool:
        """
        Remove a notebook from the library

        Args:
            notebook_id: ID of notebook to remove

        Returns:
            True if removed, False if not found
        """
        if notebook_id in self.notebooks:
            del self.notebooks[notebook_id]

            # Clear active if it was removed
            if self.active_notebook_id == notebook_id:
                self.active_notebook_id = None
                # Set new active if there are other notebooks
                if self.notebooks:
                    self.active_notebook_id = list(self.notebooks.keys())[0]

            self._save_library()
            return True

        return False

    def update_notebook(
        self,
        notebook_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        topics: Optional[List[str]] = None,
        content_types: Optional[List[str]] = None,
        use_cases: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        url: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Update notebook metadata

        Args:
            notebook_id: ID of notebook to update
            Other args: Fields to update (None = keep existing)

        Returns:
            Updated notebook object
        """
        if notebook_id not in self.notebooks:
            raise ValueError(f"Notebook not found: {notebook_id}")

        notebook = self.notebooks[notebook_id]

        # Update fields if provided
        if name is not None:
            notebook['name'] = name
        if description is not None:
            notebook['description'] = description
        if topics is not None:
            notebook['topics'] = topics
        if content_types is not None:
            notebook['content_types'] = content_types
        if use_cases is not None:
            notebook['use_cases'] = use_cases
        if tags is not None:
            notebook['tags'] = tags
        if url is not None:
            notebook['url'] = url

        notebook['updated_at'] = datetime.now().isoformat()

        self._save_library()
        return notebook

    def get_notebook(self, notebook_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific notebook by ID"""
        return self.notebooks.get(notebook_id)

    def list_notebooks(self) -> List[Dict[str, Any]]:
        """List all notebooks in the library"""
        return list(self.notebooks.values())

    def search_notebooks(self, query: str) -> List[Dict[str, Any]]:
        """
        Search notebooks by query

        Args:
            query: Search query (searches name, description, topics, tags)

        Returns:
            List of matching notebooks
        """
        query_lower = query.lower()
        results = []

        for notebook in self.notebooks.values():
            # Search in various fields
            searchable = [
                notebook['name'].lower(),
                notebook['description'].lower(),
                ' '.join(notebook['topics']).lower(),
                ' '.join(notebook['tags']).lower(),
                ' '.join(notebook.get('use_cases', [])).lower()
            ]

            if any(query_lower in field for field in searchable):
                results.append(notebook)

        return results

    def select_notebook(self, notebook_id: str) -> Dict[str, Any]:
        """
        Set a notebook as active

        Args:
            notebook_id: ID of notebook to activate

        Returns:
            The activated notebook
        """
        if notebook_id not in self.notebooks:
            raise ValueError(f"Notebook not found: {notebook_id}")

        self.active_notebook_id = notebook_id
        self._save_library()

        notebook = self.notebooks[notebook_id]
        return notebook

    def get_active_notebook(self) -> Optional[Dict[str, Any]]:
        """Get the currently active notebook"""
        if self.active_notebook_id:
            return self.notebooks.get(self.active_notebook_id)
        return None

    def increment_use_count(self, notebook_id: str) -> Dict[str, Any]:
        """
        Increment usage counter for a notebook

        Args:
            notebook_id: ID of notebook that was used

        Returns:
            Updated notebook
        """
        if notebook_id not in self.notebooks:
            raise ValueError(f"Notebook not found: {notebook_id}")

        notebook = self.notebooks[notebook_id]
        notebook['use_count'] += 1
        notebook['last_used'] = datetime.now().isoformat()

        self._save_library()
        return notebook

    def get_stats(self) -> Dict[str, Any]:
        """Get library statistics"""
        total_notebooks = len(self.notebooks)
        total_topics = set()
        total_use_count = 0

        for notebook in self.notebooks.values():
            total_topics.update(notebook['topics'])
            total_use_count += notebook['use_count']

        # Find most used
        most_used = None
        if self.notebooks:
            most_used = max(
                self.notebooks.values(),
                key=lambda n: n['use_count']
            )

        return {
            'total_notebooks': total_notebooks,
            'total_topics': len(total_topics),
            'total_use_count': total_use_count,
            'active_notebook': self.get_active_notebook(),
            'most_used_notebook': most_used,
            'library_path': str(self.library_file)
        }


def main():
    """Command-line interface for notebook management"""
    parser = argparse.ArgumentParser(description='Manage NotebookLM library')

    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # Add command
    add_parser = subparsers.add_parser('add', help='Add a notebook')
    add_parser.add_argument('--url', required=True, help='NotebookLM URL')
    add_parser.add_argument('--name', required=True, help='Display name')
    add_parser.add_argument('--description', required=True, help='Description')
    add_parser.add_argument('--topics', required=True, help='Comma-separated topics')
    add_parser.add_argument('--use-cases', help='Comma-separated use cases')
    add_parser.add_argument('--tags', help='Comma-separated tags')
    add_parser.add_argument('--json', action='store_true', help='Output notebook as JSON')

    # Create command
    create_parser = subparsers.add_parser('create', help='Create and register a notebook')
    create_parser.add_argument('--name', required=True, help='Display name')
    create_parser.add_argument('--description', required=True, help='Description')
    create_parser.add_argument('--topics', required=True, help='Comma-separated topics')
    create_parser.add_argument('--use-cases', help='Comma-separated use cases')
    create_parser.add_argument('--tags', help='Comma-separated tags')
    create_parser.add_argument('--json', action='store_true', help='Output notebook as JSON')
    create_parser.add_argument('--show-browser', action='store_true', help='Show browser during creation')

    # List command
    subparsers.add_parser('list', help='List all notebooks')
    list_parser = subparsers.choices['list']
    list_parser.add_argument('--json', action='store_true', help='Output notebooks as JSON')

    # Search command
    search_parser = subparsers.add_parser('search', help='Search notebooks')
    search_parser.add_argument('--query', required=True, help='Search query')

    # Activate command
    activate_parser = subparsers.add_parser('activate', help='Set active notebook')
    activate_parser.add_argument('--id', required=True, help='Notebook ID')

    # Remove command
    remove_parser = subparsers.add_parser('remove', help='Remove a notebook')
    remove_parser.add_argument('--id', required=True, help='Notebook ID')

    # Stats command
    subparsers.add_parser('stats', help='Show library statistics')

    args = parser.parse_args()

    # Initialize library
    library = NotebookLibrary()

    # Execute command
    if args.command == 'add':
        topics = [t.strip() for t in args.topics.split(',')]
        use_cases = [u.strip() for u in args.use_cases.split(',')] if args.use_cases else None
        tags = [t.strip() for t in args.tags.split(',')] if args.tags else None

        notebook = library.add_notebook(
            url=args.url,
            name=args.name,
            description=args.description,
            topics=topics,
            use_cases=use_cases,
            tags=tags
        )
        if args.json:
            print(json.dumps(notebook, indent=2))
        else:
            print(f"✅ Added notebook: {notebook['name']} ({notebook['id']})")

    elif args.command == 'create':
        topics = [t.strip() for t in args.topics.split(',')]
        use_cases = [u.strip() for u in args.use_cases.split(',')] if args.use_cases else None
        tags = [t.strip() for t in args.tags.split(',')] if args.tags else None

        notebook = library.create_notebook(
            name=args.name,
            description=args.description,
            topics=topics,
            use_cases=use_cases,
            tags=tags,
            headless=not args.show_browser,
        )
        if args.json:
            print(json.dumps(notebook, indent=2))
        else:
            print(f"✅ Created notebook: {notebook['name']} ({notebook['id']})")

    elif args.command == 'list':
        notebooks = library.list_notebooks()
        if args.json:
            print(json.dumps(notebooks, indent=2))
        elif notebooks:
            print("\n📚 Notebook Library:")
            for notebook in notebooks:
                active = " [ACTIVE]" if notebook['id'] == library.active_notebook_id else ""
                print(f"\n  📓 {notebook['name']}{active}")
                print(f"     ID: {notebook['id']}")
                print(f"     Topics: {', '.join(notebook['topics'])}")
                print(f"     Uses: {notebook['use_count']}")
        else:
            print("📚 Library is empty. Add notebooks with: notebook_manager.py add")

    elif args.command == 'search':
        results = library.search_notebooks(args.query)
        if results:
            print(f"\n🔍 Found {len(results)} notebooks:")
            for notebook in results:
                print(f"\n  📓 {notebook['name']} ({notebook['id']})")
                print(f"     {notebook['description']}")
        else:
            print(f"🔍 No notebooks found for: {args.query}")

    elif args.command == 'activate':
        notebook = library.select_notebook(args.id)
        print(f"Now using: {notebook['name']}")

    elif args.command == 'remove':
        if library.remove_notebook(args.id):
            print("Notebook removed from library")
        else:
            print(f"⚠️ Notebook not found: {args.id}")

    elif args.command == 'stats':
        stats = library.get_stats()
        print("\n📊 Library Statistics:")
        print(f"  Total notebooks: {stats['total_notebooks']}")
        print(f"  Total topics: {stats['total_topics']}")
        print(f"  Total uses: {stats['total_use_count']}")
        if stats['active_notebook']:
            print(f"  Active: {stats['active_notebook']['name']}")
        if stats['most_used_notebook']:
            print(f"  Most used: {stats['most_used_notebook']['name']} ({stats['most_used_notebook']['use_count']} uses)")
        print(f"  Library path: {stats['library_path']}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
