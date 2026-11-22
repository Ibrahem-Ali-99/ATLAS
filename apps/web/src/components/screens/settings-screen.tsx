"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { MembershipTable } from "@/components/membership-table";
import { SignOutDialog } from "@/components/sign-out-dialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { sessionQueryOptions } from "@/lib/api";

export function SettingsScreen() {
  const session = useQuery(sessionQueryOptions);
  const [signOutOpen, setSignOutOpen] = useState(false);
  const user = session.data?.user;

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
        <p className="mt-1 text-sm leading-6 text-muted-foreground">
          Account details from the current session. Profile editing is not available in this release.
        </p>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Account</CardTitle>
          <CardDescription>Read-only fields returned by the API.</CardDescription>
        </CardHeader>
        <CardContent>
          {session.isPending || !user ? (
            <div className="space-y-2">
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
            </div>
          ) : (
            <div className="grid gap-4">
              <label className="grid gap-2 text-sm">
                <span className="font-medium">Name</span>
                <input
                  readOnly
                  value={user.full_name}
                  className="h-10 rounded-md border border-input bg-background px-3 text-sm"
                />
              </label>
              <label className="grid gap-2 text-sm">
                <span className="font-medium">Email</span>
                <input
                  readOnly
                  value={user.email}
                  className="h-10 rounded-md border border-input bg-background px-3 text-sm"
                />
              </label>
            </div>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Organizations</CardTitle>
          <CardDescription>Roles are stored on the membership, not chosen in the browser.</CardDescription>
        </CardHeader>
        <CardContent>
          {session.isPending || !session.data ? (
            <Skeleton className="h-16 w-full" />
          ) : (
            <MembershipTable memberships={session.data.memberships} />
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Session</CardTitle>
          <CardDescription>Signing out revokes the server session for this browser.</CardDescription>
        </CardHeader>
        <CardContent>
          <Button variant="outline" onClick={() => setSignOutOpen(true)}>
            Sign out
          </Button>
        </CardContent>
      </Card>
      <SignOutDialog open={signOutOpen} onOpenChange={setSignOutOpen} />
    </div>
  );
}
