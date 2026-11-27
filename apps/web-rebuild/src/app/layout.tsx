import type { Metadata } from "next";

import "../presentation/index.css";

export const metadata: Metadata = {
  title: "ATLAS",
  description: "ATLAS workspace",
  icons: { icon: "/favicon.png" },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
