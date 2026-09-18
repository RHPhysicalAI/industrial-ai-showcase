# This project was developed with assistance from AI tools.
"""Fleet Manager settings — extends common_lib.ServiceSettings."""

from pydantic import Field

from common_lib.config import ServiceSettings


class FleetManagerSettings(ServiceSettings):
    service_name: str = "fleet-manager"

    missions_topic: str = "fleet.missions"
    alerts_topic: str = "fleet.safety.alerts"
    telemetry_topic: str = "fleet.telemetry"
    events_topic: str = "fleet.events"
    ops_events_topic: str = "fleet.ops.events"
    mes_orders_topic: str = "mes.orders"
    consumer_group_id: str = "fleet-manager"

    policy_version: str = Field(
        default="vla-warehouse-v1.3",
        description="Active VLA policy version pinned in emitted missions.",
    )
