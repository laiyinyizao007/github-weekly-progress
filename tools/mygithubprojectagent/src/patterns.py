"""Sensitive information detection patterns for privacy protection."""

import re
from dataclasses import dataclass
from typing import List, Pattern


@dataclass
class SensitivePattern:
    """Definition of a sensitive information pattern."""

    name: str
    pattern: Pattern[str]
    description: str
    severity: str = "high"  # low, medium, high, critical


# Common API key patterns
API_KEY_PATTERNS = [
    # Generic API keys - more lenient matching
    r"(?i)(api[_-]?key|apikey)\s*[=:]\s*['\"]([a-zA-Z0-9_\-]{8,})['\"]",
    r"(?i)(api[_-]?key|apikey)\s*=\s*([a-zA-Z0-9_\-]{8,})",
    # AWS
    r"(?i)(AKIA[0-9A-Z]{16})",
    r"(?i)(aws[_-]?secret[_-]?access[_-]?key)\s*[=:]\s*['\"]?([a-zA-Z0-9/+=]{40})['\"]?",
    # GitHub
    r"(ghp_[a-zA-Z0-9]{36})",
    r"(gho_[a-zA-Z0-9]{36})",
    r"(ghu_[a-zA-Z0-9]{36})",
    r"(ghs_[a-zA-Z0-9]{36})",
    r"(ghr_[a-zA-Z0-9]{36})",
    # Slack
    r"(xox[baprs]-[0-9a-zA-Z]{10,48})",
    # OpenAI
    r"(sk-[a-zA-Z0-9]{48})",
    r"(sk-[a-zA-Z0-9]{20,})",  # More lenient OpenAI pattern
    # Stripe
    r"(sk_live_[0-9a-zA-Z]{24})",
    r"(pk_live_[0-9a-zA-Z]{24})",
    # Google
    r"(?i)(AIza[0-9A-Za-z_\-]{35})",
    # Generic Bearer tokens
    r"(?i)(bearer\s+[a-zA-Z0-9_\-\.=]{20,})",
]

# Password patterns
PASSWORD_PATTERNS = [
    r"(?i)(password|passwd|pwd)\s*[=:]\s*['\"]([^'\"]{4,})['\"]",
    r"(?i)(password|passwd|pwd)\s*=\s*([^\s'\";]{4,})",
    r"(?i)(?<![a-z])(pass|password)(?![a-z])\s*[=:]\s*['\"]?([a-zA-Z0-9!@#$%^&*]{8,})['\"]?",
]

# Token patterns
TOKEN_PATTERNS = [
    r"(?i)(token|auth_token|access_token)\s*[=:]\s*['\"]?([a-zA-Z0-9_\-\.=]{16,})['\"]?",
    r"(?i)(oauth[_-]?token)\s*[=:]\s*['\"]?([a-zA-Z0-9_\-]{16,})['\"]?",
]

# Secret patterns
SECRET_PATTERNS = [
    r"(?i)(secret|secret_key|secretkey)\s*[=:]\s*['\"]([^'\"]{8,})['\"]",
    r"(?i)(secret|secret_key)\s*=\s*([^\s'\";]{8,})",
    r"(?i)(client[_-]?secret)\s*[=:]\s*['\"]?([a-zA-Z0-9_\-]{16,})['\"]?",
]

# Private key patterns
PRIVATE_KEY_PATTERNS = [
    r"-----BEGIN (RSA |DSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]*?-----END",
    r"(?i)(private[_-]?key)\s*[=:]\s*['\"]([^'\"]{20,})['\"]",
]

# Database connection strings (with passwords)
DATABASE_URL_PATTERNS = [
    r"(?i)(mongodb(\+srv)?://[^:]+:)([^@]+)@",
    r"(?i)(postgres(ql)?://[^:]+:)([^@]+)@",
    r"(?i)(postgresql://[^:]+:)([^@]+)@",
    r"(?i)(mysql://[^:]+:)([^@]+)@",
    r"(?i)(redis://:[^@]+@)",
]

# Email patterns (for partial masking)
EMAIL_PATTERN = r"[\w.+-]+@[\w-]+\.[\w.-]+"


class PatternRegistry:
    """Registry of all sensitive patterns."""

    def __init__(self):
        """Initialize pattern registry with default patterns."""
        self._patterns: List[SensitivePattern] = []
        self._register_default_patterns()

    def _register_default_patterns(self) -> None:
        """Register all default sensitive patterns."""
        # API Keys
        for i, pattern_str in enumerate(API_KEY_PATTERNS):
            self.add_pattern(
                SensitivePattern(
                    name=f"api_key_{i}",
                    pattern=re.compile(pattern_str),
                    description="API Key",
                    severity="critical",
                )
            )

        # Passwords
        for i, pattern_str in enumerate(PASSWORD_PATTERNS):
            self.add_pattern(
                SensitivePattern(
                    name=f"password_{i}",
                    pattern=re.compile(pattern_str),
                    description="Password",
                    severity="critical",
                )
            )

        # Tokens
        for i, pattern_str in enumerate(TOKEN_PATTERNS):
            self.add_pattern(
                SensitivePattern(
                    name=f"token_{i}",
                    pattern=re.compile(pattern_str),
                    description="Access Token",
                    severity="critical",
                )
            )

        # Secrets
        for i, pattern_str in enumerate(SECRET_PATTERNS):
            self.add_pattern(
                SensitivePattern(
                    name=f"secret_{i}",
                    pattern=re.compile(pattern_str),
                    description="Secret Key",
                    severity="critical",
                )
            )

        # Private Keys
        for i, pattern_str in enumerate(PRIVATE_KEY_PATTERNS):
            self.add_pattern(
                SensitivePattern(
                    name=f"private_key_{i}",
                    pattern=re.compile(pattern_str),
                    description="Private Key",
                    severity="critical",
                )
            )

        # Database URLs
        for i, pattern_str in enumerate(DATABASE_URL_PATTERNS):
            self.add_pattern(
                SensitivePattern(
                    name=f"database_url_{i}",
                    pattern=re.compile(pattern_str),
                    description="Database Connection String",
                    severity="critical",
                )
            )

        # Email (medium severity - partial masking)
        self.add_pattern(
            SensitivePattern(
                name="email",
                pattern=re.compile(EMAIL_PATTERN),
                description="Email Address",
                severity="medium",
            )
        )

    def add_pattern(self, pattern: SensitivePattern) -> None:
        """Add a custom pattern to the registry.

        Args:
            pattern: SensitivePattern to add
        """
        self._patterns.append(pattern)

    def get_patterns(
        self,
        enabled_types: List[str] = None,
    ) -> List[SensitivePattern]:
        """Get all registered patterns, optionally filtered.

        Args:
            enabled_types: List of pattern types to include
                (api_key, password, token, secret, email)

        Returns:
            List of matching SensitivePattern objects
        """
        if enabled_types is None:
            return self._patterns.copy()

        type_mapping = {
            "api_key": ["api_key"],
            "password": ["password"],
            "token": ["token"],
            "secret": ["secret", "private_key"],
            "email": ["email"],
        }

        enabled_prefixes = []
        for t in enabled_types:
            enabled_prefixes.extend(type_mapping.get(t, [t]))

        return [
            p for p in self._patterns
            if any(p.name.startswith(prefix) for prefix in enabled_prefixes)
        ]

    def detect(
        self,
        content: str,
        enabled_types: List[str] = None,
    ) -> List[dict]:
        """Detect sensitive information in content.

        Args:
            content: Text to scan
            enabled_types: List of pattern types to check

        Returns:
            List of detected sensitive items with position info
        """
        patterns = self.get_patterns(enabled_types)
        detections = []

        for pattern in patterns:
            for match in pattern.pattern.finditer(content):
                detections.append({
                    "pattern_name": pattern.name,
                    "pattern_type": self._get_type_from_name(pattern.name),
                    "description": pattern.description,
                    "severity": pattern.severity,
                    "match": match.group(),
                    "start": match.start(),
                    "end": match.end(),
                })

        # Sort by position
        detections.sort(key=lambda x: x["start"])
        return detections

    def _get_type_from_name(self, name: str) -> str:
        """Get the type category from pattern name.

        Args:
            name: Pattern name

        Returns:
            Type category
        """
        if name.startswith("api_key"):
            return "api_key"
        elif name.startswith("password"):
            return "password"
        elif name.startswith("token"):
            return "token"
        elif name.startswith("secret"):
            return "secret"
        elif name.startswith("private_key"):
            return "private_key"
        elif name.startswith("database"):
            return "database_url"
        elif name == "email":
            return "email"
        return "unknown"


# Global pattern registry instance
pattern_registry = PatternRegistry()
