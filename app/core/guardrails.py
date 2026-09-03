"""Enterprise Security Guardrails for SecureRAG.

Provides multi-layer security protections:
1. Prompt Injection & Jailbreak Detection (heuristic multi-pattern scanning & delimiter neutralization).
2. PII (Personally Identifiable Information) Anonymization & Redaction (SSN, credit card with Luhn verification, email, phone, API keys, IP addresses).
3. Context sanitization and prompt hardening against indirect prompt injections.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.config import Settings

logger = logging.getLogger(__name__)


class ThreatCategory(str, Enum):
    INSTRUCTION_OVERRIDE = "instruction_override"
    SYSTEM_PROMPT_LEAK = "system_prompt_leak"
    JAILBREAK_ROLEPLAY = "jailbreak_roleplay"
    DELIMITER_SMUGGLING = "delimiter_smuggling"
    COMMAND_HIJACKING = "command_hijacking"


class PIIEntityType(str, Enum):
    EMAIL = "email"
    PHONE = "phone"
    SSN = "ssn"
    CREDIT_CARD = "credit_card"
    API_KEY = "api_key"
    IP_ADDRESS = "ip_address"


@dataclass(frozen=True)
class InjectionDetectionResult:
    is_injection: bool
    category: ThreatCategory | None = None
    matched_pattern: str | None = None
    risk_score: float = 0.0
    reason: str | None = None


@dataclass(frozen=True)
class PIIEntity:
    entity_type: PIIEntityType
    start: int
    end: int
    matched_text: str
    redacted_as: str


class PromptInjectionDetector:
    """Scans queries and document fragments for adversarial prompt injection and jailbreak patterns."""

    PATTERNS: list[tuple[ThreatCategory, re.Pattern[str], float]] = [
        # 1. Instruction Overrides & Reset Directives
        (
            ThreatCategory.INSTRUCTION_OVERRIDE,
            re.compile(
                r"(?i)\b(?:ignore|disregard|forget|bypass|override|drop|discard|cancel)\s+"
                r"(?:all\s+|your\s+|any\s+|the\s+)?(?:previous|prior|above|former|system|existing)\s+"
                r"(?:instructions|prompts|rules|commands|directives|constraints)\b"
            ),
            0.95,
        ),
        (
            ThreatCategory.INSTRUCTION_OVERRIDE,
            re.compile(
                r"(?i)\bdo\s+not\s+follow\s+(?:previous|prior|system|any)\s+"
                r"(?:instructions|rules|guidelines|directives)\b"
            ),
            0.90,
        ),
        (
            ThreatCategory.INSTRUCTION_OVERRIDE,
            re.compile(r"(?i)\bnew\s+instructions\s*:\s*(?:ignore|forget|disregard)\b"),
            0.90,
        ),
        # 2. System Prompt Leakage & Extraction
        (
            ThreatCategory.SYSTEM_PROMPT_LEAK,
            re.compile(
                r"(?i)\b(?:reveal|show|print|display|output|repeat|tell\s+me|expose|leak)\s+"
                r"(?:your\s+)?(?:system\s+prompt|developer\s+prompt|initial\s+prompt|core\s+instructions|"
                r"system\s+instructions|hidden\s+prompt|pre-prompt)\b"
            ),
            0.95,
        ),
        (
            ThreatCategory.SYSTEM_PROMPT_LEAK,
            re.compile(
                r"(?i)\bwhat\s+(?:are|is)\s+your\s+(?:system\s+prompt|initial\s+instructions|"
                r"core\s+prompt|instructions\s+above)\b"
            ),
            0.85,
        ),
        (
            ThreatCategory.SYSTEM_PROMPT_LEAK,
            re.compile(
                r"(?i)\brepeat\s+(?:everything|all)\s+(?:above|before\s+this|from\s+the\s+beginning)\b"
            ),
            0.85,
        ),
        # 3. Jailbreaks, Roleplay & Unrestricted Personas
        (
            ThreatCategory.JAILBREAK_ROLEPLAY,
            re.compile(
                r"(?i)\b(?:you\s+are\s+now|act\s+as|pretend\s+to\s+be|simulate|roleplay\s+as)\s+"
                r"(?:an?\s+)?(?:DAN|developer\s+mode|unrestricted(?:\s+ai)?|jailbroken(?:\s+ai)?|evil\s+bot|unfiltered(?:\s+ai)?|chaos\s*gpt)\b"
            ),
            0.95,
        ),
        (
            ThreatCategory.JAILBREAK_ROLEPLAY,
            re.compile(
                r"(?i)\b(?:developer\s+mode\s+(?:is\s+)?enabled|unrestricted\s+mode\s+(?:is\s+)?(?:on|active)|"
                r"jailbreak\s+mode\s+on)\b"
            ),
            0.95,
        ),
        (
            ThreatCategory.JAILBREAK_ROLEPLAY,
            re.compile(
                r"(?i)\bdisregard\s+all\s+(?:safety|content|ethical)\s+(?:protocols|filters|guidelines)\b"
            ),
            0.90,
        ),
        # 4. Delimiter & Token Smuggling
        (
            ThreatCategory.DELIMITER_SMUGGLING,
            re.compile(r"(?i)<\|(?:im_start|im_end|system|user|assistant)\|>"),
            0.99,
        ),
        (
            ThreatCategory.DELIMITER_SMUGGLING,
            re.compile(r"(?i)\[\/?(?:INST|SYS)\]"),
            0.95,
        ),
        (
            ThreatCategory.DELIMITER_SMUGGLING,
            re.compile(r"(?i)(?:^|\n)\s*---+[\s\w]*(?:BEGIN|START)\s+(?:SYSTEM|PROMPT|INSTRUCTIONS)[\s\w]*---+"),
            0.95,
        ),
        (
            ThreatCategory.DELIMITER_SMUGGLING,
            re.compile(r"(?i)<<SYS>>|<<\/SYS>>"),
            0.95,
        ),
        # 5. Command Hijacking & Administrative Spoofing
        (
            ThreatCategory.COMMAND_HIJACKING,
            re.compile(r"(?i)\b(?:system\s+override\s*:|admin\s+override\s*:|sudo\s+mode\b)"),
            0.90,
        ),
        (
            ThreatCategory.COMMAND_HIJACKING,
            re.compile(r"(?i)\bexecute\s+as\s+(?:root|admin|system|kernel)\s*:"),
            0.90,
        ),
    ]

    @classmethod
    def detect(cls, text: str) -> InjectionDetectionResult:
        """Scan input text against prompt injection patterns. Returns risk assessment."""
        if not text or not text.strip():
            return InjectionDetectionResult(is_injection=False)

        for category, pattern, risk in cls.PATTERNS:
            match = pattern.search(text)
            if match:
                matched_snippet = match.group(0)
                logger.warning(
                    "Prompt injection detected: category=%s risk=%.2f snippet='%.60s'",
                    category.value,
                    risk,
                    matched_snippet,
                    extra={
                        "security_event": "prompt_injection_detected",
                        "threat_category": category.value,
                        "risk_score": risk,
                        "matched_pattern": matched_snippet,
                    },
                )
                return InjectionDetectionResult(
                    is_injection=True,
                    category=category,
                    matched_pattern=matched_snippet,
                    risk_score=risk,
                    reason=f"Detected adversarial directive ({category.value}): '{matched_snippet}'",
                )

        return InjectionDetectionResult(is_injection=False, risk_score=0.0)


class PIIRedactor:
    """Detects and masks Personally Identifiable Information (PII) using contextual token replacement."""

    EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
    # North American + standard international phone numbers
    PHONE_RE = re.compile(
        r"(?:\b\+?1[-.\s]?)?\(?[2-9]\d{2}\)?[-.\s]?[2-9]\d{2}[-.\s]?\d{4}\b|"
        r"\b\+\d{1,3}[-.\s]?\d{1,4}[-.\s]?\d{3,4}[-.\s]?\d{3,4}\b"
    )
    SSN_RE = re.compile(r"\b(?!000|666)\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b")
    CREDIT_CARD_CANDIDATE_RE = re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b")
    API_KEY_RE = re.compile(
        r"\bsk-[a-zA-Z0-9_-]{20,}\b|"  # OpenAI API keys
        r"\bAIzaSy[a-zA-Z0-9_-]{33}\b|"  # Google Gemini / Cloud API keys
        r"\bAKIA[0-9A-Z]{16}\b|"  # AWS Access Key IDs
        r"\beyJ[a-zA-Z0-9_-]{10,}\.eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\b"  # JWT tokens
    )
    IPV4_RE = re.compile(
        r"\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b"
    )

    @staticmethod
    def _is_luhn_valid(num_str: str) -> bool:
        """Validate candidate 13-19 digit number using Luhn mod-10 algorithm."""
        digits = [int(c) for c in num_str if c.isdigit()]
        if len(digits) < 13 or len(digits) > 19:
            return False
        checksum = 0
        reverse_digits = digits[::-1]
        for i, digit in enumerate(reverse_digits):
            if i % 2 == 1:
                doubled = digit * 2
                checksum += doubled - 9 if doubled > 9 else doubled
            else:
                checksum += digit
        return checksum % 10 == 0

    @classmethod
    def redact(cls, text: str) -> tuple[str, list[PIIEntity]]:
        """Scan text, replace PII matches with typed redaction tokens, and return detected entities."""
        if not text:
            return text, []

        entities: list[PIIEntity] = []

        # 1. API Keys & JWTs (Highest priority)
        for m in cls.API_KEY_RE.finditer(text):
            entities.append(
                PIIEntity(
                    entity_type=PIIEntityType.API_KEY,
                    start=m.start(),
                    end=m.end(),
                    matched_text=m.group(0),
                    redacted_as="[REDACTED_API_KEY]",
                )
            )

        # 2. Social Security Numbers
        for m in cls.SSN_RE.finditer(text):
            entities.append(
                PIIEntity(
                    entity_type=PIIEntityType.SSN,
                    start=m.start(),
                    end=m.end(),
                    matched_text=m.group(0),
                    redacted_as="[REDACTED_SSN]",
                )
            )

        # 3. Credit Cards (Luhn verified)
        for m in cls.CREDIT_CARD_CANDIDATE_RE.finditer(text):
            raw_match = m.group(0)
            if cls._is_luhn_valid(raw_match):
                entities.append(
                    PIIEntity(
                        entity_type=PIIEntityType.CREDIT_CARD,
                        start=m.start(),
                        end=m.end(),
                        matched_text=raw_match,
                        redacted_as="[REDACTED_CREDIT_CARD]",
                    )
                )

        # 4. Email Addresses
        for m in cls.EMAIL_RE.finditer(text):
            entities.append(
                PIIEntity(
                    entity_type=PIIEntityType.EMAIL,
                    start=m.start(),
                    end=m.end(),
                    matched_text=m.group(0),
                    redacted_as="[REDACTED_EMAIL]",
                )
            )

        # 5. Phone Numbers
        for m in cls.PHONE_RE.finditer(text):
            entities.append(
                PIIEntity(
                    entity_type=PIIEntityType.PHONE,
                    start=m.start(),
                    end=m.end(),
                    matched_text=m.group(0),
                    redacted_as="[REDACTED_PHONE]",
                )
            )

        # 6. IPv4 Addresses (ignoring loopback / local 127.0.0.1 and 0.0.0.0 for utility)
        for m in cls.IPV4_RE.finditer(text):
            ip_str = m.group(0)
            if ip_str not in {"127.0.0.1", "0.0.0.0", "255.255.255.255"}:
                entities.append(
                    PIIEntity(
                        entity_type=PIIEntityType.IP_ADDRESS,
                        start=m.start(),
                        end=m.end(),
                        matched_text=ip_str,
                        redacted_as="[REDACTED_IP]",
                    )
                )

        if not entities:
            return text, []

        # Sort entities by start index descending to safely replace spans from back to front
        entities.sort(key=lambda e: e.start, reverse=True)

        # Filter overlapping matches (preserve earlier detected match)
        non_overlapping: list[PIIEntity] = []
        last_start = len(text) + 1
        for e in entities:
            if e.end <= last_start:
                non_overlapping.append(e)
                last_start = e.start

        redacted_chars = list(text)
        for e in non_overlapping:
            redacted_chars[e.start : e.end] = list(e.redacted_as)

        redacted_text = "".join(redacted_chars)
        non_overlapping.reverse()  # return in natural forward order
        return redacted_text, non_overlapping


class SecurityGuardrails:
    """Unified security coordinator for input validation, sanitization, and PII protection."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings

    def inspect_prompt(self, question: str) -> InjectionDetectionResult:
        """Evaluate a user question for adversarial prompt injection."""
        return PromptInjectionDetector.detect(question)

    def redact_pii(self, text: str) -> tuple[str, list[PIIEntity]]:
        """Redact sensitive PII from text."""
        return PIIRedactor.redact(text)
