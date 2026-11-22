import { Badge } from "@/components/ui/badge";

export function UnavailableModule({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <div className="mx-auto flex w-full max-w-xl flex-col items-start gap-4 rounded-xl border border-dashed border-border bg-card px-8 py-12">
      <Badge variant="secondary">Not in this release</Badge>
      <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
      <p className="text-sm leading-6 text-muted-foreground">{description}</p>
    </div>
  );
}
