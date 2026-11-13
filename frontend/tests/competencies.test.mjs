import test from "node:test";
import assert from "node:assert/strict";
import { competencyInputs } from "../src/services/competencies.ts";

test("optional reporting competencies normalize without introducing scoring controls",()=>{
  assert.deepEqual(competencyInputs([" Communication ","communication","", "Learning   Agility"]),["Communication","Learning Agility"]);
  assert.deepEqual(competencyInputs([]),[]);
});

test("DSA stays technical and reporting configuration is bounded",()=>{
  for(const name of ["DSA","Data Structures and Algorithms"]) assert.throws(()=>competencyInputs([name]),/Skills & Requirements/);
  assert.throws(()=>competencyInputs(["x".repeat(101)]),/100 characters/);
  assert.throws(()=>competencyInputs(Array.from({length:21},(_,i)=>`Competency ${i}`)),/up to 20/);
});
