import { ResearchScreen } from "../../../components/research-screen";

export default async function ResearchPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <ResearchScreen sessionId={id} />;
}
