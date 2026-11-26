"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { LockKeyhole } from "lucide-react";

import { AuthFrame } from "@/components/screens/auth-frame";
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
    <AuthFrame title="Sign in" description="Welcome back to your ATLAS workspace." icon={<LockKeyhole size={20} />}>
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
                <p role="alert" className="text-xs text-destructive">{form.formState.errors.email.message}</p>
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
                <p role="alert" className="text-xs text-destructive">{form.formState.errors.password.message}</p>
              ) : null}
            </div>
            {errorMessage ? (
              <p role="alert" className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-foreground">
                {errorMessage}
              </p>
            ) : null}
            <Button type="submit" className="w-full" disabled={mutation.isPending}>
              {mutation.isPending ? "Signing in…" : "Sign in"}
            </Button>
          </form>
          <Link href="/forgot-password" className="mt-4 inline-block text-sm font-medium text-primary hover:underline">Forgot password?</Link>
    </AuthFrame>
  );
}
