"use client";

import { useState } from "react";

import { LaunchDemoButton } from "@/components/public/launch-demo-button";
import { CaptureFrame } from "@/components/public/product-shot";
import { Button } from "@/components/ui/button";
import { demoSteps, isReleaseCapture, workspaceRoutes } from "@/lib/public-site";

export function DemoTour() {
  const [index, setIndex] = useState(0);
  const step = demoSteps[index];

  return (
    <div className="grid gap-6 lg:grid-cols-[16rem_1fr]">
      <div className="flex gap-2 overflow-x-auto pb-1 lg:flex-col lg:overflow-visible" role="tablist" aria-label="Demo chapters">
        {demoSteps.map((item, itemIndex) => (
          <button
            key={item.src}
            type="button"
            role="tab"
            id={`demo-tab-${itemIndex}`}
            aria-selected={itemIndex === index}
            aria-controls="demo-panel"
            className={`shrink-0 rounded-lg px-3 py-2 text-left text-sm lg:shrink ${itemIndex === index ? "bg-primary text-primary-foreground" : "bg-card text-foreground ring-1 ring-border hover:bg-accent"}`}
            onClick={() => setIndex(itemIndex)}
          >
            {item.title}
          </button>
        ))}
      </div>
      <div
        id="demo-panel"
        role="tabpanel"
        aria-labelledby={`demo-tab-${index}`}
        tabIndex={0}
        className="min-w-0"
      >
        {isReleaseCapture(step) ? (
          <CaptureFrame capture={step} />
        ) : (
          <div className="rounded-2xl border border-border bg-card p-6 sm:p-8">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-primary">{step.title}</p>
            <p className="mt-4 text-base leading-7">{step.caption}</p>
            <p className="mt-4 text-sm leading-6 text-muted-foreground">
              A release capture for this chapter is a 1440×900 view of the redesigned workspace. The assistant frame stays unpublished until that retrieval work replaces it.
            </p>
          </div>
        )}
        <div className="mt-4 flex flex-wrap gap-2">
          <Button type="button" variant="outline" disabled={index === 0} onClick={() => setIndex((value) => value - 1)}>
            Previous
          </Button>
          <Button type="button" variant="outline" disabled={index === demoSteps.length - 1} onClick={() => setIndex((value) => value + 1)}>
            Next
          </Button>
          <p className="self-center text-sm text-muted-foreground">
            {index + 1} of {demoSteps.length}
          </p>
        </div>
      </div>
      <div className="lg:col-span-2">
        <h2 className="text-xl font-semibold">Open the same modules in the workspace</h2>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
          Launch interactive demo opens these modules in a Harbor & Co. session. The pictures stay on this page.
          The session does not publish a password, and it does not enter an administrator workspace.
        </p>
        <ul className="mt-4 flex flex-wrap gap-2 text-sm text-muted-foreground">
          {workspaceRoutes.map((route) => (
            <li key={route.href} className="rounded-md bg-card px-3 py-1.5 ring-1 ring-border">
              {route.label}
            </li>
          ))}
        </ul>
        <div className="mt-4">
          <LaunchDemoButton />
        </div>
      </div>
    </div>
  );
}
