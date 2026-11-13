import test from "node:test";
import assert from "node:assert/strict";
import { resultsFilename } from "../src/services/exportFilename.ts";

test("download names retain the job title with portable characters",()=>{
  for(const [title,expected] of [
    ["AI Engineer","AI Engineer-results.csv"],
    ['  AI / Engineer: "Europe"?  ',"AI Engineer Europe-results.csv"],
    ["Développeur 日本語","Développeur 日本語-results.csv"],
    ["../CON\\..\r\nInjected: value","CON .. Injected value-results.csv"],
    ["... /:*? ","assessment-results.csv"],
  ]) assert.equal(resultsFilename(title),expected);
  assert.equal(resultsFilename("😀".repeat(120)),"😀".repeat(100)+"-results.csv");
});
