// This project was developed with assistance from AI tools.
import { useEffect, useState } from "react";
import {
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  Flex,
  FlexItem,
  Label,
  Stack,
  StackItem,
  ToggleGroup,
  ToggleGroupItem,
} from "@patternfly/react-core";
import type { Topology } from "./types.js";
import { fetchTopology } from "./api.js";
import { PlatformGovernanceTab } from "./PlatformGovernanceTab.js";
import archDiagram from "./phases-1-2-arch.png";

type ArchView = "purdue" | "diagram" | "governance";

const PURDUE_LEVELS = [
  {
    level: 4,
    label: "Level 4 — Enterprise / Central Hub",
    color: "#0066CC",
    components: [
      { name: "Training Pipelines (DSPA)", ns: "vla-training", role: "VLA fine-tuning orchestration" },
      { name: "Model Registry", ns: "redhat-ods-applications", role: "Model versioning + lineage" },
      { name: "MLflow + MinIO", ns: "mlflow", role: "Experiment tracking + artifact storage" },
      { name: "AMQ Streams (Hub)", ns: "fleet-ops", role: "Fleet telemetry aggregation & analytics" },
      { name: "Argo CD", ns: "openshift-gitops", role: "GitOps policy rollout" },
      { name: "Advanced Cluster Mgmt", ns: "open-cluster-management", role: "Multi-site cluster governance" },
      { name: "Sigstore", ns: "openshift-pipelines", role: "Image signing & attestation policy" },
      { name: "Edge Manager", ns: "open-cluster-management", role: "Edge device management" },
      { name: "Central Console", ns: "fleet-ops", role: "Multi-site oversight dashboard" },
    ],
  },
  {
    level: 3,
    label: "Level 3 — Site Operations",
    color: "#3E8635",
    components: [
      { name: "AMQ Streams (Site)", ns: "fleet-ops", role: "Local event backbone / MirrorMaker" },
      { name: "Cosmos Reason 2-8B", ns: "cosmos", role: "Vision language model — obstruction detection" },
      { name: "Warehouse Mgmt System", ns: "fleet-ops", role: "Work orders / inventory" },
      { name: "Fleet Mgmt / Dispatch", ns: "fleet-ops", role: "Route execution engine" },
      { name: "Isaac Sim", ns: "isaac-sim", role: "Digital twin simulation" },
      { name: "Nucleus", ns: "nucleus", role: "Asset store / physics" },
    ],
  },
  {
    level: 2,
    label: "Level 2 — HMI / SCADA",
    color: "#F0AB00",
    components: [
      { name: "PLC / SCADA Systems", ns: "factory-floor", role: "Legacy bridge — OPC-UA gateway" },
    ],
  },
  {
    level: 1,
    label: "Level 1 — Field Devices / Robot Edge",
    color: "#A30000",
    components: [
      { name: "Robot / Equipment", ns: "robot-edge", role: "GR00T VLA + SONIC WBC" },
      { name: "IP Cameras", ns: "warehouse-edge", role: "Warehouse aisle video feeds" },
      { name: "Sensors", ns: "factory-floor", role: "Telemetry / environmental" },
    ],
  },
];

export function ArchitectureView() {
  const [topology, setTopology] = useState<Topology | null>(null);
  const [view, setView] = useState<ArchView>("purdue");

  useEffect(() => {
    fetchTopology().then(setTopology).catch(() => undefined);
  }, []);

  return (
    <Stack hasGutter>
      <StackItem>
        <ToggleGroup aria-label="Architecture view toggle">
          <ToggleGroupItem
            text="Purdue Model"
            isSelected={view === "purdue"}
            onChange={() => setView("purdue")}
          />
          <ToggleGroupItem
            text="Reference Architecture"
            isSelected={view === "diagram"}
            onChange={() => setView("diagram")}
          />
          <ToggleGroupItem
            text="Platform Governance"
            isSelected={view === "governance"}
            onChange={() => setView("governance")}
          />
        </ToggleGroup>
      </StackItem>

      {view === "governance" ? (
        <StackItem>
          <PlatformGovernanceTab />
        </StackItem>
      ) : view === "diagram" ? (
        <StackItem>
          <Card>
            <CardHeader>
              <CardTitle>Reference Architecture — Phases 1 & 2</CardTitle>
            </CardHeader>
            <CardBody>
              <img
                src={archDiagram}
                alt="Physical AI Reference Architecture — Central Hub and On-Site"
                style={{ width: "100%", height: "auto", borderRadius: 4 }}
              />
            </CardBody>
          </Card>
        </StackItem>
      ) : (
        <>
          <StackItem>
            <Card>
              <CardHeader>
                <CardTitle>System Architecture — Purdue Model Overlay</CardTitle>
              </CardHeader>
              <CardBody>
                <Stack hasGutter>
                  {PURDUE_LEVELS.map((level) => (
                    <StackItem key={level.level}>
                      <div
                        style={{
                          borderLeft: `4px solid ${level.color}`,
                          paddingLeft: 16,
                          marginBottom: 8,
                        }}
                      >
                        <div style={{ fontWeight: 600, marginBottom: 8, color: level.color }}>
                          {level.label}
                        </div>
                        <Flex
                          spaceItems={{ default: "spaceItemsSm" }}
                          flexWrap={{ default: "wrap" }}
                        >
                          {level.components.map((c) => (
                            <FlexItem key={c.name}>
                              <div className="showcase-arch-component">
                                <div style={{ fontWeight: 600 }}>{c.name}</div>
                                <div style={{ fontSize: 12, color: "#6A6E73" }}>{c.ns}</div>
                                <div style={{ fontSize: 12, color: "#6A6E73" }}>{c.role}</div>
                              </div>
                            </FlexItem>
                          ))}
                        </Flex>
                      </div>
                    </StackItem>
                  ))}
                </Stack>
              </CardBody>
            </Card>
          </StackItem>

          <StackItem>
            <Flex spaceItems={{ default: "spaceItemsLg" }}>
              <FlexItem flex={{ default: "flex_1" }}>
                <Card isFullHeight>
                  <CardHeader><CardTitle>KubeVirt VM</CardTitle></CardHeader>
                  <CardBody>
                    <Stack hasGutter>
                      <StackItem>
                        <Label color="purple" isCompact>companion cluster</Label>
                        {" "}plc-gateway-01
                      </StackItem>
                      <StackItem>
                        <div style={{ fontSize: 13, color: "#6A6E73" }}>
                          Namespace: factory-floor
                        </div>
                        <div style={{ fontSize: 13, color: "#6A6E73" }}>
                          OPC-UA server on port 4840
                        </div>
                        <div style={{ fontSize: 13, color: "#6A6E73" }}>
                          Fedora 40 — containerDisk + cloud-init
                        </div>
                      </StackItem>
                      <StackItem>
                        <div style={{ fontSize: 12, color: "#6A6E73", fontStyle: "italic" }}>
                          OpenShift Virtualization runs legacy PLC/HMI gateways alongside container workloads
                        </div>
                      </StackItem>
                    </Stack>
                  </CardBody>
                </Card>
              </FlexItem>

              <FlexItem flex={{ default: "flex_1" }}>
                <Card isFullHeight>
                  <CardHeader><CardTitle>MES Order Flow</CardTitle></CardHeader>
                  <CardBody>
                    <Stack hasGutter>
                      <StackItem>
                        <Label color="blue" isCompact>mes.orders</Label>
                        {" → Fleet Manager → "}
                        <Label color="green" isCompact>fleet.missions</Label>
                      </StackItem>
                      <StackItem>
                        <div style={{ fontSize: 13, color: "#6A6E73" }}>
                          SAP PP/DS-shaped production orders translated into robot missions
                        </div>
                      </StackItem>
                    </Stack>
                  </CardBody>
                </Card>
              </FlexItem>

              <FlexItem flex={{ default: "flex_1" }}>
                <Card isFullHeight>
                  <CardHeader><CardTitle>Air-Gap Path</CardTitle></CardHeader>
                  <CardBody>
                    <Stack hasGutter>
                      <StackItem>
                        <div style={{ fontSize: 13, color: "#6A6E73" }}>
                          Mirror registry → OCI artifacts → disconnected install
                        </div>
                        <div style={{ fontSize: 13, color: "#6A6E73" }}>
                          Every dependency mirrorable; no live internet at runtime
                        </div>
                      </StackItem>
                    </Stack>
                  </CardBody>
                </Card>
              </FlexItem>
            </Flex>
          </StackItem>
        </>
      )}
    </Stack>
  );
}
