#!/usr/bin/env python3
import asyncio
import logging
import os
import time
from pathlib import Path

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:1000")
ADMIN_EMAIL = "admin@vaultrun.com"
ADMIN_PASSWORD = "super-secret-password-12345678"  # Should match test fixtures or local db

# Example vision costs per page
VISION_COST_PER_PAGE_USD = 0.005
OCR_COST_PER_PAGE_USD = 0.001


async def get_auth_token(client: httpx.AsyncClient) -> str:
    response = await client.post(
        f"{API_BASE_URL}/api/v1/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    if response.status_code != 200:
        logger.error(f"Login failed: {response.text}")
        raise RuntimeError("Failed to authenticate for benchmaring")
    return response.json()["access_token"]


async def process_document(client: httpx.AsyncClient, token: str, file_path: Path) -> dict:
    start_time = time.perf_counter()
    headers = {"Authorization": f"Bearer {token}"}

    with open(file_path, "rb") as f:
        files = {"file": (file_path.name, f, "application/pdf")}
        logger.info(f"[{file_path.name}] Uploading...")
        response = await client.post(
            f"{API_BASE_URL}/api/v1/documents/upload", headers=headers, files=files
        )

    if response.status_code != 200:
        logger.error(f"[{file_path.name}] Upload failed: {response.text}")
        return {"status": "failed"}

    doc_id = response.json()["document_id"]
    logger.info(f"[{file_path.name}] Uploaded ({doc_id}). Waiting for indexing...")

    # Poll status
    attempts = 0
    while attempts < 60:
        await asyncio.sleep(2)
        attempts += 1
        res = await client.get(f"{API_BASE_URL}/api/v1/documents/{doc_id}/status", headers=headers)
        if res.status_code == 200:
            data = res.json()
            if data["status"] in ("indexed", "failed", "dead_lettered"):
                latency = time.perf_counter() - start_time
                logger.info(
                    f"[{file_path.name}] Finished with status: {data['status']} in {latency:.2f}s"
                )
                data["latency_seconds"] = latency
                return data

    logger.warning(f"[{file_path.name}] Timed out waiting for indexing.")
    return {"status": "timeout"}


async def main():
    target_dir = Path(__file__).resolve().parents[2] / "Docs" / "Documents"
    if not target_dir.exists():
        logger.error(f"Directory {target_dir} not found.")
        return

    pdf_files = list(target_dir.glob("*.pdf"))
    if not pdf_files:
        logger.warning(f"No PDFs found in {target_dir}.")
        return

    logger.info(f"Found {len(pdf_files)} PDFs. Starting benchmark...")

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            token = await get_auth_token(client)
        except Exception as e:
            logger.error(f"Check if API is running: {e}")
            return

        tasks = [process_document(client, token, path) for path in pdf_files]
        results = await asyncio.gather(*tasks)

    # Analyze output
    total_latency = 0.0
    total_cost = 0.0
    success_count = 0
    ocr_hit = 0
    vision_hit = 0

    for res in results:
        if res.get("status") == "indexed":
            success_count += 1
            total_latency += res.get("latency_seconds", 0)
            if res.get("extraction_ocr_used"):
                ocr_hit += 1
            if res.get("extraction_vision_used"):
                vision_hit += 1

            # Naive cost calculation (assuming 15 pages avg per doc if page count unknown)
            # In production, pages would be fetched from the DB
            pages = 10  # Example estimate
            if res.get("extraction_vision_used"):
                total_cost += VISION_COST_PER_PAGE_USD * pages
            elif res.get("extraction_ocr_used"):
                total_cost += OCR_COST_PER_PAGE_USD * pages

    logger.info("=========================================")
    logger.info("        BENCHMARK RESULTS SUMMARY        ")
    logger.info("=========================================")
    logger.info(f"Total documents processed: : {len(results)}")
    logger.info(f"Successfully indexed       : {success_count}")
    logger.info(f"Documents requiring OCR    : {ocr_hit}")
    logger.info(f"Documents requiring Vision : {vision_hit}")
    if success_count > 0:
        logger.info(f"Average Pipeline Latency : {total_latency / success_count:.2f} seconds/doc")
    logger.info(f"Estimated Extraction Cost: ${total_cost:.4f}")
    logger.info("=========================================")


if __name__ == "__main__":
    asyncio.run(main())
