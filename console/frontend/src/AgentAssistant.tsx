// This project was developed with assistance from AI tools.
import { useState } from "react";
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
  Spinner,
  Stack,
  StackItem,
  TextArea,
} from "@patternfly/react-core";
import { TimesIcon } from "@patternfly/react-icons";
import { queryAgent } from "./api.js";

interface Message {
  role: "user" | "assistant";
  content: string;
  timestamp: string;
  status?: "thinking" | "complete" | "error";
}

interface AgentAssistantProps {
  onClose?: () => void;
}

export function AgentAssistant({ onClose }: AgentAssistantProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);

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

  return (
    <Card isFullHeight>
      <CardHeader>
        <Flex justifyContent={{ default: "justifyContentSpaceBetween" }}>
          <FlexItem>
            <CardTitle>Agent Assistant (Read-Only)</CardTitle>
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
          <StackItem isFilled style={{ overflowY: "auto", minHeight: 300, maxHeight: 500 }}>
            {messages.length === 0 ? (
              <p style={{ color: "#6a6e73", fontStyle: "italic" }}>
                Ask a question about MLflow experiments, runs, or metrics...
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
}