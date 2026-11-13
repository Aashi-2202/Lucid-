export const COMMON_COMPETENCIES = [
  "Communication", "Leadership and Influence",
  "Problem-Solving and Critical Thinking", "Learning Agility",
];

export function competencyInputs(values: string[]): string[] {
  const result: string[] = [];
  for (const raw of values) {
    const name = raw.trim().replace(/\s+/g, " ");
    if (!name) continue;
    if (name.length > 100) throw new Error("Keep each additional competency within 100 characters.");
    if (/^(dsa|data structures?(?:\s*(?:and|&)\s*|\s+)algorithms?)$/i.test(name)) {
      throw new Error("Add DSA under Skills & Requirements so it can be scored.");
    }
    if (!result.some(item => item.toLocaleLowerCase() === name.toLocaleLowerCase())) result.push(name);
  }
  if (result.length > 20) throw new Error("Add up to 20 additional competencies.");
  return result;
}
