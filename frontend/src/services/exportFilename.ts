export function resultsFilename(title: string): string {
  const cleaned = title.normalize("NFKC").replace(/[\p{C}<>:"/\\|?*]+/gu, " ").replace(/\s+/g, " ").replace(/^[ .]+|[ .]+$/g, "");
  const base = Array.from(cleaned).slice(0, 100).join("").replace(/[ .]+$/g, "") || "assessment";
  return `${base}-results.csv`;
}
