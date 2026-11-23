export type UploadOrigin = "operational" | "demo";

export function documentUploadForm(file: File, origin: UploadOrigin = "operational"): FormData {
  const body = new FormData();
  body.append("file", file);
  body.append("origin", origin);
  return body;
}
