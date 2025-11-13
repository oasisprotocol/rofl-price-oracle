import cbor2
import httpx
import json
import time
import typing
from web3.types import TxParams

from .RoflUtility import RoflUtility


class RoflUtilityAppd(RoflUtility):
    ROFL_SOCKET_PATH = "/run/rofl-appd.sock"

    def __init__(self, url: str = ''):
        self.url = url

    def _appd_get(self, path: str, params: typing.Any) -> typing.Any:
        transport = None
        if self.url and not self.url.startswith('http'):
            transport = httpx.HTTPTransport(uds=self.url)
            print(f"Using HTTP socket: {self.url}")
        elif not self.url:
            transport = httpx.HTTPTransport(uds=self.ROFL_SOCKET_PATH)
            print(f"Using unix domain socket: {self.ROFL_SOCKET_PATH}")

        client = httpx.Client(transport=transport)

        url = self.url if self.url and self.url.startswith('http') else "http://localhost"
        while True:
            print(f"  Getting {params} from {url+path}")
            response = client.get(url + path, params=params, timeout=None)
            print(f"  Response: {response.status_code} {response.reason_phrase}")
            if response.is_success:
                break
            time.sleep(1)

        return response

    def _appd_post(self, path: str, payload: typing.Any) -> typing.Any:
        transport = None
        if self.url and not self.url.startswith('http'):
            transport = httpx.HTTPTransport(uds=self.url)
            print(f"Using HTTP socket: {self.url}")
        elif not self.url:
            transport = httpx.HTTPTransport(uds=self.ROFL_SOCKET_PATH)
            print(f"Using unix domain socket: {self.ROFL_SOCKET_PATH}")

        client = httpx.Client(transport=transport)

        url = self.url if self.url and self.url.startswith('http') else "http://localhost"
        while True:
            print(f"  Posting {json.dumps(payload)} to {url+path}")
            response = client.post(url + path, json=payload, timeout=None)
            print(f"  Response: {response.status_code} {response.reason_phrase}")
            if response.is_success:
                break
            time.sleep(1)

        return response

    def fetch_appid(self) -> str:
        path = '/rofl/v1/app/id'
        response = self._appd_get(path, {})
        return response.content.decode("utf-8")

    def fetch_key(self, id: str) -> str:
        payload = {
            "key_id": id,
            "kind": "secp256k1"
        }

        path = '/rofl/v1/keys/generate'

        response = self._appd_post(path, payload).json()
        return response["key"]

    def submit_tx(self, tx: TxParams) -> typing.Any:
        payload = {
            "tx": {
                "kind": "eth",
                "data": {
                    "gas_limit": tx["gas"],
                    "value": tx["value"],
                    "data": tx["data"][2:] if tx["data"].startswith("0x") else tx["data"]
                },
            },
            "encrypt": False,
        }

        # Contract create transactions don't have "to". For others, include it.
        if "to" in tx:
            payload["tx"]["data"]["to"] = tx["to"][2:] if tx["to"].startswith("0x") else tx["to"]

        path = '/rofl/v1/tx/sign-submit'

        result = self._appd_post(path, payload).json()
        if result["data"]:
            result["data"] = cbor2.loads(bytes.fromhex(result["data"]))
        return result