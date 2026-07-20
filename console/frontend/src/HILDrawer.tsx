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
  Alert,
  AlertActionLink,
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

            {/* Pane 4: Blast Radius (only for promote_policy_version) */}
            {approval.tool_name === "promote_policy_version" && approval.blast_radius && (
              <StackItem>
                <Card>
                  <CardTitle>Blast Radius</CardTitle>
                  <CardBody>
                    <Stack hasGutter>
                      <StackItem>
                        <DescriptionList isHorizontal isCompact>
                          <DescriptionListGroup>
                            <DescriptionListTerm>Factory</DescriptionListTerm>
                            <DescriptionListDescription>
                              <strong>{approval.blast_radius.factory}</strong>
                            </DescriptionListDescription>
                          </DescriptionListGroup>
                          <DescriptionListGroup>
                            <DescriptionListTerm>Robots Affected</DescriptionListTerm>
                            <DescriptionListDescription>
                              <strong>{approval.blast_radius.robot_count}</strong>
                            </DescriptionListDescription>
                          </DescriptionListGroup>
                          <DescriptionListGroup>
                            <DescriptionListTerm>Version Change</DescriptionListTerm>
                            <DescriptionListDescription>
                              <code>{approval.blast_radius.current_version}</code>
                              {" → "}
                              <code>{approval.blast_radius.target_version}</code>
                            </DescriptionListDescription>
                          </DescriptionListGroup>
                          <DescriptionListGroup>
                            <DescriptionListTerm>Impact Level</DescriptionListTerm>
                            <DescriptionListDescription>
                              <Label
                                color={
                                  approval.blast_radius.impact_level === "low"
                                    ? "green"
                                    : approval.blast_radius.impact_level === "medium"
                                    ? "orange"
                                    : "red"
                                }
                              >
                                {approval.blast_radius.impact_level.toUpperCase()}
                              </Label>
                            </DescriptionListDescription>
                          </DescriptionListGroup>
                        </DescriptionList>
                      </StackItem>
                      <StackItem>
                        <div
                          style={{
                            fontSize: "0.875rem",
                            color: "#6a6e73",
                            backgroundColor: "#f5f5f5",
                            padding: 12,
                            borderRadius: 4,
                          }}
                        >
                          This promotion will update <strong>{approval.blast_radius.robot_count}</strong> robot
                          {approval.blast_radius.robot_count !== 1 ? "s" : ""} in{" "}
                          <strong>{approval.blast_radius.factory}</strong> from version{" "}
                          <code>{approval.blast_radius.current_version}</code> to{" "}
                          <code>{approval.blast_radius.target_version}</code>.
                        </div>
                      </StackItem>
                    </Stack>
                  </CardBody>
                </Card>
              </StackItem>
            )}

            {/* Pane 5: Guardrails (if moderation results available) */}
            {approval.moderation_results && (
              <StackItem>
                <Card>
                  <CardTitle>Safety Guardrails</CardTitle>
                  <CardBody>
                    <Stack hasGutter>
                      {/* Input Moderation */}
                      <StackItem>
                        <DescriptionList isHorizontal isCompact>
                          <DescriptionListGroup>
                            <DescriptionListTerm>Input Check</DescriptionListTerm>
                            <DescriptionListDescription>
                              <Label
                                color={
                                  approval.moderation_results.input.decision === "allowed"
                                    ? "green"
                                    : approval.moderation_results.input.decision === "blocked"
                                    ? "red"
                                    : "orange"
                                }
                              >
                                {approval.moderation_results.input.decision.toUpperCase()}
                              </Label>
                            </DescriptionListDescription>
                          </DescriptionListGroup>
                          {approval.moderation_results.input.categories.length > 0 && (
                            <DescriptionListGroup>
                              <DescriptionListTerm>Flagged Categories</DescriptionListTerm>
                              <DescriptionListDescription>
                                {approval.moderation_results.input.categories.join(", ")}
                              </DescriptionListDescription>
                            </DescriptionListGroup>
                          )}
                          <DescriptionListGroup>
                            <DescriptionListTerm>Input Latency</DescriptionListTerm>
                            <DescriptionListDescription>
                              {approval.moderation_results.input.latency_ms.toFixed(0)}ms
                            </DescriptionListDescription>
                          </DescriptionListGroup>
                        </DescriptionList>
                      </StackItem>

                      {/* Output Moderation */}
                      <StackItem>
                        <DescriptionList isHorizontal isCompact>
                          <DescriptionListGroup>
                            <DescriptionListTerm>Output Check</DescriptionListTerm>
                            <DescriptionListDescription>
                              <Label
                                color={
                                  approval.moderation_results.output.decision === "allowed"
                                    ? "green"
                                    : approval.moderation_results.output.decision === "blocked"
                                    ? "red"
                                    : "orange"
                                }
                              >
                                {approval.moderation_results.output.decision.toUpperCase()}
                              </Label>
                            </DescriptionListDescription>
                          </DescriptionListGroup>
                          {approval.moderation_results.output.categories.length > 0 && (
                            <DescriptionListGroup>
                              <DescriptionListTerm>Flagged Categories</DescriptionListTerm>
                              <DescriptionListDescription>
                                {approval.moderation_results.output.categories.join(", ")}
                              </DescriptionListDescription>
                            </DescriptionListGroup>
                          )}
                          <DescriptionListGroup>
                            <DescriptionListTerm>Output Latency</DescriptionListTerm>
                            <DescriptionListDescription>
                              {approval.moderation_results.output.latency_ms.toFixed(0)}ms
                            </DescriptionListDescription>
                          </DescriptionListGroup>
                        </DescriptionList>
                      </StackItem>

                      <StackItem>
                        <div
                          style={{
                            fontSize: "0.75rem",
                            color: "#6a6e73",
                            backgroundColor: "#f5f5f5",
                            padding: 8,
                            borderRadius: 4,
                          }}
                        >
                          <strong>Llama Guard 3-8B:</strong> Content moderation powered by Meta's safety model.
                          All requests are checked for harmful content before and after LLM processing.
                        </div>
                      </StackItem>
                    </Stack>
                  </CardBody>
                </Card>
              </StackItem>
            )}

            {/* Pane 5.5: Context Trail - Tool Call Trace */}
            {approval.tool_call_trace && approval.tool_call_trace.length > 0 && (
              <StackItem>
                <Card>
                  <CardTitle>Context Trail</CardTitle>
                  <CardBody>
                    <div style={{ fontSize: "0.875rem", marginBottom: 8, color: "#6a6e73" }}>
                      Read-only tool calls the agent made before requesting approval:
                    </div>
                    <Stack hasGutter>
                      {approval.tool_call_trace.map((call, idx) => (
                        <StackItem key={idx}>
                          <div
                            style={{
                              padding: 12,
                              background: "#f5f5f5",
                              borderRadius: 4,
                              borderLeft: call.success ? "3px solid #3e8635" : "3px solid #c9190b",
                            }}
                          >
                            <div style={{ display: "flex", alignItems: "center", marginBottom: 6 }}>
                              <span style={{ fontWeight: 600, color: "#151515", marginRight: 8 }}>
                                {idx + 1}. {call.tool_name}
                              </span>
                              <span
                                style={{
                                  fontSize: "0.75rem",
                                  color: "#6a6e73",
                                  marginLeft: "auto",
                                }}
                              >
                                {call.duration_ms}ms
                              </span>
                            </div>
                            {Object.keys(call.arguments).length > 0 && (
                              <div style={{ fontSize: "0.813rem", color: "#6a6e73", marginBottom: 4 }}>
                                <strong>Args:</strong>{" "}
                                {JSON.stringify(call.arguments, null, 0)}
                              </div>
                            )}
                            <div style={{ fontSize: "0.813rem", color: "#151515", fontFamily: "monospace" }}>
                              → {call.response_summary}
                            </div>
                          </div>
                        </StackItem>
                      ))}
                    </Stack>
                  </CardBody>
                </Card>
              </StackItem>
            )}

            {/* Pane 6: Proposed Git Changes (only for promote_policy_version) */}
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

            {/* Merge Error Alert (if PR merge failed) */}
            {approval.approval_status === "merge_failed" && approval.merge_error && (
              <StackItem>
                <Alert
                  variant="danger"
                  isInline
                  title="PR Merge Failed"
                  actionLinks={
                    approval.pr_url ? (
                      <AlertActionLink
                        onClick={() => window.open(approval.pr_url, "_blank")}
                      >
                        View PR #{approval.merge_error.pr_number}
                      </AlertActionLink>
                    ) : undefined
                  }
                >
                  <Stack hasGutter>
                    <StackItem>
                      <strong>Error Type:</strong> {approval.merge_error.error_type}
                    </StackItem>
                    <StackItem>
                      <strong>Details:</strong> {approval.merge_error.error}
                    </StackItem>
                    <StackItem>
                      <div style={{ fontSize: "0.875rem", marginTop: 8 }}>
                        {approval.merge_error.error_type === "conflict" && (
                          <div>
                            <strong>Next Steps:</strong>
                            <ol style={{ marginTop: 4, marginLeft: 20 }}>
                              <li>Click the PR link above to view the conflict</li>
                              <li>Resolve conflicts in GitHub or locally</li>
                              <li>Merge the PR manually once conflicts are resolved</li>
                            </ol>
                          </div>
                        )}
                        {approval.merge_error.error_type === "checks_failed" && (
                          <div>
                            <strong>Next Steps:</strong>
                            <ol style={{ marginTop: 4, marginLeft: 20 }}>
                              <li>Click the PR link to view failing checks</li>
                              <li>Fix the issues causing check failures</li>
                              <li>Wait for checks to pass, then merge manually</li>
                            </ol>
                          </div>
                        )}
                        {approval.merge_error.error_type === "not_mergeable" && (
                          <div>
                            <strong>Next Steps:</strong>
                            <ol style={{ marginTop: 4, marginLeft: 20 }}>
                              <li>Review branch protection rules</li>
                              <li>Ensure required reviews are approved</li>
                              <li>Merge manually once requirements are met</li>
                            </ol>
                          </div>
                        )}
                      </div>
                    </StackItem>
                  </Stack>
                </Alert>
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
