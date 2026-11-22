import { AssistantView } from "./assistant-view";

export const metadata = { title: "AI Assistant" };

export default async function AssistantPage({ searchParams }: { searchParams: Promise<{ session?: string }> }) {
  const { session } = await searchParams;
  return <AssistantView initialSession={typeof session === "string" && /^[a-f0-9-]{36}$/i.test(session) ? session : ""} />;
}
