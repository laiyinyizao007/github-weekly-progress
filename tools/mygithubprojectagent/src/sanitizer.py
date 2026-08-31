"""Sanitization engine for removing sensitive information from code."""

import hashlib
import re
from typing import Dict, List, Optional, Set

from src.config import PrivacyConfig
from src.patterns import SensitivePattern, pattern_registry


class Sanitizer:
    """Sanitizes sensitive information from text content."""

    def __init__(self, config: Optional[PrivacyConfig] = None):
        """Initialize sanitizer with configuration.

        Args:
            config: Privacy configuration. Uses defaults if None.
        """
        self.config = config or PrivacyConfig()
        self.registry = pattern_registry
        self._redaction_cache: Dict[str, str] = {}

    def _get_enabled_types(self) -> List[str]:
        """Get list of enabled sanitizer types from config."""
        types = []
        if self.config.sanitize_api_keys:
            types.append("api_key")
        if self.config.sanitize_passwords:
            types.append("password")
        if self.config.sanitize_tokens:
            types.append("token")
        if self.config.sanitize_secrets:
            types.append("secret")
        if self.config.sanitize_emails:
            types.append("email")
        return types

    def _redact_value(self, value: str, pattern_type: str) -> str:
        """Redact a sensitive value according to configured style.

        Args:
            value: The sensitive value to redact
            pattern_type: Type of sensitive data

        Returns:
            Redacted value
        """
        cache_key = f"{value}:{pattern_type}:{self.config.redaction_style}"
        if cache_key in self._redaction_cache:
            return self._redaction_cache[cache_key]

        if self.config.redaction_style == "remove":
            result = ""
        elif self.config.redaction_style == "hash":
            # Create a short hash that identifies the value without revealing it
            hash_val = hashlib.sha256(value.encode()).hexdigest()[:8]
            result = f"<{pattern_type.upper()}_HASH_{hash_val}>"
        else:  # mask (default)
            if pattern_type == "email":
                # Partial mask for emails: u***@e***.com
                result = self._mask_email(value)
            else:
                # Full mask for other sensitive data
                result = f"***REDACTED_{pattern_type.upper()}***"

        self._redaction_cache[cache_key] = result
        return result

    def _mask_email(self, email: str) -> str:
        """Partially mask an email address.

        Args:
            email: Email address to mask

        Returns:
            Masked email like u***@e***.com
        """
        parts = email.split("@")
        if len(parts) != 2:
            return "***REDACTED_EMAIL***"

        user, domain = parts
        domain_parts = domain.split(".")

        # Mask username: keep first char
        masked_user = user[0] + "***" if len(user) > 1 else "***"

        # Mask domain: keep first char of first part
        if domain_parts:
            masked_domain = domain_parts[0][0] + "***"
            if len(domain_parts) > 1:
                masked_domain += "." + ".".join(domain_parts[1:])
        else:
            masked_domain = "***"

        return f"{masked_user}@{masked_domain}"

    def sanitize(self, content: str) -> str:
        """Sanitize sensitive information from content.

        Args:
            content: Text content to sanitize

        Returns:
            Sanitized content with sensitive info redacted
        """
        enabled_types = self._get_enabled_types()
        if not enabled_types:
            return content

        detections = self.registry.detect(content, enabled_types)
        if not detections:
            return content

        # Apply redactions from end to start to preserve positions
        result = content
        for detection in reversed(detections):
            start = detection["start"]
            end = detection["end"]
            pattern_type = detection["pattern_type"]
            match_text = detection["match"]

            # Determine what to replace with
            redacted = self._redact_value(match_text, pattern_type)

            # Replace in result
            result = result[:start] + redacted + result[end:]

        return result

    def sanitize_file(
        self,
        file_path: str,
        content: str,
        is_config_file: bool = False,
    ) -> str:
        """Sanitize a file with special handling for config files.

        Args:
            file_path: Path of the file (for detection)
            content: File content
            is_config_file: Whether this is known to be a config file

        Returns:
            Sanitized content
        """
        # Detect config files by name
        config_file_indicators = [
            ".env",
            "config",
            "secret",
            "credential",
            "key",
            "token",
            "password",
        ]

        lower_path = file_path.lower()
        detected_config = any(indicator in lower_path for indicator in config_file_indicators)

        if is_config_file or detected_config:
            # For config files, apply more aggressive sanitization
            return self._sanitize_config_file(content)

        return self.sanitize(content)

    def _sanitize_config_file(self, content: str) -> str:
        """Apply aggressive sanitization to config files.

        Args:
            content: Config file content

        Returns:
            Sanitized content
        """
        lines = content.split("\n")
        result_lines = []

        for line in lines:
            stripped = line.strip()

            # Skip comments and empty lines
            if not stripped or stripped.startswith("#") or stripped.startswith("//"):
                result_lines.append(line)
                continue

            # Check for key=value patterns that look sensitive
            sensitive_keys = [
                r"(?i)^\s*(api[_-]?key|apikey)",
                r"(?i)^\s*(password|passwd|pwd)",
                r"(?i)^\s*(token|auth_token|access_token)",
                r"(?i)^\s*(secret|secret_key)",
                r"(?i)^\s*(private[_-]?key)",
                r"(?i)^\s*(client[_-]?secret)",
                r"(?i)^\s*(aws[_-]?access[_-]?key[_-]?id)",
                r"(?i)^\s*(aws[_-]?secret)",
                r"(?i)^\s*(database[_-]?url|db[_-]?url)",
            ]

            is_sensitive_line = any(
                re.search(pattern, stripped) for pattern in sensitive_keys
            )

            if is_sensitive_line:
                # Redact the entire value part
                redacted_line = re.sub(
                    r"([=:]\s*).*$",
                    r"\1***REDACTED***",
                    line,
                )
                result_lines.append(redacted_line)
            else:
                # Still apply normal sanitization
                result_lines.append(self.sanitize(line))

        return "\n".join(result_lines)

    def get_stats(self, original: str, sanitized: str) -> Dict:
        """Get sanitization statistics.

        Args:
            original: Original content
            sanitized: Sanitized content

        Returns:
            Dictionary with statistics
        """
        enabled_types = self._get_enabled_types()
        detections = self.registry.detect(original, enabled_types)

        # Count by type
        type_counts: Dict[str, int] = {}
        for d in detections:
            t = d["pattern_type"]
            type_counts[t] = type_counts.get(t, 0) + 1

        return {
            "total_detections": len(detections),
            "type_counts": type_counts,
            "content_length_before": len(original),
            "content_length_after": len(sanitized),
        }

    def scan_only(self, content: str) -> List[dict]:
        """Scan content without sanitizing (for analysis).

        Args:
            content: Content to scan

        Returns:
            List of detected sensitive items
        """
        enabled_types = self._get_enabled_types()
        return self.registry.detect(content, enabled_types)
