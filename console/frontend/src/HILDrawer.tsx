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
  Button,
  Card,
  CardBody,
  CardTitle,
  DescriptionList,
  DescriptionListDescription,
  DescriptionListGroup,
  DescriptionListTerm,
  Flex,
  FlexItem,
  Modal,
  ModalVariant,
  TextArea,
  Stack,
  StackItem,
  Label,
  Spinner,
  CodeBlock,
  CodeBlockCode,
} from "@patternfly/react-core";
import { CheckCircleIcon, TimesCircleIcon } from "@patternfly/react-icons";
import type { PendingApproval } from "./api.js";
import { getPendingApprovals } from "./api.js";

interface HILDrawerProps {
  approvalId: number;
  onApprove: () => void;
  onReject: (reason: string) => void;
  onClose: () => void;
  children: React.ReactNode;
}

export function HILDrawer({
  approvalId,
  onApprove,
  onReject,
  onClose,
  children,
}: HILDrawerProps) {
  const [approval, setApproval] = useState<PendingApproval | null>(null);
  const [recentApprovals, setRecentApprovals] = useState<PendingApproval[]>([]);
  const [loading, setLoading] = useState(true);
  const [showRejectModal, setShowRejectModal] = useState(false);
  const [rejectionReason, setRejectionReason] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    const loadApprovalData = async () => {
      try {
        // Get current pending approval
        const pending = await getPendingApprovals();
        const current = pending.find((a) => a.id === approvalId);
        setApproval(current ?? null);

        // Get recent COMPLETED approvals from history (not other pending items)
        const historyResp = await fetch("/api/audit/history?limit=10");
        if (historyResp.ok) {
          const historyData = await historyResp.json() as { history: PendingApproval[] };
          const completedApprovals = historyData.history
            .filter((a) => a.approval_status !== "pending" && a.id !== approvalId)
            .slice(0, 5);
          setRecentApprovals(completedApprovals);
        }
      } catch (err) {
        console.error("Failed to load approval data:", err);
      } finally {
        setLoading(false);
      }
    };

    void loadApprovalData();
  }, [approvalId]);

  const handleApprove = () => {
    setSubmitting(true);
    onApprove();
  };

  const handleRejectClick = () => {
    setShowRejectModal(true);
  };

  const handleRejectSubmit = () => {
    if (!rejectionReason.trim()) return;
    setSubmitting(true);
    onReject(rejectionReason);
    setShowRejectModal(false);
  };

  const panelContent = (
    <DrawerPanelContent isResizable defaultSize="600px" minSize="500px">
      <DrawerHead>
        <span style={{ fontSize: "1.25rem", fontWeight: 600 }}>
          Human-in-the-Loop Approval Required
        </span>
        <DrawerActions>
          <DrawerCloseButton onClick={onClose} />
        </DrawerActions>
      </DrawerHead>
      <DrawerPanelBody>
        {loading ? (
          <Flex justifyContent={{ default: "justifyContentCenter" }} style={{ padding: 40 }}>
            <Spinner size="lg" />
          </Flex>
        ) : !approval ? (
          <div style={{ padding: 20, textAlign: "center", color: "#6a6e73" }}>
            Approval request #{approvalId} not found
          </div>
        ) : (
          <Stack hasGutter>
            {/* Pane 1: Proposed Action */}
            <StackItem>
              <Card>
                <CardTitle>Proposed Action</CardTitle>
                <CardBody>
                  <DescriptionList isHorizontal isCompact>
                    <DescriptionListGroup>
                      <DescriptionListTerm>Tool</DescriptionListTerm>
                      <DescriptionListDescription>
                        <code>{approval.tool_name}</code>
                      </DescriptionListDescription>
                    </DescriptionListGroup>
                    <DescriptionListGroup>
                      <DescriptionListTerm>Arguments</DescriptionListTerm>
                      <DescriptionListDescription>
                        <pre style={{ fontSize: "0.875rem", margin: 0 }}>
                          {JSON.stringify(approval.tool_arguments, null, 2)}
                        </pre>
                      </DescriptionListDescription>
                    </DescriptionListGroup>
                    <DescriptionListGroup>
                      <DescriptionListTerm>Session</DescriptionListTerm>
                      <DescriptionListDescription>
                        {approval.session_id}
                      </DescriptionListDescription>
                    </DescriptionListGroup>
                  </DescriptionList>
                </CardBody>
              </Card>
            </StackItem>

            {/* Pane 2: Review & Impact */}
            <StackItem>
              <Card>
                <CardTitle>Review & Impact</CardTitle>
                <CardBody>
                  <Stack hasGutter>
                    <StackItem>
                      <strong>Action:</strong> {getActionDescription(approval.tool_name)}
                    </StackItem>
                    <StackItem>
                      <strong>Impact:</strong> <Label color="green">LOW</Label>
                    </StackItem>
                    <StackItem>
                      <p style={{ fontSize: "0.875rem", color: "#6a6e73", margin: 0 }}>
                        {getImpactDescription(approval.tool_name)}
                      </p>
                    </StackItem>
                  </Stack>
                </CardBody>
              </Card>
            </StackItem>

            {/* Pane 3: Recent Approvals */}
            <StackItem>
              <Card>
                <CardTitle>Recent Approval History</CardTitle>
                <CardBody>
                  {recentApprovals.length === 0 ? (
                    <p style={{ color: "#6a6e73", fontSize: "0.875rem", fontStyle: "italic" }}>
                      No recent approvals
                    </p>
                  ) : (
                    <Stack hasGutter>
                      {recentApprovals.map((item) => (
                        <StackItem key={item.id}>
                          <Flex alignItems={{ default: "alignItemsCenter" }}>
                            <FlexItem spacer={{ default: "spacerSm" }}>
                              {item.approval_status === "approved" ? (
                                <CheckCircleIcon color="green" />
                              ) : (
                                <TimesCircleIcon color="red" />
                              )}
                            </FlexItem>
                            <FlexItem flex={{ default: "flex_1" }}>
                              <div style={{ fontSize: "0.875rem" }}>
                                <strong>ID {item.id}:</strong> {item.tool_name}
                              </div>
                              <div style={{ fontSize: "0.75rem", color: "#6a6e73" }}>
                                {new Date(item.timestamp).toLocaleString()}
                              </div>
                            </FlexItem>
                          </Flex>
                        </StackItem>
                      ))}
                    </Stack>
                  )}
                </CardBody>
              </Card>
            </StackItem>

            {/* Pane 4: Proposed Git Changes (only for promote_policy_version) */}
            {approval.tool_name === "promote_policy_version" && approval.git_diff && (
              <StackItem>
                <Card>
                  <CardTitle>Proposed Git Changes</CardTitle>
                  <CardBody>
                    <Stack hasGutter>
                      {approval.summary && (
                        <StackItem>
                          <div
                            style={{
                              fontSize: "0.875rem",
                              color: "#6a6e73",
                              borderLeft: "3px solid #06c",
                              paddingLeft: 12,
                              marginBottom: 8,
                            }}
                          >
                            <strong>Summary:</strong>
                            <div style={{ marginTop: 4 }}>
                              {approval.summary.split("\n").map((line, idx) => (
                                <div key={idx}>{line}</div>
                              ))}
                            </div>
                          </div>
                        </StackItem>
                      )}
                      <StackItem>
                        <div style={{ fontSize: "0.875rem", marginBottom: 8 }}>
                          <strong>Changes to be committed:</strong>
                        </div>
                        <CodeBlock>
                          <CodeBlockCode
                            style={{
                              fontFamily: "monospace",
                              fontSize: "0.75rem",
                              maxHeight: "400px",
                              overflow: "auto",
                              whiteSpace: "pre",
                            }}
                          >
                            {approval.git_diff}
                          </CodeBlockCode>
                        </CodeBlock>
                      </StackItem>
                      <StackItem>
                        <div
                          style={{
                            fontSize: "0.75rem",
                            color: "#6a6e73",
                            fontStyle: "italic",
                            backgroundColor: "#f5f5f5",
                            padding: 8,
                            borderRadius: 4,
                          }}
                        >
                          <strong>Note:</strong> These changes will be committed to a new Git branch
                          and opened as a Pull Request. Argo CD will sync the cluster after PR merge.
                          No direct cluster API calls will be made.
                        </div>
                      </StackItem>
                    </Stack>
                  </CardBody>
                </Card>
              </StackItem>
            )}

            {/* Action Buttons */}
            <StackItem>
              <Flex justifyContent={{ default: "justifyContentSpaceBetween" }}>
                <FlexItem>
                  <Button
                    variant="danger"
                    onClick={handleRejectClick}
                    isDisabled={submitting}
                  >
                    Reject
                  </Button>
                </FlexItem>
                <FlexItem>
                  <Button
                    variant="primary"
                    onClick={handleApprove}
                    isDisabled={submitting}
                    isLoading={submitting}
                  >
                    Approve
                  </Button>
                </FlexItem>
              </Flex>
            </StackItem>
          </Stack>
        )}
      </DrawerPanelBody>

      {/* Rejection Reason Modal */}
      {showRejectModal && (
        <Modal
          variant={ModalVariant.small}
          title="Rejection Reason"
          isOpen={showRejectModal}
          onClose={() => setShowRejectModal(false)}
        >
          <Stack hasGutter>
            <StackItem>
              <p>Please provide a reason for rejecting this action:</p>
            </StackItem>
            <StackItem>
              <TextArea
                value={rejectionReason}
                onChange={(_event, value) => setRejectionReason(value)}
                placeholder="e.g., Model name conflicts with existing model"
                rows={4}
                autoFocus
              />
            </StackItem>
            <StackItem>
              <Flex justifyContent={{ default: "justifyContentFlexEnd" }}>
                <FlexItem>
                  <Button variant="link" onClick={() => setShowRejectModal(false)}>
                    Cancel
                  </Button>
                </FlexItem>
                <FlexItem>
                  <Button
                    variant="danger"
                    onClick={handleRejectSubmit}
                    isDisabled={!rejectionReason.trim()}
                  >
                    Submit Rejection
                  </Button>
                </FlexItem>
              </Flex>
            </StackItem>
          </Stack>
        </Modal>
      )}
    </DrawerPanelContent>
  );

  return (
    <Drawer isExpanded={true} isInline>
      <DrawerContent panelContent={panelContent}>
        <DrawerContentBody>{children}</DrawerContentBody>
      </DrawerContent>
    </Drawer>
  );
}

// Helper functions for descriptions
function getActionDescription(toolName: string): string {
  switch (toolName) {
    case "register_model":
      return "Register a new model in MLflow model registry";
    case "promote_policy_version":
      return "Promote model policy version to factory via Git PR";
    default:
      return "Execute state-modifying operation";
  }
}

function getImpactDescription(toolName: string): string {
  switch (toolName) {
    case "register_model":
      return "This action will create a new model entry in the MLflow registry. The model metadata will be stored in the database and versioned.";
    case "promote_policy_version":
      return "This action will generate a Kustomize overlay and open a GitHub Pull Request. The cluster will be updated via Argo CD after PR merge. No direct cluster API calls will be made.";
    default:
      return "This action will modify system state.";
  }
}
