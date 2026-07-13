// This project was developed with assistance from AI tools.
import { useState, useEffect } from "react";
import {
  Button,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  Flex,
  FlexItem,
  Form,
  FormGroup,
  Label,
  Spinner,
  Stack,
  StackItem,
  TextArea,
} from "@patternfly/react-core";
import { TimesIcon } from "@patternfly/react-icons";
import { queryAgent, approveRequest, rejectRequest } from "./api.js";
import { HILDrawer } from "./HILDrawer.js";

interface Message {
  role: "user" | "assistant";
  content: string;
  timestamp: string;
  status?: "thinking" | "complete" | "error";
}

interface Suggestion {
  category: string;
  icon: string;
  text: string;
  priority?: number;
}

interface AgentAssistantProps {
  onClose?: () => void;
}

export function AgentAssistant({ onClose }: AgentAssistantProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [pendingApprovalId, setPendingApprovalId] = useState<number | null>(null);
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(true);

  // Load suggestions on mount
  useEffect(() => {
    const loadSuggestions = async () => {
      try {
        const resp = await fetch("/api/agent/suggestions");
        if (resp.ok) {
          const data = (await resp.json()) as { suggestions: Suggestion[] };
          setSuggestions(data.suggestions);
        }
      } catch (err) {
        console.error("Failed to load suggestions:", err);
      }
    };
    void loadSuggestions();
  }, []);

  const handleApprove = async () => {
    if (!pendingApprovalId) return;

    try {
      setLoading(true);
      const result = await approveRequest(pendingApprovalId);

      const resultMessage: Message = {
        role: "assistant",
        content: result.result ?? `✅ Action approved and executed successfully`,
        timestamp: result.timestamp,
        status: "complete",
      };
      setMessages((prev) => [...prev, resultMessage]);
      setPendingApprovalId(null);
    } catch (err) {
      const errorMessage: Message = {
        role: "assistant",
        content: `Error approving request: ${err instanceof Error ? err.message : "Unknown error"}`,
        timestamp: new Date().toISOString(),
        status: "error",
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setLoading(false);
    }
  };

  const handleReject = async (reason: string) => {
    if (!pendingApprovalId) return;

    try {
      setLoading(true);
      const result = await rejectRequest(pendingApprovalId, reason);

      const resultMessage: Message = {
        role: "assistant",
        content: `❌ Action rejected: ${reason}`,
        timestamp: result.timestamp,
        status: "complete",
      };
      setMessages((prev) => [...prev, resultMessage]);
      setPendingApprovalId(null);
    } catch (err) {
      const errorMessage: Message = {
        role: "assistant",
        content: `Error rejecting request: ${err instanceof Error ? err.message : "Unknown error"}`,
        timestamp: new Date().toISOString(),
        status: "error",
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setLoading(false);
    }
  };

  const handleSuggestionClick = (text: string) => {
    setInput(text);
    setShowSuggestions(false);
    // Auto-submit
    setTimeout(() => {
      const form = document.querySelector("form");
      if (form) {
        form.requestSubmit();
      }
    }, 100);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || loading) return;

    const userMessage: Message = {
      role: "user",
      content: input,
      timestamp: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setLoading(true);

    try {
      const response = await queryAgent(input);
      const assistantMessage: Message = {
        role: "assistant",
        content: response.response,
        timestamp: response.timestamp,
        status: "complete",
      };
      setMessages((prev) => [...prev, assistantMessage]);

      // Check if response indicates approval needed
      if (response.response.includes("⏸️") && response.response.includes("approval")) {
        // Extract approval ID from response
        const match = response.response.match(/Request #(\d+)/);
        if (match && match[1]) {
          const approvalId = parseInt(match[1], 10);
          setPendingApprovalId(approvalId);
        }
      }
    } catch (err) {
      const errorMessage: Message = {
        role: "assistant",
        content: `Error: ${err instanceof Error ? err.message : "Agent unavailable"}`,
        timestamp: new Date().toISOString(),
        status: "error",
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setLoading(false);
    }
  };

  const chatContent = (
    <Card isFullHeight>
      <CardHeader>
        <Flex justifyContent={{ default: "justifyContentSpaceBetween" }}>
          <FlexItem>
            <CardTitle>Agent Assistant</CardTitle>
          </FlexItem>
          {onClose && (
            <FlexItem>
              <Button variant="plain" onClick={onClose} aria-label="Close">
                <TimesIcon />
              </Button>
            </FlexItem>
          )}
        </Flex>
      </CardHeader>
      <CardBody>
        <Stack hasGutter style={{ height: "100%" }}>
          {/* Suggested Questions */}
          {showSuggestions && suggestions.length > 0 && messages.length === 0 && (
            <StackItem>
              <Stack hasGutter>
                <StackItem>
                  <div style={{ fontSize: "0.875rem", fontWeight: 600, color: "#151515" }}>
                    Suggested Questions:
                  </div>
                </StackItem>
                <StackItem>
                  <Flex spaceItems={{ default: "spaceItemsSm" }} flexWrap={{ default: "wrap" }}>
                    {suggestions.map((s, idx) => (
                      <FlexItem key={idx}>
                        <Button
                          variant="secondary"
                          isSmall
                          onClick={() => handleSuggestionClick(s.text)}
                        >
                          {s.icon} {s.text}
                        </Button>
                      </FlexItem>
                    ))}
                  </Flex>
                </StackItem>
              </Stack>
            </StackItem>
          )}

          <StackItem isFilled style={{ overflowY: "auto", minHeight: 300, maxHeight: 500 }}>
            {messages.length === 0 && !showSuggestions ? (
              <p style={{ color: "#6a6e73", fontStyle: "italic" }}>
                Ask a question about MLflow experiments, runs, or metrics...
              </p>
            ) : messages.length === 0 ? (
              <p style={{ color: "#6a6e73", fontStyle: "italic", marginTop: 8 }}>
                Or ask your own question below...
              </p>
            ) : (
              <Stack hasGutter>
                {messages.map((msg, idx) => (
                  <StackItem key={idx}>
                    <div
                      style={{
                        padding: 12,
                        borderRadius: 4,
                        backgroundColor: msg.role === "user" ? "#f0f0f0" : "#e7f1fa",
                      }}
                    >
                      <strong>{msg.role === "user" ? "You" : "Agent"}:</strong>{" "}
                      {msg.content}
                      {msg.status === "error" && (
                        <span style={{ color: "#c9190b", marginLeft: 8 }}>(Error)</span>
                      )}
                    </div>
                  </StackItem>
                ))}
                {loading && (
                  <StackItem>
                    <Flex alignItems={{ default: "alignItemsCenter" }}>
                      <FlexItem>
                        <Spinner size="md" />
                      </FlexItem>
                      <FlexItem>
                        <span style={{ color: "#6a6e73" }}>Agent thinking...</span>
                      </FlexItem>
                    </Flex>
                  </StackItem>
                )}
              </Stack>
            )}
          </StackItem>
          <StackItem>
            <Form onSubmit={handleSubmit}>
              <FormGroup>
                <Flex>
                  <FlexItem flex={{ default: "flex_1" }}>
                    <TextArea
                      value={input}
                      onChange={(_event, value) => setInput(value)}
                      placeholder="Ask about experiments, runs, metrics..."
                      rows={2}
                      disabled={loading}
                    />
                  </FlexItem>
                  <FlexItem>
                    <Button type="submit" isDisabled={loading || !input.trim()}>
                      Ask
                    </Button>
                  </FlexItem>
                </Flex>
              </FormGroup>
            </Form>
          </StackItem>
        </Stack>
      </CardBody>
    </Card>
  );

  // Wrap with HIL drawer if approval pending
  if (pendingApprovalId !== null) {
    return (
      <HILDrawer
        approvalId={pendingApprovalId}
        onApprove={handleApprove}
        onReject={handleReject}
        onClose={() => setPendingApprovalId(null)}
      >
        {chatContent}
      </HILDrawer>
    );
  }

  return chatContent;
}