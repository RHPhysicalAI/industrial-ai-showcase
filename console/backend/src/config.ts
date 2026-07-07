// This project was developed with assistance from AI tools.
export interface AppConfig {
  port: number;
  logLevel: string;
  kafkaBootstrapServers: string;
  kafkaClientId: string;
  kafkaConsumerGroup: string;
  kafkaTopics: string[];
  wmsStubBaseUrl: string;
  mjpegUrl: string;
  signalingServer: string;
  turnUrl: string;
  turnUsername: string;
  turnCredential: string;
  githubToken: string;
  githubRepo: string;
  clusterAppsDomain: string;
  agenticOrchestratorUrl: string;
}

export function loadConfig(): AppConfig {
  return {
    port: parseInt(process.env.PORT ?? "8090", 10),
    logLevel: process.env.LOG_LEVEL ?? "info",
    kafkaBootstrapServers:
      process.env.KAFKA_BOOTSTRAP_SERVERS ??
      "fleet-kafka-bootstrap.fleet-ops.svc.cluster.local:9092",
    kafkaClientId: process.env.KAFKA_CLIENT_ID ?? "showcase-console",
    kafkaConsumerGroup:
      process.env.KAFKA_CONSUMER_GROUP ?? "showcase-console",
    kafkaTopics:
      (process.env.KAFKA_TOPICS ?? "fleet.events,fleet.missions,fleet.ops.events,fleet.telemetry,fleet.safety.alerts,warehouse.cameras.aisle3,factory-b.telemetry,factory-b.missions,factory-b.ops.events,mes.orders").split(","),
    wmsStubBaseUrl:
      process.env.WMS_STUB_BASE_URL ?? "http://wms-stub.fleet-ops.svc.cluster.local:8082",
    mjpegUrl: process.env.MJPEG_URL ?? "",
    signalingServer: process.env.SIGNALING_SERVER ?? "",
    turnUrl: process.env.TURN_URL ?? "",
    turnUsername: process.env.TURN_USERNAME ?? "",
    turnCredential: process.env.TURN_CREDENTIAL ?? "",
    githubToken: process.env.GITHUB_TOKEN ?? "",
    githubRepo: process.env.GITHUB_REPO ?? "jeremyary/industrial-ai-showcase",
    clusterAppsDomain: process.env.CLUSTER_APPS_DOMAIN ?? "",
    agenticOrchestratorUrl:
      process.env.AGENTIC_ORCHESTRATOR_URL ??
      "http://agentic-orchestrator.agentic-ops.svc.cluster.local:8080",
  };
}
