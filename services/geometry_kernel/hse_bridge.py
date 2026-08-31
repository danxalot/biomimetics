#!/usr/bin/env python3
"""HSE Bridge: subscribe to OTEL signals and publish HSE state to Redis.

This lightweight bridge listens for telemetry messages on Redis pubsub
channel `otel:signals` (JSON messages), maps them to geometry forces using
`SignalForceMapper` and writes a summarized HSE state to key
`arca:hse:state_vector` for the `geometry_kernel` to ingest.

Run as a sidecar or short-lived process. This file modifies service behavior
only and does not alter orchestration or architecture.
"""
import os
import json
import time
import logging
from datetime import datetime

import redis

from geometry_kernel.otel_mapping import (
    OTELSignal,
    SignalType,
    SignalForceMapper,
)

LOG = logging.getLogger("hse_bridge")
logging.basicConfig(level=logging.INFO)


def parse_signal(msg: dict) -> OTELSignal:
    # Expecting keys: signal_type, service, metric, value, baseline, timestamp
    stype = msg.get("signal_type") or msg.get("type")
    try:
        signal_type = SignalType(stype)
    except Exception:
        # try normalize
        signal_type = SignalType(stype.lower()) if isinstance(stype, str) else None

    ts_raw = msg.get("timestamp") or msg.get("time") or datetime.utcnow().isoformat()
    try:
        ts = datetime.fromisoformat(ts_raw)
    except Exception:
        ts = datetime.utcnow()

    return OTELSignal(
        signal_type=signal_type,
        service=msg.get("service", "unknown"),
        metric=msg.get("metric", "unknown"),
        value=float(msg.get("value", 0.0)),
        baseline=float(msg.get("baseline", 0.0)),
        timestamp=ts,
        additional_context=msg.get("context", {}),
    )


def force_to_dict(force):
    # Serialize Force dataclass to JSON-friendly dict
    return {
        "target_id": force.target_id,
        "vector": force.vector.to_list(),
        "magnitude": force.magnitude,
        "source": getattr(force.source, "value", str(force.source)),
        "rationale": getattr(force, "rationale", ""),
    }


def main():
    redis_host = os.getenv("REDIS_HOST", "redis")
    redis_port = int(os.getenv("REDIS_PORT", "6379"))
    channel = os.getenv("OTEL_CHANNEL", "otel:signals")
    hse_key = os.getenv("HSE_KEY", "arca:hse:state_vector")

    r = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)
    pubsub = r.pubsub(ignore_subscribe_messages=True)
    pubsub.subscribe(channel)

    LOG.info("HSE Bridge started; subscribed to %s, publishing HSE to %s", channel, hse_key)

    try:
        for message in pubsub.listen():
            try:
                data = message.get("data")
                if not data:
                    continue
                # Data may be JSON string
                if isinstance(data, str):
                    payload = json.loads(data)
                else:
                    payload = data

                sig = parse_signal(payload)
                mapping = SignalForceMapper.map_signal(sig)

                forces = [force_to_dict(f) for f in mapping.forces]

                # HSE state summary
                hse_state = {
                    "timestamp": datetime.utcnow().isoformat(),
                    "service": sig.service,
                    "signal_type": sig.signal_type.value if sig.signal_type else None,
                    "interpretation": mapping.interpretation.value if mapping.interpretation else None,
                    "confidence": mapping.confidence,
                    "forces": forces,
                }

                # Write HSE state as JSON string
                r.set(hse_key, json.dumps(hse_state))
                LOG.info("Published HSE state from %s (%s): %d forces", sig.service, sig.signal_type, len(forces))

            except Exception as e:
                LOG.exception("Error processing OTEL message: %s", e)
                time.sleep(0.5)

    except KeyboardInterrupt:
        LOG.info("HSE Bridge shutting down")


if __name__ == "__main__":
    main()
