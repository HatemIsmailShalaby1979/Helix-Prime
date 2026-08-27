"""
Notion Adapter for B2B Onboarding Automator

This module provides integration with Notion for documentation management.
It handles page creation, database synchronization, and content management.
"""

import logging
from dataclasses import dataclass
from typing import Any

import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class NotionPage:
    """Notion page data structure."""

    id: str
    title: str
    content: str
    url: str
    created_time: str
    last_edited_time: str
    parent_id: str | None = None
    archived: bool = False
    properties: dict[str, Any] = None


@dataclass
class NotionDatabase:
    """Notion database data structure."""

    id: str
    title: str
    description: str
    url: str
    properties: dict[str, Any]
    created_time: str


class NotionAdapter:
    """
    Notion adapter for B2B Onboarding Automator.

    This class provides integration with Notion for:
    - Page creation and management
    - Database synchronization
    - Content management
    - API integration
    """

    def __init__(self, api_key: str, database_id: str | None = None):
        self.api_key = api_key
        self.database_id = database_id
        self.base_url = "https://api.notion.com/v1"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28",
        }
        self.logger = logging.getLogger(__name__)

    def create_page(
        self,
        title: str,
        content: str,
        parent_id: str | None = None,
        properties: dict[str, Any] | None = None,
    ) -> NotionPage:
        """
        Create a new page in Notion.

        Args:
            title: Page title
            content: Page content (Markdown format)
            parent_id: Parent page ID (optional)
            properties: Additional page properties (optional)

        Returns:
            Created NotionPage object
        """
        url = f"{self.base_url}/pages"

        # Prepare page data
        page_data = {
            "parent": {"type": "page_id", "page_id": parent_id}
            if parent_id
            else {"type": "workspace"},
            "properties": {"title": [{"type": "text", "text": {"content": title}}]},
            "children": self._convert_markdown_to_blocks(content),
        }

        if properties:
            page_data["properties"].update(properties)

        # Make API request
        response = requests.post(url, headers=self.headers, json=page_data)

        if response.status_code == 200:
            page_data = response.json()
            notion_page = self._parse_page_response(page_data)
            self.logger.info(f"Created page: {title} (ID: {notion_page.id})")
            return notion_page
        else:
            self.logger.error(f"Failed to create page: {response.text}")
            raise Exception(f"Failed to create page: {response.text}")

    def create_database(
        self,
        title: str,
        description: str,
        properties: dict[str, Any],
        parent_id: str | None = None,
    ) -> NotionDatabase:
        """
        Create a new database in Notion.

        Args:
            title: Database title
            description: Database description
            properties: Database properties
            parent_id: Parent page ID (optional)

        Returns:
            Created NotionDatabase object
        """
        url = f"{self.base_url}/databases"

        # Prepare database data
        database_data = {
            "parent": {"type": "page_id", "page_id": parent_id}
            if parent_id
            else {"type": "workspace"},
            "title": [{"type": "text", "text": {"content": title}}],
            "description": [{"type": "text", "text": {"content": description}}],
            "properties": properties,
        }

        # Make API request
        response = requests.post(url, headers=self.headers, json=database_data)

        if response.status_code == 200:
            database_data = response.json()
            notion_database = self._parse_database_response(database_data)
            self.logger.info(f"Created database: {title} (ID: {notion_database.id})")
            return notion_database
        else:
            self.logger.error(f"Failed to create database: {response.text}")
            raise Exception(f"Failed to create database: {response.text}")

    def get_page(self, page_id: str) -> NotionPage:
        """
        Get a page by ID.

        Args:
            page_id: Page ID

        Returns:
            NotionPage object
        """
        url = f"{self.base_url}/pages/{page_id}"

        # Make API request
        response = requests.get(url, headers=self.headers)

        if response.status_code == 200:
            page_data = response.json()
            return self._parse_page_response(page_data)
        else:
            self.logger.error(f"Failed to get page: {response.text}")
            raise Exception(f"Failed to get page: {response.text}")

    def update_page(
        self, page_id: str, title: str | None = None, content: str | None = None
    ) -> NotionPage:
        """
        Update a page.

        Args:
            page_id: Page ID
            title: New title (optional)
            content: New content (optional)

        Returns:
            Updated NotionPage object
        """
        url = f"{self.base_url}/pages/{page_id}"

        # Get current page data
        page = self.get_page(page_id)

        # Prepare update data
        update_data = {"properties": page.properties}

        if title:
            update_data["properties"]["title"] = [
                {"type": "text", "text": {"content": title}}
            ]

        if content:
            update_data["children"] = self._convert_markdown_to_blocks(content)

        # Make API request
        response = requests.patch(url, headers=self.headers, json=update_data)

        if response.status_code == 200:
            page_data = response.json()
            return self._parse_page_response(page_data)
        else:
            self.logger.error(f"Failed to update page: {response.text}")
            raise Exception(f"Failed to update page: {response.text}")

    def archive_page(self, page_id: str) -> bool:
        """
        Archive a page.

        Args:
            page_id: Page ID

        Returns:
            True if successful, False otherwise
        """
        url = f"{self.base_url}/pages/{page_id}"

        # Prepare archive data
        archive_data = {"archived": True}

        # Make API request
        response = requests.patch(url, headers=self.headers, json=archive_data)

        if response.status_code == 200:
            self.logger.info(f"Archived page: {page_id}")
            return True
        else:
            self.logger.error(f"Failed to archive page: {response.text}")
            return False

    def query_database(
        self,
        database_id: str,
        filter: dict[str, Any] | None = None,
        sorts: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Query a database.

        Args:
            database_id: Database ID
            filter: Filter conditions (optional)
            sorts: Sort conditions (optional)

        Returns:
            List of database results
        """
        url = f"{self.base_url}/databases/{database_id}/query"

        # Prepare query data
        query_data = {}

        if filter:
            query_data["filter"] = filter

        if sorts:
            query_data["sorts"] = sorts

        # Make API request
        response = requests.post(url, headers=self.headers, json=query_data)

        if response.status_code == 200:
            return response.json().get("results", [])
        else:
            self.logger.error(f"Failed to query database: {response.text}")
            raise Exception(f"Failed to query database: {response.text}")

    def _convert_markdown_to_blocks(self, markdown: str) -> list[dict[str, Any]]:
        """
        Convert Markdown content to Notion blocks.

        Args:
            markdown: Markdown content

        Returns:
            List of Notion blocks
        """
        blocks = []

        # Simple Markdown to blocks conversion
        lines = markdown.split("\n")

        for line in lines:
            if line.startswith("# "):
                # Heading 1
                blocks.append(
                    {
                        "object": "block",
                        "type": "heading_1",
                        "heading_1": {
                            "rich_text": [
                                {"type": "text", "text": {"content": line[2:]}}
                            ]
                        },
                    }
                )
            elif line.startswith("## "):
                # Heading 2
                blocks.append(
                    {
                        "object": "block",
                        "type": "heading_2",
                        "heading_2": {
                            "rich_text": [
                                {"type": "text", "text": {"content": line[3:]}}
                            ]
                        },
                    }
                )
            elif line.startswith("### "):
                # Heading 3
                blocks.append(
                    {
                        "object": "block",
                        "type": "heading_3",
                        "heading_3": {
                            "rich_text": [
                                {"type": "text", "text": {"content": line[4:]}}
                            ]
                        },
                    }
                )
            elif line.startswith("- "):
                # Bullet point
                blocks.append(
                    {
                        "object": "block",
                        "type": "bulleted_list_item",
                        "bulleted_list_item": {
                            "rich_text": [
                                {"type": "text", "text": {"content": line[2:]}}
                            ]
                        },
                    }
                )
            elif line.startswith("1. "):
                # Numbered list
                blocks.append(
                    {
                        "object": "block",
                        "type": "numbered_list_item",
                        "numbered_list_item": {
                            "rich_text": [
                                {"type": "text", "text": {"content": line[3:]}}
                            ]
                        },
                    }
                )
            elif line.startswith("```"):
                # Code block
                code_content = []
                # Find end of code block
                for i, block_line in enumerate(lines):
                    if block_line == "```":
                        code_block = "\n".join(code_content)
                        blocks.append(
                            {
                                "object": "block",
                                "type": "code",
                                "code": {
                                    "language": "plain text",
                                    "rich_text": [
                                        {
                                            "type": "text",
                                            "text": {"content": code_block},
                                        }
                                    ],
                                },
                            }
                        )
                        # Remove code block from lines
                        lines = lines[:i] + lines[i + 1 :]
                        break
                    else:
                        code_content.append(block_line)
                continue
            elif line.strip():
                # Regular paragraph
                blocks.append(
                    {
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [{"type": "text", "text": {"content": line}}]
                        },
                    }
                )
            else:
                # Empty line
                blocks.append(
                    {
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {"rich_text": []},
                    }
                )

        return blocks

    def _parse_page_response(self, page_data: dict[str, Any]) -> NotionPage:
        """
        Parse Notion page response to NotionPage object.

        Args:
            page_data: Notion API response

        Returns:
            NotionPage object
        """
        properties = page_data.get("properties", {})

        return NotionPage(
            id=page_data["id"],
            title=properties.get("title", [{"text": {"content": ""}}])[0]["text"][
                "content"
            ],
            content="",  # Content is in children
            url=page_data.get("url", ""),
            created_time=page_data.get("created_time", ""),
            last_edited_time=page_data.get("last_edited_time", ""),
            parent_id=page_data.get("parent", {}).get("page_id"),
            archived=page_data.get("archived", False),
            properties=properties,
        )

    def _parse_database_response(self, database_data: dict[str, Any]) -> NotionDatabase:
        """
        Parse Notion database response to NotionDatabase object.

        Args:
            database_data: Notion API response

        Returns:
            NotionDatabase object
        """
        title = database_data.get("title", [{"text": {"content": ""}}])[0]["text"][
            "content"
        ]

        return NotionDatabase(
            id=database_data["id"],
            title=title,
            description=database_data.get("description", [{"text": {"content": ""}}])[
                0
            ]["text"]["content"],
            url=database_data.get("url", ""),
            properties=database_data.get("properties", {}),
            created_time=database_data.get("created_time", ""),
        )

    def test_connection(self) -> bool:
        """
        Test Notion API connection.

        Returns:
            True if connection is successful, False otherwise
        """
        url = f"{self.base_url}/users/me"

        # Make API request
        response = requests.get(url, headers=self.headers)

        if response.status_code == 200:
            self.logger.info("Notion API connection test successful")
            return True
        else:
            self.logger.error(f"Notion API connection test failed: {response.text}")
            return False

    def export_page_to_markdown(self, page_id: str) -> str:
        """
        Export a page to Markdown format.

        Args:
            page_id: Page ID

        Returns:
            Markdown content
        """
        page = self.get_page(page_id)

        # Convert blocks to Markdown
        markdown = f"# {page.title}\n\n"

        # Note: In a real implementation, we would need to fetch the children
        # and convert them to Markdown format

        return markdown

    def import_markdown_to_page(
        self, title: str, markdown: str, parent_id: str | None = None
    ) -> NotionPage:
        """
        Import Markdown content to a new page.

        Args:
            title: Page title
            markdown: Markdown content
            parent_id: Parent page ID (optional)

        Returns:
            Created NotionPage object
        """
        return self.create_page(title, markdown, parent_id)


def create_notion_adapter(
    api_key: str, database_id: str | None = None
) -> NotionAdapter:
    """
    Factory function to create NotionAdapter.

    Args:
        api_key: Notion API key
        database_id: Database ID (optional)

    Returns:
        NotionAdapter instance
    """
    return NotionAdapter(api_key, database_id)


if __name__ == "__main__":
    # Example usage
    print("=== Notion Adapter ===")

    # Create adapter (using dummy API key for example)
    adapter = create_notion_adapter("dummy_api_key")

    # Test connection
    print("Testing Notion API connection...")
    if adapter.test_connection():
        print("أ¢إ“â€œ Notion API connection successful")
    else:
        print("أ¢إ“â€” Notion API connection failed")

    print("\n=== Notion Adapter Complete ===")
