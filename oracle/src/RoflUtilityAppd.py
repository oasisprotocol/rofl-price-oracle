"""RoflUtilityAppd: ROFL utility for production appd daemon."""

import json
import logging
import time
from typing import Any

import cbor2
import httpx
from web3.types import TxParams

from .RoflUtility import RoflUtility

logger = logging.getLogger(__name__)

# Retry configuration for appd requests
MAX_RETRIES = 30  # ~30 seconds with 1s base delay
BACKOFF_BASE = 1.0
BACKOFF_MAX = 5.0


class RoflUtilityAppd(RoflUtility):
    """ROFL utility implementation for production appd daemon.

    Communicates with the ROFL appd via Unix domain socket or HTTP.

    :cvar ROFL_SOCKET_PATH: Default Unix socket path for appd.
    :ivar url: Optional HTTP URL or socket path override.
    """

    ROFL_SOCKET_PATH = "/run/rofl-appd.sock"

    def __init__(self, url: str = "") -> None:
        """Initialize the appd utility.

        :param url: Optional URL or socket path. Empty uses default socket.
        """
        self.url = url

    def _build_transport(self) -> httpx.HTTPTransport | None:
        """Build HTTP transport for appd requests."""
        if self.url and not self.url.startswith("http"):
            logger.debug("Using HTTP socket: %s", self.url)
            return httpx.HTTPTransport(uds=self.url)
        if not self.url:
            logger.debug("Using unix domain socket: %s", self.ROFL_SOCKET_PATH)
            return httpx.HTTPTransport(uds=self.ROFL_SOCKET_PATH)
        return None

    def _appd_get(self, path: str, params: Any) -> httpx.Response:
        """Make a GET request to the appd with retry and backoff.

        :param path: API endpoint path.
        :param params: Query parameters.
        :returns: HTTP response.
        :raises RuntimeError: If max retries exceeded.
        """
        transport = self._build_transport()
        base_url = self.url if self.url and self.url.startswith("http") else "http://localhost"

        with httpx.Client(transport=transport) as client:
            for attempt in range(MAX_RETRIES):
                try:
                    logger.debug(
                        "GET %s params=%s (attempt %d)", path, params, attempt + 1
                    )
                    response = client.get(base_url + path, params=params, timeout=None)
                    logger.debug(
                        "Response: %s %s", response.status_code, response.reason_phrase
                    )
                    if response.is_success:
                        return response
                    logger.warning(
                        "appd GET %s failed: %s %s (attempt %d/%d)",
                        path,
                        response.status_code,
                        response.reason_phrase,
                        attempt + 1,
                        MAX_RETRIES,
                    )
                except httpx.RequestError as exc:
                    logger.warning(
                        "appd GET %s error: %s (attempt %d/%d)",
                        path,
                        exc,
                        attempt + 1,
                        MAX_RETRIES,
                    )
                delay = min(BACKOFF_BASE * (1.5 ** attempt), BACKOFF_MAX)
                time.sleep(delay)

        raise RuntimeError(f"appd GET {path} failed after {MAX_RETRIES} attempts")

    def _appd_post(self, path: str, payload: Any) -> httpx.Response:
        """Make a POST request to the appd with retry and backoff.

        :param path: API endpoint path.
        :param payload: JSON payload.
        :returns: HTTP response.
        :raises RuntimeError: If max retries exceeded.
        """
        transport = self._build_transport()
        base_url = self.url if self.url and self.url.startswith("http") else "http://localhost"

        with httpx.Client(transport=transport) as client:
            for attempt in range(MAX_RETRIES):
                try:
                    logger.debug(
                        "POST %s payload=%s (attempt %d)",
                        path,
                        json.dumps(payload),
                        attempt + 1,
                    )
                    response = client.post(base_url + path, json=payload, timeout=None)
                    logger.debug(
                        "Response: %s %s", response.status_code, response.reason_phrase
                    )
                    if response.is_success:
                        return response
                    logger.warning(
                        "appd POST %s failed: %s %s (attempt %d/%d)",
                        path,
                        response.status_code,
                        response.reason_phrase,
                        attempt + 1,
                        MAX_RETRIES,
                    )
                except httpx.RequestError as exc:
                    logger.warning(
                        "appd POST %s error: %s (attempt %d/%d)",
                        path,
                        exc,
                        attempt + 1,
                        MAX_RETRIES,
                    )
                delay = min(BACKOFF_BASE * (1.5 ** attempt), BACKOFF_MAX)
                time.sleep(delay)

        raise RuntimeError(f"appd POST {path} failed after {MAX_RETRIES} attempts")

    def fetch_appid(self) -> str:
        """Fetch the current ROFL app ID from appd.

        :returns: Bech32-encoded app ID.
        """
        path = "/rofl/v1/app/id"
        response = self._appd_get(path, {})
        return response.content.decode("utf-8")

    def fetch_key(self, id: str) -> str:
        """Generate or fetch a key by ID.

        :param id: Key identifier.
        :returns: Generated key value.
        """
        payload = {
            "key_id": id,
            "kind": "secp256k1",
        }

        path = "/rofl/v1/keys/generate"

        response = self._appd_post(path, payload).json()
        return response["key"]

    def submit_tx(self, tx: TxParams) -> Any:
        """Submit a transaction via the ROFL appd sign-submit endpoint.

        :param tx: Transaction parameters including data, to, gas, value.
        :returns: Transaction result with CBOR-decoded data.
        """
        # Strip 0x prefix from hex strings and normalize to lowercase
        data_hex = tx["data"][2:] if str(tx["data"]).startswith("0x") else str(tx["data"])
        data_hex = data_hex.lower()

        # For contract creation, to is empty. For calls, strip 0x prefix.
        to_hex = ""
        if "to" in tx and tx["to"]:
            to_hex = tx["to"][2:] if str(tx["to"]).startswith("0x") else str(tx["to"])
            to_hex = to_hex.lower()

        payload = {
            "tx": {
                "kind": "eth",
                "data": {
                    "gas_limit": int(tx["gas"]),
                    "to": to_hex,
                    "value": str(tx["value"]),
                    "data": data_hex,
                },
            },
            "encrypted": False,
        }

        path = "/rofl/v1/tx/sign-submit"

        result = self._appd_post(path, payload).json()
        if result.get("data"):
            result["data"] = cbor2.loads(bytes.fromhex(result["data"]))
        return result
