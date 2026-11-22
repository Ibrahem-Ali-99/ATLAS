export function isStaleChunkError(error: Error): boolean {
  const message = error.message.toLowerCase();
  return message.includes("failed to load chunk") || message.includes("loading chunk");
}
