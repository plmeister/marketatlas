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
import base64
import json
import sys
from hashlib import sha256
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
    ToDeviceMessage,
    UnknownToDeviceEvent,
)
from nio.api import Api
from nio.crypto.sas import Sas

sys.path.insert(0, str(Path(__file__).resolve().parent))

from matrix_transport import load_config  # noqa: E402


def _patch_nio_sas() -> None:
    """Work around matrix-nio 0.26.0 SAS interop bugs against modern Element.

    Three separate regressions in the libolm -> vodozemac migration break SAS
    verification with Element (each is self-consistent nio<->nio, which is why
    upstream tests never caught them):

    1. commitment: nio sends the m.key.verification.accept commitment as a hex
       digest instead of the spec-mandated unpadded base64 -> Element cancels
       with key_mismatch before any emoji are shown (upstream issue #570).
    2. emoji: vodozemac's sas.emoji_indices already holds the seven 6-bit
       indices, but nio feeds them back through the old libolm bit-splitting,
       so the emoji never match the peer's.
    3. MAC: nio only negotiates the deprecated "hkdf-hmac-sha256" (libolm v1
       encoding) while vodozemac's calculate_mac() emits the correct
       "hkdf-hmac-sha256.v2" base64, so the MACs disagree at the final step.
    """

    def _b64_sha256(*parts: str) -> str:
        digest = sha256("".join(parts).encode()).digest()
        return base64.b64encode(digest).decode().rstrip("=")

    original_from_start = Sas.from_key_verification_start.__func__

    @classmethod
    def from_key_verification_start(cls, own_user, own_device, own_fp_key, other_olm_device, event):
        obj = original_from_start(
            cls, own_user, own_device, own_fp_key, other_olm_device, event
        )
        content = Api.to_canonical_json(event.source["content"])
        obj.commitment = _b64_sha256(obj.pubkey, content)
        return obj

    Sas.from_key_verification_start = from_key_verification_start

    def _check_commitment(self, key: str) -> bool:
        content = Api.to_canonical_json(self.start_verification().content)
        return self.commitment == _b64_sha256(key, content)

    Sas._check_commitment = _check_commitment

    def _generate_emoji(self, extra_info):
        """Work around matrix-nio 0.26.0.

        vodozemac's ``sas.emoji_indices`` already returns the seven final
        6-bit indices, but nio 0.26.0 feeds them back through the old libolm
        bit-splitting (``format(x, "08b")`` + regroup), so our emoji never
        match the peer's. Use the indices directly, exactly like
        ``_generate_decimals`` does for ``.decimals``.
        """
        indices = self.established_sas.bytes(extra_info).emoji_indices
        return [self.emoji[int(i)] for i in indices]

    Sas._generate_emoji = _generate_emoji

    # nio 0.26.0 only advertises/negotiates the deprecated MAC method
    # "hkdf-hmac-sha256" (the libolm v1 encoding bug). vodozemac's
    # calculate_mac() emits the *correct* hkdf-hmac-sha256.v2 base64, so
    # Element (which supports .v2 and prefers it) computes v1 bytes and the
    # MACs disagree -> m.key_mismatch after the emoji match. Negotiate .v2.
    Sas._mac_normal = "hkdf-hmac-sha256.v2"
    Sas._mac_v1 = ["hkdf-hmac-sha256.v2", "hkdf-hmac-sha256"]


_patch_nio_sas()


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
        config=AsyncClientConfig(store_sync_tokens=True, encryption_enabled=True),
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
    armed = False

    async def on_to_device(event: KeyVerificationEvent) -> None:
        if not armed:
            return
        print(f"[verify] event: {type(event).__name__}")
        try:
            await _dispatch(event)
        except Exception as exc:  # surface protocol errors instead of swallowing
            print(f"verification handler error: {type(exc).__name__}: {exc}")

    async def _dispatch(event: KeyVerificationEvent) -> None:
        if isinstance(event, KeyVerificationStart):
            if "emoji" not in event.short_authentication_string:
                print(f"peer lacks emoji SAS: {event.short_authentication_string}")
                return
            print(f"verification requested by {event.sender} ({event.from_device})")
            if event.transaction_id not in client.key_verifications:
                print("peer device not in store; querying keys, please retry Verify")
                client.users_for_key_query.add(event.sender)
                try:
                    await client.keys_query()
                except LocalProtocolError:
                    pass
                return
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
                # nio never sends the responder's completion message, but
                # Element keeps the session shown as pending until it arrives.
                other = sas.other_olm_device
                done_msg = ToDeviceMessage(
                    "m.key.verification.done",
                    other.user_id,
                    other.id,
                    {"transaction_id": event.transaction_id},
                )
                resp = await client.to_device(done_msg)
                if isinstance(resp, ToDeviceError):
                    print(f"done send failed: {resp}")
                print(f"verified device(s): {sas.verified_devices}")
                print("verification complete.")
                done.set()

    client.add_to_device_callback(on_to_device, (KeyVerificationEvent,))

    async def on_unknown(event: UnknownToDeviceEvent) -> None:
        # nio (0.26) has no request/ready handshake, but modern Element opens a
        # verification with m.key.verification.request and waits for a ready.
        etype = event.source.get("type", event.type)
        if not armed:
            return
        print(f"[unknown to-device] type={etype} from={event.sender}")
        if etype != "m.key.verification.request":
            return
        content = event.source.get("content", {})
        from_device = content.get("from_device")
        tx = content.get("transaction_id")
        print(f"verification request from {event.sender} ({from_device}); sending ready")
        client.users_for_key_query.add(event.sender)
        try:
            await client.keys_query()
        except LocalProtocolError:
            pass
        ready = ToDeviceMessage(
            "m.key.verification.ready",
            event.sender,
            from_device,
            {
                "from_device": client.device_id,
                "methods": ["m.sas.v1"],
                "transaction_id": tx,
            },
        )
        resp = await client.to_device(ready)
        if isinstance(resp, ToDeviceError):
            print(f"ready send failed: {resp}")

    client.add_to_device_callback(on_unknown, (UnknownToDeviceEvent,))

    async def _pump_keys() -> None:
        if getattr(client, "should_upload_keys", False):
            await client.keys_upload()
        if getattr(client, "should_query_keys", False):
            try:
                await client.keys_query()
            except LocalProtocolError:
                pass

    await client.sync(timeout=30000, full_state=True)
    await _pump_keys()
    # self-verification needs our own other devices in the store
    client.users_for_key_query.add(cfg.user_id)
    for room in getattr(client, "rooms", {}).values():
        client.users_for_key_query.update(getattr(room, "users", {}))
    try:
        await client.keys_query()
    except LocalProtocolError:
        pass
    await _pump_keys()

    try:
        known = list(client.device_store[cfg.user_id])
    except KeyError:
        known = []
    print(f"known {cfg.user_id} devices: {known}")

    print(
        f"device {client.device_id} ({cfg.user_id}) is waiting for a verification "
        "request.\nIn Element open the @moss device -> Verify, then compare emoji. "
        "Ctrl-C to stop."
    )
    # Drain anything the server replayed from earlier sessions before we start
    # reacting, otherwise a stale start/key pair gets answered with fresh SAS
    # keys and the two sides derive different emoji.
    await client.sync(timeout=3000)
    armed = True
    print("armed; ready for a fresh verification request.")
    try:
        while not done.is_set():
            await client.sync(timeout=30000)
            await _pump_keys()
    except KeyboardInterrupt:
        pass
    finally:
        await client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_run()))
