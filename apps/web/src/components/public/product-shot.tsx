"use client";

import Image from "next/image";

export function ProductShot({
  src,
  alt,
  caption,
  priority = false,
}: {
  src: string;
  alt: string;
  caption: string;
  priority?: boolean;
}) {
  return (
    <figure className="overflow-hidden rounded-xl border border-border bg-card shadow-[0_28px_70px_-36px_rgba(23,25,29,0.55)]">
      <Image
        src={src}
        alt={alt}
        width={1440}
        height={960}
        priority={priority}
        sizes="(min-width: 1024px) 760px, 100vw"
        className="h-auto w-full"
      />
      <figcaption className="border-t border-border px-4 py-3 text-sm leading-6 text-muted-foreground">
        {caption}
      </figcaption>
    </figure>
  );
}
