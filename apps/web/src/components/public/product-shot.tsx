"use client";

import Image from "next/image";

import { fitsLandscapeFrame, phoneFrame, type ProductCapture } from "@/lib/public-site";

const frameClass =
  "overflow-hidden rounded-2xl border border-border bg-card shadow-[0_32px_80px_-48px_rgba(23,25,29,0.55)]";

export function ProductWindow({
  capture,
  priority = false,
  alt,
}: {
  capture: ProductCapture;
  priority?: boolean;
  alt?: string;
}) {
  return (
    <figure className={frameClass}>
      <div className="flex items-center gap-3 border-b border-border bg-muted/70 px-4 py-2.5">
        <span className="flex gap-1.5" aria-hidden="true">
          <span className="size-2 rounded-full bg-[var(--border-strong)]" />
          <span className="size-2 rounded-full bg-[var(--border-strong)]" />
          <span className="size-2 rounded-full bg-[var(--border-strong)]" />
        </span>
        <span className="truncate text-xs text-muted-foreground">{capture.frame ? `${capture.title} · ${capture.frame}` : capture.title}</span>
      </div>
      <div className="relative aspect-[16/10] bg-[#111318]">
        <Image
          src={capture.src}
          alt={alt ?? capture.alt}
          fill
          priority={priority}
          sizes="(min-width: 1024px) 720px, 100vw"
          className="object-cover object-top"
        />
      </div>
      <figcaption className="border-t border-border px-5 py-4 text-sm leading-6 text-muted-foreground">
        {capture.caption}
      </figcaption>
    </figure>
  );
}

export function CaptureFrame({ capture }: { capture: ProductCapture }) {
  if (capture.width <= phoneFrame.width) {
    return (
      <figure className={frameClass}>
        <DeviceShot capture={capture} />
        <figcaption className="border-t border-border px-5 py-4 text-sm leading-6 text-muted-foreground">
          {capture.caption}
        </figcaption>
      </figure>
    );
  }

  if (fitsLandscapeFrame(capture)) {
    return <ProductWindow capture={capture} />;
  }

  return (
    <figure className={frameClass}>
      <div className="flex items-center gap-3 border-b border-border bg-muted/70 px-4 py-2.5">
        <span className="truncate text-xs text-muted-foreground">{capture.title} · full capture</span>
      </div>
      <div
        tabIndex={0}
        aria-label={`${capture.title} capture. Scroll to see the rest of the page.`}
        className="max-h-[min(70vh,40rem)] overflow-y-auto bg-[#111318]"
      >
        <Image
          src={capture.src}
          alt={capture.alt}
          width={capture.width}
          height={capture.height}
          sizes="(min-width: 1024px) 860px, 100vw"
          className="h-auto w-full"
        />
      </div>
      <figcaption className="border-t border-border px-5 py-4 text-sm leading-6 text-muted-foreground">
        {capture.caption} The picture keeps its own proportions. Scroll inside the frame to see the rest.
      </figcaption>
    </figure>
  );
}

export function DeviceShot({ capture }: { capture: ProductCapture }) {
  return (
    <div className="flex justify-center bg-[radial-gradient(ellipse_at_center,var(--accent),transparent_70%)] px-6 py-10">
      <div className="w-[17.5rem] max-w-full rounded-[2rem] border border-[var(--border-strong)] bg-card p-2 shadow-[0_24px_50px_-32px_rgba(23,25,29,0.6)]">
        <div
          tabIndex={0}
          aria-label={`${capture.title}. Scroll to see the rest of the narrow layout.`}
          className="overflow-y-auto rounded-[1.6rem] bg-[#111318]"
          style={{ height: `min(36rem, ${phoneFrame.height}px)` }}
        >
          <Image
            src={capture.src}
            alt={capture.alt}
            width={capture.width}
            height={capture.height}
            sizes="280px"
            className="h-auto w-full"
          />
        </div>
      </div>
    </div>
  );
}
