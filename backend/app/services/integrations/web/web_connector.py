import hashlib
import logging
from typing import Any
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from app.services.integrations.connector_service import ConnectorService
from app.services.integrations.health_utils import (
    ConnectorHealthStatus,
    build_health_report,
    classify_health_status,
)

logger = logging.getLogger(__name__)


class WebConnector(ConnectorService):
    """
    Web Crawler Connector.
    Fetches content from a URL and prepares it for ingestion.
    """

    def sync(self) -> dict[str, Any]:
        url = self.connector.config.get("url")
        if not url:
            return {"error": "No URL configured for web connector"}

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 AverQel-Bot/1.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }

        try:
            with httpx.Client(
                timeout=20.0, follow_redirects=True, headers=headers
            ) as client:
                response = client.get(url)
                response.raise_for_status()
                html_content = response.text

            # Parse HTML and extract main text
            soup = BeautifulSoup(html_content, "html.parser")

            # Aggressive cleanup of non-content elements
            for element in soup(
                [
                    "script",
                    "style",
                    "nav",
                    "footer",
                    "header",
                    "aside",
                    "form",
                    "iframe",
                    "button",
                ]
            ):
                element.decompose()

            # Get title and high-fidelity text
            title = (
                soup.title.string.strip() if (soup.title and soup.title.string) else url
            )

            # Focus on article or main content if available
            main_content = soup.find("main") or soup.find("article") or soup.body
            text_content = (
                main_content.get_text(separator="\n", strip=True)
                if main_content
                else soup.get_text(separator="\n", strip=True)
            )

            # Refined Intelligence Markdown
            markdown_content = f"# Intelligence Source: {title}\n\n"
            markdown_content += f"**Origin URL:** {url}\n"
            markdown_content += f"**Content Length:** {len(text_content)}\n\n"
            markdown_content += "---\n\n"
            markdown_content += text_content

            payload = markdown_content.encode("utf-8")
            content_hash = hashlib.sha256(payload).hexdigest()

            if self.connector.config.get("last_content_hash") == content_hash:
                return {
                    "status": "skipped",
                    "hash": content_hash,
                    "message": "Content is already up-to-date",
                }

            return {
                "status": "success",
                "title": title,
                "payload": markdown_content,
                "hash": content_hash,
                "filename": f"web_{url.replace('https://', '').replace('http://', '').replace('/', '_')[:30]}.md",
                "message": f"Successfully crawled and ingested: {title}",
            }

        except Exception as e:
            logger.error(f"Web Sync Failure: {e}")
            return {"status": "error", "message": f"Crawl failed: {str(e)}"}

    def validate_config(self) -> bool:
        url = self.connector.config.get("url")
        if not url:
            return False
        try:
            parsed = urlparse(url)
            if not (parsed.scheme and parsed.netloc):
                return False
            with httpx.Client(
                timeout=10.0,
                follow_redirects=True,
                headers={"User-Agent": "AverQel-Bot/1.0"},
            ) as client:
                try:
                    response = client.head(url)
                except Exception:
                    response = client.get(url)
                if response.status_code == 405:
                    response = client.get(url)
                return response.status_code < 400
        except Exception:
            return False

    def validate_health(self) -> dict[str, Any]:
        url = self.connector.config.get("url")
        if not url:
            return build_health_report(
                status="degraded",
                healthy=False,
                message="No URL configured for web connector.",
                error_code="missing_url",
                metadata={"provider": "web-crawler"},
            )
        try:
            parsed = urlparse(url)
            if not (parsed.scheme and parsed.netloc):
                return build_health_report(
                    status="degraded",
                    healthy=False,
                    message="Configured URL is invalid.",
                    error_code="invalid_url",
                    metadata={"provider": "web-crawler"},
                )
            with httpx.Client(
                timeout=10.0,
                follow_redirects=True,
                headers={"User-Agent": "AverQel-Bot/1.0"},
            ) as client:
                try:
                    response = client.head(url)
                except Exception:
                    response = client.get(url)
                if response.status_code == 405:
                    response = client.get(url)
                if response.status_code < 400:
                    return build_health_report(
                        status="healthy",
                        healthy=True,
                        http_status=response.status_code,
                        metadata={"provider": "web-crawler"},
                    )
                status: ConnectorHealthStatus = (
                    "offline" if response.status_code >= 500 else "degraded"
                )
                return build_health_report(
                    status=status,
                    healthy=False,
                    message=f"Web crawl endpoint returned {response.status_code}.",
                    error_code=f"http_{response.status_code}",
                    http_status=response.status_code,
                    metadata={"provider": "web-crawler"},
                )
        except Exception as exc:  # noqa: BLE001
            status, error_code = classify_health_status(exception=exc, message=str(exc))
            return build_health_report(
                status=status,
                healthy=False,
                message=str(exc),
                error_code=error_code,
                metadata={"provider": "web-crawler"},
            )
