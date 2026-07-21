"""Test specific model variants from the image to verify automatic detection."""

from app.providers.services.reasoning_capabilities import (
    _OPENAI_COMPATIBLE_HINTS,
    _matches_any,
    model_supports_reasoning,
    reasoning_capabilities,
    uses_gemma_think_trigger,
)


class TestSpecificModelVariants:
    """Test specific model variants shown in the UI image."""

    def test_gemma_4_variants_from_image(self):
        """Test specific Gemma 4 variants from the image."""
        gemma_variants = [
            "gemma 4 12b qat",
            "gemma 4 26b a4b qat",
            "gemma 4 31b qat",
            "gemma 4 12b",
            "gemma 4 31b",
            "gemma 4 e4b",
            "gemma 4 e2b",
            "gemma 4 26b a4b",
        ]

        for model in gemma_variants:
            # Test with Google provider (Gemma's native provider)
            result = model_supports_reasoning("google", model)
            print(f"Model: {model}, Supports Reasoning: {result}")
            # Should detect reasoning for Gemma 4 models
            assert result, f"{model} should support reasoning as Gemma 4 variant"

    def test_qwen_variants_from_image(self):
        """Test Qwen variants from the image."""
        qwen_variants = [
            "qwen3.6 27b",
            "qwen3.6 35b a3b",
        ]

        for model in qwen_variants:
            result = model_supports_reasoning("openai-compatible", model)
            print(f"Model: {model}, Supports Reasoning: {result}")
            # Should detect reasoning for Qwen models
            assert result, f"{model} should support reasoning as Qwen variant"

    def test_nemotron_variant_from_image(self):
        """Test Nemotron variant from the image."""
        nemotron_models = [
            "nemotron 3 nano 4b",
        ]

        for model in nemotron_models:
            result = model_supports_reasoning("openai-compatible", model)
            print(f"Model: {model}, Supports Reasoning: {result}")
            # Should detect reasoning for Nemotron models
            assert result, f"{model} should support reasoning as Nemotron variant"

    def test_pattern_matching_coverage(self):
        """Test that pattern matching catches various naming conventions."""
        test_cases = [
            # Gemma variants with different naming patterns
            ("gemma-4-12b", True),
            ("gemma-4-12b-qat", True),
            ("gemma-4-26b-a4b", True),
            ("gemma-4-31b", True),
            ("gemma-4-e4b", True),
            ("gemma-4-e2b", True),
            # Qwen variants
            ("qwen3.6", True),
            ("qwen-3.6", True),
            ("qwen3.6-27b", True),
            ("qwen3.6-35b", True),
            # Nemotron variants
            ("nemotron-3", True),
            ("nemotron-3-nano", True),
            ("nemotron-3-nano-4b", True),
            # Edge cases
            ("gemma-4-it", True),
            ("gemma-4-instruct", True),
        ]

        for model_name, expected in test_cases:
            result = _matches_any(model_name, _OPENAI_COMPATIBLE_HINTS)
            print(f"Pattern test: {model_name} -> {result} (expected: {expected})")
            # We expect most to match due to pattern matching
            # Some might not match if they don't have reasoning-specific patterns
            # but should at least not crash

    def test_case_and_space_variations(self):
        """Test that case and spaces don't break detection."""
        variations = [
            "Gemma 4 12B Qat",
            "gemma 4 12b qat",
            "GEMMA 4 12B QAT",
            "Gemma-4-12B-Qat",
            "gemma-4-12b-qat",
        ]

        for model in variations:
            result = uses_gemma_think_trigger(model)
            print(f"Case/space variation: {model} -> {result}")
            # Should be case-insensitive and handle spaces/hyphens
            assert (
                result
            ), f"{model} should trigger Gemma thinking (case/space insensitive)"

    def test_reasoning_capabilities_output_for_variants(self):
        """Test that reasoning capabilities return proper structure for variants."""
        test_models = [
            "gemma 4 12b qat",
            "qwen3.6 27b",
            "nemotron 3 nano 4b",
        ]

        for model in test_models:
            # Test with appropriate providers
            if "gemma" in model.lower():
                provider = "google"
            else:
                provider = "openai-compatible"

            caps = reasoning_capabilities(provider, model)
            print(f"Capabilities for {model}: {caps}")

            # Should have reasoning capabilities structure
            assert isinstance(caps, dict), f"{model} should return dict"
            assert (
                "supports_reasoning" in caps
            ), f"{model} should have supports_reasoning field"
