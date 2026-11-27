import type { ReactNode } from "react";

import "./site.css";

const links = [
  { href: "/site#product", label: "Product" },
  { href: "/demo", label: "Demo" },
  { href: "/case-study", label: "Case study" },
];

export function SiteFrame({ children }: { children: ReactNode }) {
  return (
    <div className="site">
      <header className="site-header">
        <a className="site-brand" href="/site">
          <span>A</span>ATLAS
        </a>
        <nav className="site-nav" aria-label="Primary">
          {links.map((link) => (
            <a key={link.href} href={link.href}>{link.label}</a>
          ))}
          <a className="site-signin" href="/login">Sign in</a>
        </nav>
      </header>
      {children}
      <footer className="site-footer">
        <p>Harbor & Co. is fictional. The screens show stored workspace records.</p>
        <nav aria-label="Footer">
          <a href="/demo">Demo</a>
          <a href="/case-study">Case study</a>
          <a href="/login">Sign in</a>
        </nav>
      </footer>
    </div>
  );
}

export function ProductShot({
  src,
  alt,
  label,
  caption,
}: {
  src: string;
  alt: string;
  label: string;
  caption: string;
}) {
  return (
    <figure className="site-shot">
      <div className="site-frame">
        <header>
          <span>ATLAS</span>
          <span>{label}</span>
        </header>
        <img src={src} alt={alt} width={1440} height={900} />
      </div>
      <figcaption className="site-caption">{caption}</figcaption>
    </figure>
  );
}
