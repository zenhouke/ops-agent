import re
from collections.abc import Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


_REDACTED = "[REDACTED]"

_PEM_PRIVATE_KEY_PATTERN = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z0-9 ]*PRIVATE KEY-----"
)

_AUTHORIZATION_BEARER_PATTERN = re.compile(
    r"(?i)(\bAuthorization\s*:\s*Bearer\s+)([^\s,;]+)"
)

_SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"(['\"]?\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|bearer[_-]?token|refresh[_-]?token|id[_-]?token|client[_-]?secret|secret[_-]?key|private[_-]?key|token|secret)\b['\"]?\s*[:=]\s*)(['\"])((?:\\.|(?!\2).)*)(\2)"
    r"|(['\"]?\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|bearer[_-]?token|refresh[_-]?token|id[_-]?token|client[_-]?secret|secret[_-]?key|private[_-]?key|token|secret)\b['\"]?\s*[:=]\s*)([^\s,'\";&}]+)",
    re.IGNORECASE | re.MULTILINE,
)

_PASSWORD_ASSIGNMENT_PATTERN = re.compile(
    r"(['\"]?\b(?:password|passwd|pwd|db[_-]?password|database[_-]?password)\b['\"]?\s*[:=]\s*)(['\"])((?:\\.|(?!\2).)*)(\2)"
    r"|(['\"]?\b(?:password|passwd|pwd|db[_-]?password|database[_-]?password)\b['\"]?\s*[:=]\s*)([^\s,'\";&}]+)",
    re.IGNORECASE | re.MULTILINE,
)

_JWT_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_-])([A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,})(?![A-Za-z0-9_-])"
)

_DATABASE_URL_PATTERN = re.compile(
    r"\b(?:postgres(?:ql)?|mysql|mariadb|mongodb(?:\+srv)?|redis|amqp|sqlserver|oracle(?:\+cx_oracle)?|mssql)(?:\+[A-Za-z0-9_]+)?://[^\s]+",
    re.IGNORECASE,
)

_HIGH_ENTROPY_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])([A-Za-z0-9_\-/+=]{32,})(?![A-Za-z0-9])"
)


class RedactionService:
    def redact_text(self, text: str) -> str:
        redacted = text
        redacted = _PEM_PRIVATE_KEY_PATTERN.sub(_REDACTED, redacted)
        redacted = _AUTHORIZATION_BEARER_PATTERN.sub(self._replace_bearer_token, redacted)
        redacted = _DATABASE_URL_PATTERN.sub(self._replace_database_url, redacted)
        redacted = _SECRET_ASSIGNMENT_PATTERN.sub(self._replace_assignment, redacted)
        redacted = _PASSWORD_ASSIGNMENT_PATTERN.sub(self._replace_assignment, redacted)
        redacted = _JWT_PATTERN.sub(_REDACTED, redacted)
        redacted = _HIGH_ENTROPY_PATTERN.sub(self._replace_high_entropy_token, redacted)
        return redacted

    def redact_value(self, value: object) -> object:
        if isinstance(value, str):
            return self.redact_text(value)
        if isinstance(value, Mapping):
            return {
                key: (
                    _REDACTED
                    if self._is_sensitive_key(str(key)) and isinstance(item, (str, int, float, bool))
                    else self.redact_value(item)
                )
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [self.redact_value(item) for item in value]
        if isinstance(value, tuple):
            return tuple(self.redact_value(item) for item in value)
        return value

    @staticmethod
    def _replace_bearer_token(match: re.Match[str]) -> str:
        return f"{match.group(1)}{_REDACTED}"

    @staticmethod
    def _replace_assignment(match: re.Match[str]) -> str:
        if match.group(1) is not None:
            return f"{match.group(1)}{match.group(2)}{_REDACTED}{match.group(4)}"
        return f"{match.group(5)}{_REDACTED}"

    @staticmethod
    def _replace_database_url(match: re.Match[str]) -> str:
        candidate = match.group(0)
        sanitized = candidate.rstrip(",;')\"]")
        trailing = candidate[len(sanitized) :]

        try:
            parts = urlsplit(sanitized)
        except ValueError:
            return candidate

        netloc = parts.netloc
        if "@" in netloc:
            _, hostinfo = netloc.rsplit("@", 1)
            netloc = f"{_REDACTED}@{hostinfo}"

        query = parts.query
        if query:
            query_items = []
            for key, value in parse_qsl(query, keep_blank_values=True):
                if RedactionService._is_sensitive_key(key):
                    query_items.append((key, _REDACTED))
                else:
                    query_items.append((key, value))
            query = urlencode(query_items)

        rebuilt = urlunsplit((parts.scheme, netloc, parts.path, query, parts.fragment))
        return f"{rebuilt}{trailing}"

    @staticmethod
    def _is_sensitive_key(key: str) -> bool:
        normalized = key.lower().replace("-", "_")
        return normalized in {
            "api_key",
            "access_token",
            "auth_token",
            "bearer_token",
            "refresh_token",
            "id_token",
            "client_secret",
            "secret_key",
            "private_key",
            "token",
            "secret",
            "password",
            "passwd",
            "pwd",
            "db_password",
            "database_password",
        }

    @staticmethod
    def _replace_high_entropy_token(match: re.Match[str]) -> str:
        token = match.group(1)
        if not RedactionService._looks_sensitive(token):
            return token
        return _REDACTED

    @staticmethod
    def _looks_sensitive(token: str) -> bool:
        if len(token) < 32:
            return False
        unique_chars = len(set(token))
        if unique_chars < 10:
            return False
        if re.fullmatch(r"[A-Fa-f0-9]{32,}", token):
            return True
        if re.fullmatch(r"[A-Za-z0-9]{32,}", token):
            has_upper = any(char.isupper() for char in token)
            has_lower = any(char.islower() for char in token)
            has_digit = any(char.isdigit() for char in token)
            return sum((has_upper, has_lower, has_digit)) >= 2
        if re.fullmatch(r"[A-Za-z0-9_\-/+=]{40,}", token):
            has_upper = any(char.isupper() for char in token)
            has_lower = any(char.islower() for char in token)
            has_digit = any(char.isdigit() for char in token)
            has_symbol = any(char in "_-/+=" for char in token)
            return sum((has_upper, has_lower, has_digit, has_symbol)) >= 3
        return False
