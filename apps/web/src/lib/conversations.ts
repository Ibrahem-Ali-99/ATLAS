import type { Conversation } from "@/lib/records";

/**
 * Retrieval checks posted conversations titled "eval" and left those rows in place.
 * The product keeps them and shows them apart from customer conversations.
 */
export function isEvaluationConversation(conversation: Pick<Conversation, "title">): boolean {
  return conversation.title.trim().toLowerCase() === "eval";
}
