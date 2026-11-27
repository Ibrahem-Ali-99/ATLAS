import { NextResponse, type NextRequest } from "next/server";

/**
 * The portfolio image is built with ATLAS_PUBLIC_SITE=1, so the public
 * origin opens the presentation. A local product server leaves the flag
 * unset and keeps the workspace on `/`.
 */
export function proxy(request: NextRequest) {
  if (process.env.ATLAS_PUBLIC_SITE !== "1" || request.nextUrl.pathname !== "/") {
    return NextResponse.next();
  }
  const url = request.nextUrl.clone();
  url.pathname = "/site";
  return NextResponse.rewrite(url);
}
