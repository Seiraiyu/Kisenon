"use client";

import { useChat } from "@ai-sdk/react";
import { useState } from "react";

export default function Page() {
  const [input, setInput] = useState("");
  const { messages, sendMessage, status, stop, error } = useChat();

  return (
    <main>
      <h1>Ask the shop database</h1>
      {messages.map((m) => (
        <div key={m.id} style={{ margin: "1rem 0" }}>
          <b>{m.role === "user" ? "You" : "AI"}:</b>
          {m.parts.map((part, i) => {
            switch (part.type) {
              case "text":
                return <p key={i}>{part.text}</p>;
              case "tool-query":
                switch (part.state) {
                  case "input-streaming":
                  case "input-available":
                    return <pre key={i}>running: {JSON.stringify(part.input)}</pre>;
                  case "output-available":
                    return (
                      <details key={i}>
                        <summary>query: {JSON.stringify(part.input)}</summary>
                        <pre>{JSON.stringify(part.output, null, 2)}</pre>
                      </details>
                    );
                  case "output-error":
                    return <pre key={i}>tool error: {part.errorText}</pre>;
                  default:
                    return null;
                }
              default:
                return null;
            }
          })}
        </div>
      ))}
      {error && <p style={{ color: "crimson" }}>{error.message}</p>}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (!input.trim()) return;
          sendMessage({ text: input });
          setInput("");
        }}
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={status !== "ready"}
          placeholder="Which country ordered the most toys last month?"
          style={{ width: "100%", padding: "0.5rem" }}
        />
        {(status === "submitted" || status === "streaming") && (
          <button type="button" onClick={stop}>Stop</button>
        )}
      </form>
    </main>
  );
}
