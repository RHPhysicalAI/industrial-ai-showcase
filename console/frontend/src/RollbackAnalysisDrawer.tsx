// This project was developed with assistance from AI tools.
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
} from "@patternfly/react-core";
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
