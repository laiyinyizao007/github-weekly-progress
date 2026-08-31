"""Tests for the sanitizer module."""

import pytest

from src.patterns import pattern_registry
from src.sanitizer import Sanitizer
from src.config import PrivacyConfig


class TestPatternDetection:
    """Test sensitive pattern detection."""

    def test_api_key_detection(self):
        """Test API key pattern detection."""
        # Test with OpenAI-style key
        content = "API_KEY = 'sk-abc123xyz78901234567890123456789012345678'"
        detections = pattern_registry.detect(content, ["api_key"])
        assert len(detections) > 0

    def test_password_detection(self):
        """Test password pattern detection."""
        content = 'password = "secret123"'
        detections = pattern_registry.detect(content, ["password"])
        assert len(detections) > 0

    def test_email_detection(self):
        """Test email pattern detection."""
        content = "Contact: user@example.com"
        detections = pattern_registry.detect(content, ["email"])
        assert len(detections) > 0

    def test_github_token_detection(self):
        """Test GitHub token detection."""
        content = "token = 'ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'"
        detections = pattern_registry.detect(content, ["token"])
        assert len(detections) > 0


class TestSanitizer:
    """Test sanitization functionality."""

    def test_mask_redaction(self):
        """Test mask redaction style."""
        config = PrivacyConfig(redaction_style="mask")
        sanitizer = Sanitizer(config)

        # Use a longer secret that matches the pattern
        content = "API_KEY = 'secret123456789012345'"
        result = sanitizer.sanitize(content)

        assert "secret123456789012345" not in result
        assert "REDACTED" in result

    def test_email_masking(self):
        """Test email partial masking."""
        config = PrivacyConfig(redaction_style="mask")
        sanitizer = Sanitizer(config)

        content = "Contact: john.doe@example.com"
        result = sanitizer.sanitize(content)

        assert "john.doe@example.com" not in result
        assert "@" in result  # Should keep @ symbol

    def test_hash_redaction(self):
        """Test hash redaction style."""
        config = PrivacyConfig(redaction_style="hash")
        sanitizer = Sanitizer(config)

        content = "password = 'secret'"
        result = sanitizer.sanitize(content)

        assert "secret" not in result
        assert "HASH" in result

    def test_no_false_positives_in_code(self):
        """Test that normal code isn't affected."""
        config = PrivacyConfig()
        sanitizer = Sanitizer(config)

        content = "def get_password_hash(password): return hash(password)"
        result = sanitizer.sanitize(content)

        # The function definition should remain
        assert "def get_password_hash" in result

    def test_config_file_sanitization(self):
        """Test special handling for config files."""
        config = PrivacyConfig()
        sanitizer = Sanitizer(config)

        content = """
DATABASE_URL=postgresql://user:password@localhost/db
API_KEY=sk-abc123
DEBUG=true
"""
        result = sanitizer.sanitize_file(".env", content)

        assert "password" not in result
        assert "sk-abc123" not in result
        assert "DEBUG=true" in result  # Non-sensitive should remain

    def test_sanitization_stats(self):
        """Test stats generation."""
        config = PrivacyConfig()
        sanitizer = Sanitizer(config)

        # Use secrets that match the patterns
        original = "API_KEY = 'secret123456789012345'\npassword = 'secret123456'"
        sanitized = sanitizer.sanitize(original)
        stats = sanitizer.get_stats(original, sanitized)

        assert stats["total_detections"] >= 2


class TestPrivacyConfig:
    """Test privacy configuration."""

    def test_default_config(self):
        """Test default configuration."""
        config = PrivacyConfig()

        assert config.sanitize_api_keys is True
        assert config.sanitize_passwords is True
        assert config.sanitize_tokens is True
        assert config.sanitize_emails is True
        assert config.sanitize_secrets is True
        assert config.redaction_style == "mask"

    def test_disabled_sanitizers(self):
        """Test with some sanitizers disabled."""
        config = PrivacyConfig(
            sanitize_api_keys=False,
            sanitize_emails=False,
        )
        sanitizer = Sanitizer(config)

        content = "API_KEY = 'secret' and email = 'test@test.com'"
        result = sanitizer.sanitize(content)

        # API key should remain (disabled)
        assert "secret" in result
        # Email should remain (disabled)
        assert "test@test.com" in result
