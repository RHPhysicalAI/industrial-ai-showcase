#!/usr/bin/env python3
"""
Demo script to trigger a synthetic rollback event for agent analysis demo.

This project was developed with assistance from AI tools.

Usage:
    python scripts/demo-trigger-rollback.py [--factory FACTORY] [--from-version VERSION] [--to-version VERSION]

Example:
    python scripts/demo-trigger-rollback.py --factory "Factory B" --from-version v1.4 --to-version v1.3
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from kafka import KafkaProducer


def trigger_rollback_event(
    factory: str = "Factory B",
    from_version: str = "v1.4",
    to_version: str = "v1.3",
    kafka_bootstrap: str = None
):
    """
    Publish a synthetic fleet.rollback event to Kafka.

    Args:
        factory: Factory name
        from_version: Version that was rolled back from
        to_version: Version rolled back to
        kafka_bootstrap: Kafka bootstrap servers (default from env)
    """

    if kafka_bootstrap is None:
        kafka_bootstrap = os.getenv(
            "KAFKA_BOOTSTRAP",
            "kafka-kafka-bootstrap.amq-streams.svc.cluster.local:9092"
        )

    # Build rollback event
    event = {
        "type": "policy.rollback",
        "factory": factory,
        "from_version": from_version,
        "to_version": to_version,
        "trigger": "collision_rate_threshold",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "metrics": {
            "collision_rate_before": 0.05,
            "collision_rate_after": 0.15,
            "threshold": 0.10,
            "time_since_promotion_minutes": 14
        },
        "reason": f"Collision rate exceeded threshold (0.15 > 0.10)",
        "auto_rollback": True
    }

    print(f"📡 Publishing rollback event to Kafka...")
    print(f"   Topic: fleet.events")
    print(f"   Factory: {factory}")
    print(f"   Rollback: {from_version} → {to_version}")
    print(f"   Trigger: collision_rate_threshold")

    try:
        # Create Kafka producer
        producer = KafkaProducer(
            bootstrap_servers=kafka_bootstrap,
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            acks='all',
            retries=3
        )

        # Send event
        future = producer.send('fleet.events', value=event)
        result = future.get(timeout=10)

        print(f"✅ Event published successfully!")
        print(f"   Partition: {result.partition}")
        print(f"   Offset: {result.offset}")
        print(f"\n📋 Event payload:")
        print(json.dumps(event, indent=2))

        producer.flush()
        producer.close()

        return True

    except Exception as e:
        print(f"❌ Failed to publish event: {e}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Trigger a synthetic rollback event for agent analysis demo"
    )
    parser.add_argument(
        "--factory",
        default="Factory B",
        help="Factory name (default: Factory B)"
    )
    parser.add_argument(
        "--from-version",
        default="v1.4",
        help="Version rolled back from (default: v1.4)"
    )
    parser.add_argument(
        "--to-version",
        default="v1.3",
        help="Version rolled back to (default: v1.3)"
    )
    parser.add_argument(
        "--kafka-bootstrap",
        help="Kafka bootstrap servers (default: from KAFKA_BOOTSTRAP env)"
    )

    args = parser.parse_args()

    success = trigger_rollback_event(
        factory=args.factory,
        from_version=args.from_version,
        to_version=args.to_version,
        kafka_bootstrap=args.kafka_bootstrap
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
