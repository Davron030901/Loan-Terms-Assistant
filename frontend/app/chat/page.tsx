import { Suspense } from "react";
import { ChatShell } from "@/components/chat/ChatShell";

export const metadata = {
  title: "Assistant",
  description: "Ask about one real bank loan contract. Off-topic questions are refused.",
};

export default function ChatPage() {
  return (
    <Suspense
      fallback={
        <div className="flex h-[100dvh] items-center justify-center">
          <span className="pulse-dot h-3 w-3 rounded-full bg-brand-500" />
        </div>
      }
    >
      <ChatShell />
    </Suspense>
  );
}
