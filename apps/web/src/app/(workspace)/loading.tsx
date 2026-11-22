import { Skeleton } from "@/components/ui/skeleton";

export default function WorkspaceLoading() {
  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-4">
      <Skeleton className="h-8 w-40" />
      <Skeleton className="h-4 w-80" />
      <Skeleton className="h-40 w-full" />
    </div>
  );
}
