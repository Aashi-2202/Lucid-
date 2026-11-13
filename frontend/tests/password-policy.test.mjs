import test from "node:test";
import assert from "node:assert/strict";
import { validNewPassword } from "../src/services/passwordPolicy.ts";

test("new passwords need eight characters and a special character",()=>{
  assert.equal(validNewPassword("short!"),false);
  assert.equal(validNewPassword("password"),false);
  assert.equal(validNewPassword("password!"),true);
  assert.equal(validNewPassword("       !"),true);
  for(const punctuation of `!"#$%&'()*+,-./:;<=>?@[\\]^_\x60{|}~`) assert.equal(validNewPassword("abcdefg"+punctuation),true);
  assert.equal(validNewPassword("a".repeat(128)+"!"),false);
  assert.equal(validNewPassword("é".repeat(7)+"!"),true);
});
