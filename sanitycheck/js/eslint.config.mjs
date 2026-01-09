import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import tsParser from "@typescript-eslint/parser";
import sanitycheck from "./rules/index.js";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const configPath = path.join(__dirname, "..", "sanitycheck.config.json");
const configText = fs.readFileSync(configPath, "utf8");
const config = JSON.parse(configText);

const jsConfig = config.js;
if (jsConfig === null || typeof jsConfig !== "object") {
  throw new Error("config.js must be an object");
}

const allowedTryCalleeNames = jsConfig.allowed_try_callee_names;
const allowedTryCalleePrefixes = jsConfig.allowed_try_callee_prefixes;
if (!Array.isArray(allowedTryCalleeNames)) {
  throw new Error("config.js.allowed_try_callee_names must be an array");
}
if (!Array.isArray(allowedTryCalleePrefixes)) {
  throw new Error("config.js.allowed_try_callee_prefixes must be an array");
}

export default [
  {
    files: ["**/*.{js,jsx,ts,tsx}"],
    languageOptions: {
      parser: tsParser,
      parserOptions: {
        ecmaVersion: "latest",
        sourceType: "module"
      }
    },
    plugins: {
      sanitycheck
    },
    rules: {
      "sanitycheck/JS001": [
        "error",
        {
          allowedTryCalleeNames,
          allowedTryCalleePrefixes
        }
      ],
      "sanitycheck/JS002": "error",
      "sanitycheck/JS003": "error",
      "sanitycheck/JS004": "error"
    }
  }
];

