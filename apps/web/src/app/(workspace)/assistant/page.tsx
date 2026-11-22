import type { Metadata } from "next";

import { UnavailableModule } from "@/components/unavailable-module";

export const metadata: Metadata = {
  title: "AI Assistant",
};

export default function AssistantPage() {
  return (
    <UnavailableModule
      title="AI Assistant"
      description="Conversational assistance is planned for a later sprint. There is no assistant to message in this release."
    />
  );
}
