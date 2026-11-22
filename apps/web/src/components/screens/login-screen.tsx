"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, login, sessionQueryKey, sessionQueryOptions } from "@/lib/api";

const loginSchema = z.object({
  email: z.string().email("Enter a valid email address"),
  password: z.string().min(8, "Password must be at least 8 characters").max(128),
});

type LoginValues = z.infer<typeof loginSchema>;

export function LoginScreen() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const session = useQuery(sessionQueryOptions);
  const form = useForm<LoginValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "", password: "" },
  });
  const mutation = useMutation({
    mutationFn: login,
    onSuccess: (nextSession) => {
      queryClient.setQueryData(sessionQueryKey, nextSession);
      router.replace("/overview");
    },
  });

  useEffect(() => {
    if (session.data) {
      router.replace("/overview");
    }
  }, [router, session.data]);

  if (session.isPending || session.data) {
    return (
      <div className="flex min-h-screen items-center justify-center p-6">
        <div className="w-full max-w-sm space-y-3">
          <Skeleton className="h-8 w-28" />
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
        </div>
      </div>
    );
  }

  const errorMessage =
    mutation.error instanceof ApiError
      ? mutation.error.message
      : mutation.error instanceof Error
        ? mutation.error.message
        : null;

  return (
    <div className="grid min-h-screen lg:grid-cols-[1.1fr_0.9fr]">
      <section className="hidden flex-col justify-between border-r border-border px-12 py-10 lg:flex">
        <div className="flex items-center gap-3">
          <div className="flex size-10 items-center justify-center rounded-lg bg-primary text-sm font-semibold text-primary-foreground">
            A
          </div>
          <div>
            <p className="text-sm font-semibold tracking-wide">ATLAS</p>
            <p className="text-xs text-muted-foreground">Operations</p>
          </div>
        </div>
        <div className="max-w-md">
          <h1 className="text-4xl font-semibold tracking-tight">Business operations command center</h1>
          <p className="mt-4 text-sm leading-6 text-muted-foreground">
            Sign in to the workspace foundation. CRM, agents, workflows, analytics, and approvals are not part of this release.
          </p>
        </div>
        <p className="text-xs text-muted-foreground">Local seed accounts are listed in the project README.</p>
      </section>
      <section className="flex items-center justify-center px-6 py-12">
        <div className="w-full max-w-sm">
          <h2 className="text-2xl font-semibold tracking-tight">Sign in</h2>
          <p className="mt-2 text-sm text-muted-foreground">Use an account from your organization.</p>
          <form
            className="mt-8 space-y-4"
            onSubmit={form.handleSubmit((values) => mutation.mutate(values))}
            noValidate
          >
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                autoComplete="email"
                aria-invalid={Boolean(form.formState.errors.email)}
                {...form.register("email")}
              />
              {form.formState.errors.email ? (
                <p className="text-xs text-red-300">{form.formState.errors.email.message}</p>
              ) : null}
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                aria-invalid={Boolean(form.formState.errors.password)}
                {...form.register("password")}
              />
              {form.formState.errors.password ? (
                <p className="text-xs text-red-300">{form.formState.errors.password.message}</p>
              ) : null}
            </div>
            {errorMessage ? (
              <p role="alert" className="rounded-md border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-200">
                {errorMessage}
              </p>
            ) : null}
            <Button type="submit" className="w-full" disabled={mutation.isPending}>
              {mutation.isPending ? "Signing in…" : "Sign in"}
            </Button>
          </form>
        </div>
      </section>
    </div>
  );
}
