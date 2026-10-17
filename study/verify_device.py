"""One-off interactive SAS (emoji) verification for the notifier device.

The daily notifier runs headless, so its device shows up as "unverified" in
Element and every alert carries the "encrypted by an unknown or deleted device"
warning. Clearing that needs a real interactive SAS handshake driven from
Element; run this script, then click *Verify* on the @moss notifier device (in
Element: the room's device list / the sender's profile -> Sessions) and compare
the emoji. The bot auto-accepts and auto-confirms (the human does the visual
check in Element); trust is written into the olm store, so future headless runs
stay verified.

Usage:
  poetry run python study/verify_device.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from nio import (
    AsyncClient,
    AsyncClientConfig,
    KeyVerificationCancel,
    KeyVerificationEvent,
    KeyVerificationKey,
    KeyVerificationMac,
    KeyVerificationStart,
    LocalProtocolError,
    ToDeviceError,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))

from matrix_transport import load_config  # noqa: E402


def _emoji_line(sas) -> str:
    return "  ".join(f"{glyph} {name}" for glyph, name in sas.get_emoji())


async def _run() -> int:
    cfg = load_config()
    store = Path(cfg.store_dir)
    store.mkdir(parents=True, exist_ok=True)

    client = AsyncClient(
        cfg.homeserver,
        cfg.user_id,
        store_path=str(store),
        config=AsyncClientConfig(store_sync_tokens=False, encryption_enabled=True),
    )
    session = store / "session.json"
    if not session.exists():
        print(f"no stored session at {session}; run the notifier once first", file=sys.stderr)
        return 1
    data = json.loads(session.read_text())
    client.restore_login(
        user_id=data["user_id"],
        device_id=data["device_id"],
        access_token=data["access_token"],
    )
    client.load_store()

    done = asyncio.Event()

    async def on_to_device(event: KeyVerificationEvent) -> None:
        if isinstance(event, KeyVerificationStart):
            if "emoji" not in event.short_authentication_string:
                print(f"peer lacks emoji SAS: {event.short_authentication_string}")
                return
            print(f"verification requested by {event.sender} ({event.from_device})")
            resp = await client.accept_key_verification(event.transaction_id)
            if isinstance(resp, ToDeviceError):
                print(f"accept failed: {resp}")
                return
            sas = client.key_verifications[event.transaction_id]
            await client.to_device(sas.share_key())
        elif isinstance(event, KeyVerificationCancel):
            print(f"verification cancelled by {event.sender}: {event.reason}")
        elif isinstance(event, KeyVerificationKey):
            sas = client.key_verifications[event.transaction_id]
            print("\nCompare these emoji with Element:")
            print("  " + _emoji_line(sas) + "\n")
            resp = await client.confirm_short_auth_string(event.transaction_id)
            if isinstance(resp, ToDeviceError):
                print(f"confirm failed: {resp}")
        elif isinstance(event, KeyVerificationMac):
            sas = client.key_verifications[event.transaction_id]
            try:
                await client.to_device(sas.get_mac())
            except LocalProtocolError as exc:
                print(f"mac error: {exc}")
                return
            if sas.verified:
                print(f"verified device(s): {sas.verified_devices}")
                print("verification complete.")
                done.set()

    client.add_to_device_callback(on_to_device, (KeyVerificationEvent,))
    await client.sync(timeout=30000, full_state=True)
    if getattr(client, "should_upload_keys", False):
        await client.keys_upload()

    print(
        f"device {client.device_id} ({cfg.user_id}) is waiting for a verification "
        "request.\nIn Element open the @moss device -> Verify, then compare emoji. "
        "Ctrl-C to stop."
    )
    try:
        while not done.is_set():
            await client.sync(timeout=30000)
    except KeyboardInterrupt:
        pass
    finally:
        await client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_run()))
