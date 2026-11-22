import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { Membership } from "@/lib/types";

export function MembershipTable({ memberships }: { memberships: Membership[] }) {
  if (memberships.length === 0) {
    return <p className="text-sm text-muted-foreground">This account has no organization memberships.</p>;
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Organization</TableHead>
          <TableHead>Slug</TableHead>
          <TableHead>Role</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {memberships.map((membership) => (
          <TableRow key={membership.id}>
            <TableCell>{membership.organization_name}</TableCell>
            <TableCell className="font-mono text-xs text-muted-foreground">
              {membership.organization_slug}
            </TableCell>
            <TableCell>
              <Badge>{membership.role}</Badge>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
