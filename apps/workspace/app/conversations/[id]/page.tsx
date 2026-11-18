import { ConversationGate } from "@/features/conversation";

export default async function ConversationPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ConversationGate conversationId={id} />;
}
