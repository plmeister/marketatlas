"""Matrix transport with end-to-end encryption, backed by matrix-nio.

Logs in once (password) to register a dedicated device, persists the access
token + olm account to a store directory, and reuses it thereafter. Sends
text and images into an (optionally encrypted) room.

Config comes from a KEY=VALUE env file (or the process environment):
  MATRIX_HOMESERVER   e.g. https://glasgow.social
  MATRIX_USER_ID      e.g. @moss:glasgow.social
  MATRIX_PASSWORD     account password (only needed for the first login)
  MATRIX_ROOM_ID      target room (encrypted rooms are fine)
"""

from __future__ import annotations

import asyncio
import io
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nio import AsyncClient, AsyncClientConfig, LoginError, RoomSendError

STORE_ROOT = os.path.expanduser("~/.local/share/marketatlas/matrix-store")
DEFAULT_ENV = os.path.expanduser("~/.config/marketatlas/notify.env")


class MatrixTransportError(RuntimeError):
    pass


@dataclass(frozen=True)
class MatrixConfig:
    homeserver: str
    user_id: str
    room_id: str
    password: str = ""
    store_dir: str = STORE_ROOT


def load_config(env_path: str | None = None) -> MatrixConfig:
    env_path = env_path or os.environ.get("NOTIFY_ENV", DEFAULT_ENV)
    if os.path.exists(env_path):
        with open(env_path) as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip().strip("'\""))
    homeserver = os.environ.get("MATRIX_HOMESERVER", "")
    user_id = os.environ.get("MATRIX_USER_ID", "")
    room_id = os.environ.get("MATRIX_ROOM_ID", "")
    if not (homeserver and user_id and room_id):
        raise SystemExit(
            "missing Matrix config: set MATRIX_HOMESERVER, MATRIX_USER_ID, "
            "MATRIX_ROOM_ID (in the env file or the environment)"
        )
    return MatrixConfig(
        homeserver=homeserver,
        user_id=user_id,
        room_id=room_id,
        password=os.environ.get("MATRIX_PASSWORD", ""),
        store_dir=os.environ.get("MATRIX_STORE_DIR", STORE_ROOT),
    )


class MatrixTransport:
    def __init__(self, config: MatrixConfig) -> None:
        self._cfg = config
        self._store = Path(config.store_dir)

    def _session_path(self) -> Path:
        return self._store / "session.json"

    async def _client(self) -> AsyncClient:
        self._store.mkdir(parents=True, exist_ok=True)
        nio_config = AsyncClientConfig(store_sync_tokens=False, encryption_enabled=True)
        client = AsyncClient(
            self._cfg.homeserver,
            self._cfg.user_id,
            store_path=str(self._store),
            config=nio_config,
        )
        session = self._session_path()
        if session.exists():
            data = json.loads(session.read_text())
            client.restore_login(
                user_id=data["user_id"],
                device_id=data["device_id"],
                access_token=data["access_token"],
            )
            client.load_store()
        else:
            if not self._cfg.password:
                raise MatrixTransportError(
                    "no stored session and no MATRIX_PASSWORD to log in with"
                )
            response = await client.login(
                password=self._cfg.password, device_name="marketatlas-notifier"
            )
            if isinstance(response, LoginError):
                raise MatrixTransportError(f"login failed: {response.message}")
            session.write_text(
                json.dumps(
                    {
                        "user_id": client.user_id,
                        "device_id": client.device_id,
                        "access_token": client.access_token,
                    }
                )
            )
            session.chmod(0o600)
        await client.sync(timeout=30000)
        if getattr(client, "should_upload_keys", False):
            await client.keys_upload()
        return client

    async def _send_text(self, client: AsyncClient, body: str) -> None:
        result = await client.room_send(
            self._cfg.room_id,
            "m.room.message",
            {"msgtype": "m.text", "body": body},
            ignore_unverified_devices=True,
        )
        if isinstance(result, RoomSendError):
            raise MatrixTransportError(f"text send failed: {result.message}")

    async def _send_image(self, client: AsyncClient, path: Path, caption: str) -> None:
        data = path.read_bytes()
        room = client.rooms.get(self._cfg.room_id)
        encrypted = bool(getattr(room, "encrypted", False))
        upload, keys = await client.upload(
            io.BytesIO(data),
            content_type="image/png",
            filename=path.name,
            encrypt=encrypted,
        )
        content: dict[str, Any] = {
            "msgtype": "m.image",
            "body": caption,
            "info": {"mimetype": "image/png", "size": len(data)},
        }
        if encrypted and keys:
            content["file"] = {**keys, "url": upload.content_uri}
        else:
            content["url"] = upload.content_uri
        result = await client.room_send(
            self._cfg.room_id, "m.room.message", content, ignore_unverified_devices=True
        )
        if isinstance(result, RoomSendError):
            raise MatrixTransportError(f"image send failed: {result.message}")

    async def _notify(self, items: list[tuple[Any, ...]]) -> None:
        client = await self._client()
        try:
            for item in items:
                if item[0] == "text":
                    await self._send_text(client, item[1])
                elif item[0] == "image":
                    await self._send_image(client, Path(item[1]), item[2])
        finally:
            await client.close()

    def notify(self, items: list[tuple[Any, ...]]) -> None:
        asyncio.run(self._notify(items))

    def self_test(self) -> None:
        self.notify([("text", "marketatlas notifier self-test: Matrix E2EE transport OK.")])
