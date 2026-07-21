// This project was developed with assistance from AI tools.
import { useEffect, useState } from "react";
import {
  Drawer,
  DrawerActions,
  DrawerCloseButton,
  DrawerContent,
  DrawerContentBody,
  DrawerHead,
  DrawerPanelBody,
  DrawerPanelContent,
  Card,
  CardBody,
  CardTitle,
  Stack,
  StackItem,
  Label,
  DescriptionList,
  DescriptionListDescription,
  DescriptionListGroup,
  DescriptionListTerm,
  Spinner,
} from "@patternfly/react-core";
import { CheckCircleIcon } from "@patternfly/react-icons";
import type { RollbackAnalysis } from "./types.js";

interface RollbackAnalysisDrawerProps {
  analysis: RollbackAnalysis;
  onClose: () => void;
  children: React.ReactNode;
}

export function RollbackAnalysisDrawer({
  analysis,
  onClose,
  children,
}: RollbackAnalysisDrawerProps) {
  const [auditHistory, setAuditHistory] = useState<any[]>([]);
  const [loadingAudit, setLoadingAudit] = useState(true);

  // Fetch recent promotion history
  useEffect(() => {
    fetch("/api/audit/history?limit=10")
      .then(res => res.json())
      .then(data => {
        setAuditHistory(data.history || []);
        setLoadingAudit(false);
      })
      .catch(() => {
        setLoadingAudit(false);
      });
  }, []);
  const panelContent = (
    <DrawerPanelContent isResizable defaultSize="600px" minSize="500px">
      <DrawerHead>
        <span style={{ fontSize: "1.25rem", fontWeight: 600 }}>
          🔍 Agent Rollback Analysis
        </span>
        <DrawerActions>
          <DrawerCloseButton onClick={onClose} />
        </DrawerActions>
      </DrawerHead>
      <DrawerPanelBody>
        <Stack hasGutter>
          {/* Pane 1: Rollback Event Summary */}
          <StackItem>
            <Card>
              <CardTitle>Rollback Event</CardTitle>
              <CardBody>
                <DescriptionList isHorizontal isCompact>
                  <DescriptionListGroup>
                    <DescriptionListTerm>Factory</DescriptionListTerm>
                    <DescriptionListDescription>
                      <strong>{analysis.factory}</strong>
                    </DescriptionListDescription>
                  </DescriptionListGroup>
                  <DescriptionListGroup>
                    <DescriptionListTerm>Rollback</DescriptionListTerm>
                    <DescriptionListDescription>
                      <code>{analysis.from_version}</code> → <code>{analysis.to_version}</code>
                    </DescriptionListDescription>
                  </DescriptionListGroup>
                  <DescriptionListGroup>
                    <DescriptionListTerm>Trigger</DescriptionListTerm>
                    <DescriptionListDescription>
                      <Label color="red">{analysis.trigger}</Label>
                    </DescriptionListDescription>
                  </DescriptionListGroup>
                  <DescriptionListGroup>
                    <DescriptionListTerm>Timestamp</DescriptionListTerm>
                    <DescriptionListDescription>
                      {new Date(analysis.timestamp).toLocaleString()}
                    </DescriptionListDescription>
                  </DescriptionListGroup>
                </DescriptionList>
              </CardBody>
            </Card>
          </StackItem>

          {/* Pane 2: Agent Analysis */}
          <StackItem>
            <Card>
              <CardTitle>Agent Investigation Results</CardTitle>
              <CardBody>
                <div style={{
                  whiteSpace: "pre-wrap",
                  fontFamily: "monospace",
                  fontSize: "0.875rem",
                  lineHeight: 1.6,
                  padding: "12px",
                  backgroundColor: "#f5f5f5",
                  borderRadius: "4px",
                  border: "1px solid #d2d2d2"
                }}>
                  {analysis.agent_analysis}
                </div>
              </CardBody>
            </Card>
          </StackItem>

          {/* Pane 2.5: Recent Promotion Activity */}
          <StackItem>
            <Card>
              <CardTitle>Recent Promotion Activity</CardTitle>
              <CardBody>
                {loadingAudit ? (
                  <Spinner size="md" />
                ) : (
                  <Stack hasGutter>
                    {auditHistory
                      .filter((item: any) =>
                        item.approval_status === "approved" &&
                        item.tool_name === "promote_policy_version"
                      )
                      .slice(0, 3)
                      .map((item: any) => {
                        const args = typeof item.tool_arguments === 'string'
                          ? JSON.parse(item.tool_arguments)
                          : item.tool_arguments;
                        const promotedVersion = args?.model_version || "unknown";
                        const isRolledBackVersion = promotedVersion === analysis.from_version;

                        return (
                          <StackItem key={item.id} style={{
                            padding: "8px",
                            backgroundColor: isRolledBackVersion ? "#fff4e5" : "#f9f9f9",
                            borderLeft: isRolledBackVersion ? "3px solid #f0ab00" : "3px solid #06c",
                            borderRadius: "4px"
                          }}>
                            <div style={{ fontSize: "0.875rem" }}>
                              <div style={{ marginBottom: "4px" }}>
                                <CheckCircleIcon color="green" style={{ marginRight: "6px" }} />
                                <strong>{args?.factory || "Unknown"}</strong> → <code>{promotedVersion}</code>
                                {isRolledBackVersion && (
                                  <Label color="orange" style={{ marginLeft: "8px" }}>
                                    Rolled back
                                  </Label>
                                )}
                              </div>
                              <div style={{ fontSize: "0.75rem", color: "#6a6e73", marginLeft: "20px" }}>
                                Approved {new Date(item.created_at).toLocaleString()}
                              </div>
                            </div>
                          </StackItem>
                        );
                      })}
                    {auditHistory.filter((item: any) =>
                      item.approval_status === "approved" &&
                      item.tool_name === "promote_policy_version"
                    ).length === 0 && (
                      <p style={{ color: "#6a6e73", fontSize: "0.875rem", fontStyle: "italic" }}>
                        No recent promotions found
                      </p>
                    )}
                  </Stack>
                )}
              </CardBody>
            </Card>
          </StackItem>

          {/* Pane 3: Investigation Details */}
          <StackItem>
            <Card>
              <CardTitle>Investigation Details</CardTitle>
              <CardBody>
                <DescriptionList isCompact>
                  <DescriptionListGroup>
                    <DescriptionListTerm>Session ID</DescriptionListTerm>
                    <DescriptionListDescription>
                      <code style={{ fontSize: "0.75rem" }}>{analysis.session_id}</code>
                    </DescriptionListDescription>
                  </DescriptionListGroup>
                  <DescriptionListGroup>
                    <DescriptionListTerm>Investigation Type</DescriptionListTerm>
                    <DescriptionListDescription>
                      Automatic post-rollback analysis (read-only)
                    </DescriptionListDescription>
                  </DescriptionListGroup>
                  <DescriptionListGroup>
                    <DescriptionListTerm>Tools Used</DescriptionListTerm>
                    <DescriptionListDescription>
                      <div style={{ fontSize: "0.875rem" }}>
                        • hil_audit (promotion history)<br/>
                        • get_factory_config (current status)<br/>
                        • get_run (training data)
                      </div>
                    </DescriptionListDescription>
                  </DescriptionListGroup>
                </DescriptionList>
              </CardBody>
            </Card>
          </StackItem>

          {/* Info Box */}
          <StackItem>
            <Card style={{ backgroundColor: "#f0f8ff", border: "1px solid #0066cc" }}>
              <CardBody>
                <p style={{ margin: 0, fontSize: "0.875rem", lineHeight: 1.5 }}>
                  ℹ️ <strong>Safety-first design:</strong> The rollback was executed immediately by the
                  rule-based safety system. The agent investigated <em>after</em> the fact to provide
                  root cause analysis, not to gate the safety action.
                </p>
              </CardBody>
            </Card>
          </StackItem>
        </Stack>
      </DrawerPanelBody>
    </DrawerPanelContent>
  );

  return (
    <Drawer isExpanded isInline>
      <DrawerContent panelContent={panelContent}>
        <DrawerContentBody>{children}</DrawerContentBody>
      </DrawerContent>
    </Drawer>
  );
}
