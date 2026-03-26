from __future__ import annotations

import io
import time
from typing import Optional, Dict, Any, List, Tuple

from src.services.pricing.cost_tracker import CostTracker
from src.tools.file_generation.image_generator_tool import ImageGeneratorTool


class ImageGenerationService:
    def __init__(self, tenant_id: int, user_id: int, job_id: str) -> None:
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.job_id = job_id
        self.tracker = CostTracker()

    async def text_to_image(
        self,
        prompt: str,
        images: Optional[List[Tuple[str, bytes]]] = None,
        generation_config: Optional[Dict[str, Any]] = None,
        safety_settings: Optional[Dict[str, Any]] = None,
        number_of_images: int = 1,
        negative_prompt: Optional[str] = None,
        seed: Optional[int] = None,
    ) -> Dict[str, Any]:
        # Pricing: API call + data-in + compute
        req_bytes = len(prompt.encode("utf-8"))
        if images:
            req_bytes += sum(len(b) for _, b in images)
        await self.tracker.record_api_call(self.job_id, "google_gemini_2_5_flash_image")
        if req_bytes > 0:
            await self.tracker.record_data_transfer(self.job_id, mb_in=req_bytes / (1024 * 1024))

        # Use production-ready Vertex AI tool path that saves to GCS/BigQuery
        start = time.monotonic()
        ref_bytes: Optional[List[bytes]] = None
        if images:
            ref_bytes = [b for _, b in images]

        tool = ImageGeneratorTool(
            tenant_id=str(self.tenant_id),
            agent_id="gemini_image_service",
            job_id=self.job_id,
            user_id=str(self.user_id),
            project_id=None,
        )
        assets = await tool.generate_image(
            prompt=prompt,
            reference_images=ref_bytes,
            negative_prompt=negative_prompt,
            number_of_images=number_of_images,
            seed=seed,
            description=f"Generated from job {self.job_id}",
            tags=["image", "ai", "gemini-2.5-flash-image"],
        )
        duration_ms = int((time.monotonic() - start) * 1000)
        await self.tracker.record_compute_time_ms(self.job_id, duration_ms)

        return {
            "duration_seconds": duration_ms / 1000.0,
            "safety": None,
            "safety_ratings": None,
            "assets": assets,
        }


