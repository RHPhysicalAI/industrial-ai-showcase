"""
Kafka event listener for fleet events (rollback, anomaly detection).

This project was developed with assistance from AI tools.

Listens for fleet.events topic and triggers agent investigation when
rollbacks occur. Agent provides post-mortem analysis visible in Console UI.
"""

import asyncio
import json
import logging
import os
import threading
from typing import Dict, Any, Optional
from kafka import KafkaConsumer
from kafka.errors import KafkaError

logger = logging.getLogger(__name__)


class FleetEventListener:
    """
    Listens for fleet events (rollback, anomaly) and triggers agent analysis.
    """

    def __init__(
        self,
        kafka_bootstrap: str,
        on_rollback_callback: Optional[callable] = None
    ):
        """
        Initialize event listener.

        Args:
            kafka_bootstrap: Kafka bootstrap servers
            on_rollback_callback: Async function called when rollback event received
        """
        self.kafka_bootstrap = kafka_bootstrap
        self.on_rollback_callback = on_rollback_callback
        self.consumer: Optional[KafkaConsumer] = None
        self.running = False
        self.thread: Optional[threading.Thread] = None

    def start(self):
        """Start listening for events in background thread."""
        if self.running:
            logger.warning("Event listener already running")
            return

        self.running = True
        self.thread = threading.Thread(target=self._consume_events, daemon=True)
        self.thread.start()
        logger.info("Fleet event listener started")

    def stop(self):
        """Stop listening for events."""
        self.running = False
        if self.consumer:
            self.consumer.close()
        logger.info("Fleet event listener stopped")

    def _consume_events(self):
        """
        Consume events from Kafka (runs in background thread).
        """
        try:
            # Create consumer
            self.consumer = KafkaConsumer(
                'fleet.events',
                bootstrap_servers=self.kafka_bootstrap,
                value_deserializer=lambda m: json.loads(m.decode('utf-8')),
                auto_offset_reset='latest',  # Only new events
                enable_auto_commit=True,
                group_id='agentic-orchestrator-fleet-events',
                consumer_timeout_ms=1000  # Poll timeout
            )

            logger.info(f"Listening for fleet.events on {self.kafka_bootstrap}")

            # Process events
            while self.running:
                try:
                    for message in self.consumer:
                        if not self.running:
                            break

                        event = message.value
                        event_type = event.get('type')

                        logger.info(f"Received fleet event: {event_type}")

                        # Handle rollback events
                        if event_type == 'policy.rollback':
                            self._handle_rollback(event)

                except StopIteration:
                    # Timeout, continue polling
                    continue
                except Exception as e:
                    logger.error(f"Error processing event: {e}", exc_info=True)
                    # Continue listening even if one event fails

        except KafkaError as e:
            logger.error(f"Kafka connection error: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"Event listener error: {e}", exc_info=True)
        finally:
            if self.consumer:
                self.consumer.close()

    def _handle_rollback(self, event: Dict[str, Any]):
        """
        Handle policy.rollback event by triggering agent analysis.

        Args:
            event: Rollback event payload
        """
        factory = event.get('factory', 'unknown')
        from_version = event.get('from_version', 'unknown')
        to_version = event.get('to_version', 'unknown')

        logger.info(
            f"Rollback detected: {factory} {from_version} → {to_version}"
        )

        # Trigger agent investigation (async callback)
        if self.on_rollback_callback:
            try:
                # Run async callback in new event loop (we're in a thread)
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self.on_rollback_callback(event))
                loop.close()
            except Exception as e:
                logger.error(f"Rollback callback error: {e}", exc_info=True)
        else:
            logger.warning("No rollback callback registered")


# Singleton instance
_event_listener: Optional[FleetEventListener] = None


def get_event_listener() -> FleetEventListener:
    """Get singleton event listener instance."""
    global _event_listener
    if _event_listener is None:
        kafka_bootstrap = os.getenv(
            "KAFKA_BOOTSTRAP",
            "kafka-kafka-bootstrap.amq-streams.svc.cluster.local:9092"
        )
        _event_listener = FleetEventListener(kafka_bootstrap=kafka_bootstrap)
    return _event_listener


def start_event_listener(on_rollback_callback: callable):
    """
    Start fleet event listener with rollback callback.

    Args:
        on_rollback_callback: Async function called when rollback occurs
    """
    listener = get_event_listener()
    listener.on_rollback_callback = on_rollback_callback
    listener.start()


def stop_event_listener():
    """Stop fleet event listener."""
    listener = get_event_listener()
    listener.stop()
