"""
Production-ready Image Generation Tool using Gemini 2.5 Flash Image (Nano Banana).

Supports:
- Text-to-image generation
- Image editing with reference images
- Multi-turn conversations for iterative refinement
- Character consistency across multiple images
- Interleaved text and image output

Model: gemini-2.5-flash-image-preview
Region: us-central1 (default)
"""

import os
from typing import Dict, List, Optional, Any
from io import BytesIO
import logging
import time

from .base_file_generator import BaseFileGenerator

logger = logging.getLogger(__name__)


class ImageGeneratorTool(BaseFileGenerator):
    """
    Gemini 2.5 Flash Image generation tool (Nano Banana).

    Features:
    - Native multimodal image generation
    - Prompt-based editing
    - Character consistency
    - High-quality photorealistic images
    - PNG output up to 1024px
    """

    def __init__(
        self,
        tenant_id: str,
        agent_id: str,
        job_id: str,
        user_id: Optional[str] = None,
        project_id: Optional[str] = None,
        location: str = "us-central1",
    ):
        """
        Initialize the Gemini 2.5 Flash Image generator.

        Args:
            tenant_id: Tenant ID for isolation
            agent_id: Agent creating the image
            job_id: Associated job ID
            user_id: Optional user ID
            project_id: GCP project ID
            location: GCP region (default: us-central1)
        """
        super().__init__(tenant_id, agent_id, job_id, user_id, project_id)

        self.location = location

        # Initialize the image generation model (GA)
        self.model_name = "gemini-2.5-flash-image"

        logger.info(f"Initialized Gemini 2.5 Flash Image generator: {self.model_name}")

    def _ensure_initialized(self):
        """Lazy initialization of Vertex AI."""
        import vertexai
        vertexai.init(project=self.project_id, location=self.location)

    async def generate_image(
        self,
        prompt: str,
        reference_images: Optional[List[bytes]] = None,
        negative_prompt: Optional[str] = None,
        number_of_images: int = 1,
        aspect_ratio: str = "1:1",
        seed: Optional[int] = None,
        description: str = "",
        tags: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Generate images using Gemini 2.5 Flash Image model.

        Args:
            prompt: Text description of the desired image
            reference_images: Optional list of reference images as bytes
            negative_prompt: Optional description of what to avoid
            number_of_images: Number of images to generate (1-8)
            aspect_ratio: Image aspect ratio ("1:1", "16:9", "9:16", etc.)
            seed: Optional seed for reproducibility
            description: Description for metadata
            tags: Optional tags for categorization

        Returns:
            List of dictionaries containing asset info for each generated image
        """
        try:
            # Normalize number_of_images (API supports up to 8)
            n = max(1, min(int(number_of_images), 8))

            from vertexai.generative_models import GenerativeModel, GenerationConfig, Part
            from google.api_core import exceptions as gax_exceptions
            self._ensure_initialized()

            def _build_parts() -> List[Any]:
                parts: List[Any] = []
                # Negative prompt as avoidance instruction
                if negative_prompt:
                    parts.append(Part.from_text(f"Avoid: {negative_prompt}"))
                parts.append(Part.from_text(prompt))
                # Add reference images if provided (max 3 for context)
                if reference_images:
                    for img_bytes in reference_images[:3]:
                        parts.append(Part.from_data(data=img_bytes, mime_type="image/png"))
                return parts

            def _gen_config(_seed: Optional[int]) -> Any:
                cfg = GenerationConfig(
                    response_modalities=["TEXT", "IMAGE"],
                    temperature=1.0,
                    top_p=0.95,
                )
                # Apply seed for reproducibility if provided
                if _seed is not None:
                    try:
                        cfg.seed = int(_seed)
                    except Exception:
                        pass
                return cfg

            model = GenerativeModel(model_name=self.model_name)

            generated_images: List[Dict[str, Any]] = []

            # Simple retry/backoff wrapper for rate limits
            def _call_with_retries(parts: List[Part], cfg: GenerationConfig):
                delays = [0.5, 1.0, 2.0]
                last_exc = None
                for attempt, d in enumerate([0.0] + delays):
                    if d:
                        time.sleep(d)
                    try:
                        return model.generate_content(parts, generation_config=cfg)
                    except (gax_exceptions.ResourceExhausted, gax_exceptions.TooManyRequests) as e:
                        last_exc = e
                        continue
                if last_exc:
                    raise last_exc
                raise RuntimeError("generate_content failed without exception")

            # Loop to produce up to n images
            seq = 0
            while len(generated_images) < n:
                cur_seed = (seed + seq) if seed is not None else None
                parts = _build_parts()
                cfg = _gen_config(cur_seed)
                response = _call_with_retries(parts, cfg)

                for candidate in response.candidates:
                    for part in candidate.content.parts:
                        if hasattr(part, "inline_data") and part.inline_data:
                            image_bytes = part.inline_data.data
                            mime_type = getattr(part.inline_data, "mime_type", "image/png") or "image/png"
                            # Derive extension from mime
                            ext = "png" if "png" in mime_type else ("jpg" if "jpeg" in mime_type or "jpg" in mime_type else "png")
                            filename = f"generated_image_{len(generated_images) + 1}.{ext}"

                            asset_info = await self.save_asset(
                                file_bytes=image_bytes,
                                filename=filename,
                                mime_type=mime_type,
                                description=description or f"Generated from prompt: {prompt[:100]}",
                                tags=tags or ["ai-generated", "gemini-2.5-flash-image"],
                                metadata={
                                    "prompt": prompt,
                                    "negative_prompt": negative_prompt,
                                    "aspect_ratio": aspect_ratio,
                                    "seed": cur_seed,
                                    "model": self.model_name,
                                    "generation_method": "text-to-image",
                                },
                            )

                            generated_images.append(asset_info)
                            if len(generated_images) >= n:
                                break
                    if len(generated_images) >= n:
                        break
                seq += 1

            logger.info(f"Successfully generated {len(generated_images)} images")
            return generated_images

        except Exception as e:
            logger.error(f"Error generating image: {e}", exc_info=True)
            raise

    async def edit_image(
        self,
        base_image_bytes: bytes,
        edit_prompt: str,
        description: str = "",
        tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Edit an existing image using Gemini 2.5 Flash Image.

        Args:
            base_image_bytes: The base image to edit
            edit_prompt: Description of the desired edit
            description: Description for metadata
            tags: Optional tags

        Returns:
            Dictionary containing asset info for the edited image
        """
        try:
            from vertexai.generative_models import GenerativeModel, GenerationConfig, Part
            self._ensure_initialized()

            generation_config = GenerationConfig(
                response_modalities=["TEXT", "IMAGE"],
            )
            model = GenerativeModel(model_name=self.model_name)

            # Create parts with image and edit instruction
            parts = [
                Part.from_data(data=base_image_bytes, mime_type="image/png"),
                Part.from_text(edit_prompt),
            ]

            response = model.generate_content(parts)

            # Extract the edited image
            for candidate in response.candidates:
                for part in candidate.content.parts:
                    if hasattr(part, "inline_data") and part.inline_data:
                        edited_image_bytes = part.inline_data.data
                        mime_type = getattr(part.inline_data, "mime_type", "image/png") or "image/png"
                        ext = "png" if "png" in mime_type else ("jpg" if "jpeg" in mime_type or "jpg" in mime_type else "png")
                        filename = f"edited_image_{self.job_id}.{ext}"

                        asset_info = await self.save_asset(
                            file_bytes=edited_image_bytes,
                            filename=filename,
                            mime_type=mime_type,
                            description=description or f"Edited: {edit_prompt[:100]}",
                            tags=tags or ["ai-edited", "gemini-2.5-flash-image"],
                            metadata={
                                "edit_prompt": edit_prompt,
                                "model": self.model_name,
                                "generation_method": "image-editing",
                            },
                        )

                        logger.info(f"Successfully edited image: {filename}")
                        return asset_info

            raise Exception("No edited image returned by model")

        except Exception as e:
            logger.error(f"Error editing image: {e}", exc_info=True)
            raise

    async def generate_with_style_reference(
        self,
        prompt: str,
        style_image_bytes: bytes,
        description: str = "",
        tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Generate an image with a specific style reference.

        Args:
            prompt: Text description of the desired content
            style_image_bytes: Reference image for style transfer
            description: Description for metadata
            tags: Optional tags

        Returns:
            Dictionary containing asset info for the generated image
        """
        try:
            from vertexai.generative_models import GenerativeModel, GenerationConfig, Part
            self._ensure_initialized()

            generation_config = GenerationConfig(
                response_modalities=["TEXT", "IMAGE"],
                temperature=1.0,
                top_p=0.95,
            )

            model = GenerativeModel(
                model_name=self.model_name, generation_config=generation_config
            )

            # Combine style instruction with prompt
            style_prompt = f"Generate an image with this style: [STYLE REFERENCE]. Content: {prompt}"

            parts = [
                Part.from_data(data=style_image_bytes, mime_type="image/png"),
                Part.from_text(style_prompt),
            ]

            response = model.generate_content(parts)

            # Extract the generated image
            for candidate in response.candidates:
                for part in candidate.content.parts:
                    if hasattr(part, "inline_data") and part.inline_data:
                        image_bytes = part.inline_data.data
                        mime_type = getattr(part.inline_data, "mime_type", "image/png") or "image/png"
                        ext = "png" if "png" in mime_type else ("jpg" if "jpeg" in mime_type or "jpg" in mime_type else "png")
                        filename = f"styled_image_{self.job_id}.{ext}"

                        asset_info = await self.save_asset(
                            file_bytes=image_bytes,
                            filename=filename,
                            mime_type=mime_type,
                            description=description
                            or f"Style transfer: {prompt[:100]}",
                            tags=tags
                            or [
                                "ai-generated",
                                "style-transfer",
                                "google-ai-generative-model",
                            ],
                            metadata={
                                "prompt": prompt,
                                "model": self.model_name,
                                "generation_method": "style-transfer",
                            },
                        )

                        logger.info(f"Successfully generated styled image: {filename}")
                        return asset_info

            raise Exception("No image returned by model")

        except Exception as e:
            logger.error(f"Error generating styled image: {e}", exc_info=True)
            raise

    async def generate_variations(
        self,
        base_image_bytes: bytes,
        num_variations: int = 3,
        variation_strength: float = 0.5,
        description: str = "",
        tags: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Generate variations of an existing image.

        Args:
            base_image_bytes: The base image to create variations from
            num_variations: Number of variations to generate
            variation_strength: Strength of variation (0.0-1.0)
            description: Description for metadata
            tags: Optional tags

        Returns:
            List of dictionaries containing asset info for each variation
        """
        try:
            from vertexai.generative_models import GenerativeModel, GenerationConfig, Part
            from google.api_core import exceptions as gax_exceptions
            self._ensure_initialized()

            variations = []

            for i in range(num_variations):
                generation_config = GenerationConfig(
                    response_modalities=["TEXT", "IMAGE"],
                    temperature=variation_strength,
                )

                model = GenerativeModel(model_name=self.model_name)

                parts = [
                    Part.from_data(data=base_image_bytes, mime_type="image/png"),
                    Part.from_text(
                        f"Create a variation of this image, maintaining the core concept but with different details."
                    ),
                ]

                # Retry on rate limits
                def _call_with_retries(parts):
                    delays = [0.5, 1.0, 2.0]
                    last_exc = None
                    for d in [0.0] + delays:
                        if d:
                            time.sleep(d)
                        try:
                            return model.generate_content(parts, generation_config=generation_config)
                        except (gax_exceptions.ResourceExhausted, gax_exceptions.TooManyRequests) as e:
                            last_exc = e
                            continue
                    if last_exc:
                        raise last_exc
                    raise RuntimeError("generate_content failed without exception")

                response = _call_with_retries(parts)

                # Extract the variation
                for candidate in response.candidates:
                    for part in candidate.content.parts:
                        if hasattr(part, "inline_data") and part.inline_data:
                            image_bytes = part.inline_data.data
                            mime_type = getattr(part.inline_data, "mime_type", "image/png") or "image/png"
                            ext = "png" if "png" in mime_type else ("jpg" if "jpeg" in mime_type or "jpg" in mime_type else "png")
                            filename = f"variation_{i + 1}_{self.job_id}.{ext}"

                            asset_info = await self.save_asset(
                                file_bytes=image_bytes,
                                filename=filename,
                                mime_type=mime_type,
                                description=description or f"Variation {i + 1}",
                                tags=tags
                                or [
                                    "ai-generated",
                                    "variation",
                                    "gemini-2.5-flash-image",
                                ],
                                metadata={
                                    "variation_number": i + 1,
                                    "variation_strength": variation_strength,
                                    "model": self.model_name,
                                    "generation_method": "variation",
                                },
                            )

                            variations.append(asset_info)
                            break

            logger.info(f"Successfully generated {len(variations)} variations")

            return variations

        except Exception as e:
            logger.error(f"Error generating variations: {e}", exc_info=True)
            raise
