"use client";

import { useState } from "react";
import Link from "next/link";

import { ProductShot } from "@/components/public/product-shot";
import { Button } from "@/components/ui/button";
import { demoSteps, workspaceRoutes } from "@/lib/public-site";

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
        <ProductShot src={step.src} alt={step.alt} caption={step.caption} />
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
          These links go to the application. The workspace asks for a session before it loads organization data.
          Sign in only on a deployment prepared for visitors. This page does not publish a password, and it does not create a session.
        </p>
        <ul className="mt-4 flex flex-wrap gap-2">
          {workspaceRoutes.map((route) => (
            <li key={route.href}>
              <Button asChild variant="outline" size="sm">
                <Link href={route.href}>{route.label}</Link>
              </Button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
