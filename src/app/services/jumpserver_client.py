from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode, urljoin, urlparse

import requests


class JumpServerError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class JumpServerConnection:
    token_id: str
    token_value: str
    host: str
    port: int
    protocol: str


class JumpServerClient:
    def __init__(self, *, base_url: str, org_id: str, access_key_id: str, access_key_secret: str, verify_tls: bool = True, timeout: float = 20.0) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self.org_id = org_id
        self.access_key_id = access_key_id
        self.access_key_secret = access_key_secret
        self.verify_tls = verify_tls
        self.timeout = timeout

    def profile(self) -> dict[str, Any]:
        return self._request("GET", "/api/v1/users/profile/")

    def list_all_assets(self) -> list[dict[str, Any]]:
        assets: list[dict[str, Any]] = []
        offset = 0
        while True:
            page = self._request("GET", "/api/v1/perms/users/self/assets/", query={"limit": 100, "offset": offset})
            if isinstance(page, list):
                assets.extend(item for item in page if isinstance(item, dict))
                break
            results = page.get("results") if isinstance(page, dict) else None
            if not isinstance(results, list):
                raise JumpServerError("JumpServer asset list response has an unsupported shape.")
            assets.extend(item for item in results if isinstance(item, dict))
            count = int(page.get("count", len(assets)))
            if not results or len(assets) >= count:
                break
            offset += len(results)
        return assets

    def get_permitted_asset(self, asset_id: str) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/perms/users/self/assets/{asset_id}/")

    def get_permitted_accounts(self, asset_id: str, asset: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        for key in ("permed_accounts", "accounts"):
            embedded = (asset or {}).get(key)
            if isinstance(embedded, list):
                return [item for item in embedded if isinstance(item, dict)]
        page = self._request("GET", f"/api/v1/perms/users/self/assets/{asset_id}/accounts/", query={"limit": 100})
        results = page.get("results")
        if not isinstance(results, list):
            raise JumpServerError("JumpServer permitted account response has an unsupported shape.")
        return [item for item in results if isinstance(item, dict)]

    def create_ssh_connection(
        self,
        *,
        asset_id: str,
        account_ref: str,
        protocol: str = "ssh",
    ) -> JumpServerConnection:
        last_error: Exception | None = None
        for connect_method in ("ssh_client", "ssh_guide"):
            token_id = ""
            try:
                token = self._request("POST", "/api/v1/authentication/connection-token/", body={
                    "asset": asset_id,
                    "account": account_ref,
                    "protocol": protocol,
                    "connect_method": connect_method,
                })
                token_id = str(token.get("id", ""))
                if not token_id:
                    raise JumpServerError("JumpServer connection-token response is missing its id.")
                client_url = self._request("GET", f"/api/v1/authentication/connection-token/{token_id}/client-url/")
                return self._decode_client_url(client_url, token)
            except Exception as exc:
                last_error = exc
                if token_id:
                    self.expire_token(token_id)
        raise JumpServerError(f"Unable to create a KoKo SSH connection: {last_error}")

    def expire_token(self, token_id: str) -> None:
        try:
            self._request("PATCH", f"/api/v1/authentication/connection-token/{token_id}/expire/", body={})
        except Exception:
            pass

    def _decode_client_url(self, response: dict[str, Any], token: dict[str, Any]) -> JumpServerConnection:
        raw_url = response.get("url")
        if not isinstance(raw_url, str) or not raw_url:
            raise JumpServerError("JumpServer client-url response is missing its URL.")
        encoded = raw_url.removeprefix("jms://")
        try:
            payload = json.loads(base64.b64decode(encoded).decode("utf-8"))
        except Exception as exc:
            raise JumpServerError("JumpServer returned an invalid jms:// client URL.") from exc
        token_payload = payload.get("token") if isinstance(payload.get("token"), dict) else payload
        endpoint = payload.get("endpoint")
        if not isinstance(endpoint, dict):
            raise JumpServerError("JumpServer client URL is missing the KoKo endpoint.")
        host = str(endpoint.get("host", "")) or (urlparse(self.base_url).hostname or "")
        port = int(endpoint.get("port", 0) or 0)
        token_id = str(token_payload.get("id") or token.get("id") or "")
        token_value = str(token_payload.get("value") or token.get("value") or "")
        if not host or port <= 0 or not token_id or not token_value:
            raise JumpServerError("JumpServer client URL contains incomplete KoKo connection data.")
        return JumpServerConnection(token_id=token_id, token_value=token_value, host=host, port=port, protocol=str(payload.get("protocol") or "ssh"))

    def _request(self, method: str, path: str, *, query: dict[str, Any] | None = None, body: dict[str, Any] | None = None) -> dict[str, Any]:
        query_string = urlencode({key: value for key, value in (query or {}).items() if value is not None})
        target = f"{path}?{query_string}" if query_string else path
        url = urljoin(self.base_url, target.lstrip("/"))
        date = datetime.now(UTC).strftime("%a, %d %b %Y %H:%M:%S GMT")
        accept = "application/json"
        signing = f"(request-target): {method.lower()} {target}\naccept: {accept}\ndate: {date}"
        signature = base64.b64encode(hmac.new(self.access_key_secret.encode(), signing.encode(), hashlib.sha256).digest()).decode()
        headers = {
            "Accept": accept,
            "Date": date,
            "Authorization": f'Signature keyId="{self.access_key_id}",algorithm="hmac-sha256",headers="(request-target) accept date",signature="{signature}"',
        }
        if self.org_id:
            headers["X-JMS-ORG"] = self.org_id
        try:
            response = requests.request(method, url, headers=headers, json=body, timeout=self.timeout, verify=self.verify_tls)
        except requests.RequestException as exc:
            raise JumpServerError(f"JumpServer request failed: {exc}") from exc
        if response.status_code >= 400:
            detail = ""
            try:
                payload = response.json()
                detail = str(payload.get("detail") or payload.get("error") or payload.get("msg") or "") if isinstance(payload, dict) else ""
            except ValueError:
                pass
            raise JumpServerError(f"JumpServer returned HTTP {response.status_code}{f': {detail}' if detail else ''}.")
        if response.status_code == 204 or not response.content:
            return {}
        payload = response.json()
        if isinstance(payload, list):
            return {"count": len(payload), "results": payload}
        if not isinstance(payload, dict):
            raise JumpServerError("JumpServer returned a non-object JSON response.")
        return payload
