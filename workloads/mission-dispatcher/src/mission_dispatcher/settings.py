# This project was developed with assistance from AI tools.
"""Mission Dispatcher settings — extends common_lib.ServiceSettings."""

from pydantic import Field

from common_lib.config import ServiceSettings


class MissionDispatcherSettings(ServiceSettings):
    service_name: str = "mission-dispatcher"

    missions_topic: str = "fleet.missions"
    ops_events_topic: str = "fleet.ops.events"
    telemetry_topic: str = "fleet.telemetry"
    consumer_group_id: str = "mission-dispatcher"

    # Phase 1 companion SNO reaches hub Kafka via TLS-passthrough Route.
    # Server cert CN matches the bootstrap route; we skip CN verification
    # because the companion doesn't have the cluster CA trust store plumbed
    # yet (Phase 2 hardens with proper CA + KafkaUser client auth).
    kafka_ssl_endpoint_identification_algorithm: str = Field(default="none")
    kafka_enable_ssl_certificate_verification: bool = Field(default=True)

    vla_endpoint_url: str = Field(
        default="http://10.0.0.74:8000/act",
        description="Companion host VLA endpoint (macvlan IP) per ADR-026.",
    )
    vla_request_timeout_s: float = Field(default=10.0)

    policy_version: str = Field(default="v1.0")

    waypoint_hz: float = Field(default=5.0, gt=0.0)
    waypoint_speed_mps: float = Field(default=2.0, gt=0.0)
