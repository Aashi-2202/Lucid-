import test from "node:test";
import assert from "node:assert/strict";
import { newSkillDraft, skillInputs } from "../src/services/skillDrafts.ts";

test("saving preserves seven settings and parses approved aliases only at submission", () => {
  const draft = {...newSkillDraft(), skill:" Python ", description:" Build APIs ", mandatory:true,
    importance:5, required_evidence_level:4, assessment_method:"resume", aliasesText:"Python3, Python 3,\npython3\n CPython "};
  assert.equal(draft.aliasesText.endsWith("CPython "), true);
  assert.deepEqual(skillInputs([draft]), [{skill:"Python", description:"Build APIs", mandatory:true,
    importance:5, required_evidence_level:4, assessment_method:"resume", aliases:["Python3", "Python 3", "CPython"]}]);
});
test("interview method roundtrips without silently resetting stored values or mandatory", () => {
  const original={skill:"Communication", description:null, mandatory:true, importance:4,
    required_evidence_level:3, assessment_method:"interview", aliases:[]};
  assert.deepEqual(skillInputs([newSkillDraft(original)]), [original]);
});
test("blank named requirements are rejected rather than silently discarded", () => {
  assert.throws(() => skillInputs([newSkillDraft()]), /requirement 1/);
  assert.deepEqual(skillInputs([]), []);
  assert.notEqual(newSkillDraft().key, newSkillDraft().key);
});
