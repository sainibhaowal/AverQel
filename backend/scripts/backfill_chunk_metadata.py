import asyncio
import logging

from sqlalchemy import select

from app.documents.models.document_chunk import DocumentChunk
from app.platform.database.session import get_session_factory

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def extract_latest_header(content: str) -> str | None:
    """Finds the last markdown header in the chunk content."""
    lines = content.split("\n")
    headers = [line.strip() for line in lines if line.startswith("# ") or line.startswith("## ")]
    return headers[-1] if headers else None


async def backfill_metadata():
    logger.info("Starting chunk metadata backfill...")
    db = get_session_factory()()
    try:
        # Fetch all chunks
        stmt = select(DocumentChunk).order_by(DocumentChunk.document_id, DocumentChunk.chunk_index)
        chunks = db.scalars(stmt).all()

        updated_count = 0
        current_header = None
        current_doc = None

        for chunk in chunks:
            if current_doc != chunk.document_id:
                current_doc = chunk.document_id
                current_header = "PROSE"

            metadata = dict(chunk.chunk_metadata) if chunk.chunk_metadata else {}
            needs_update = False

            # Extract header from this chunk or inherit from previous
            found_header = extract_latest_header(chunk.content)
            if found_header:
                current_header = found_header

            if "header_1" not in metadata or metadata["header_1"] != current_header:
                metadata["header_1"] = current_header
                needs_update = True

            expected_page = (chunk.chunk_index // 4) + 1
            if metadata.get("page_number") != expected_page:
                metadata["page_number"] = expected_page
                needs_update = True

            if needs_update:
                chunk.chunk_metadata = metadata
                updated_count += 1

        if updated_count > 0:
            logger.info(f"Committing {updated_count} updated chunks...")
            db.commit()
        else:
            logger.info("No chunks needed updating. Existing data is fine.")

        logger.info("Backfill complete.")
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(backfill_metadata())
