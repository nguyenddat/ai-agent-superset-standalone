import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { join } from "node:path"
import { test } from "node:test"

import { buildChartData } from "./data.ts"
import type { ChartField, ChartSpec } from "./spec.ts"

type Case = {
  name: string
  fields: ChartField[]
  rows: unknown[][]
  spec: ChartSpec
  expect: { valid: boolean; errors: string[]; stats?: Record<string, number> }
}

const FIXTURES = join(import.meta.dirname, "..", "..", "..", "..", "tests", "fixtures")
const cases: Case[] = JSON.parse(readFileSync(join(FIXTURES, "chart_cases.json"), "utf-8"))

test("chart_cases.json has the shared cases", () => {
  assert.ok(cases.length >= 40)
})

for (const item of cases.filter((entry) => entry.expect.valid && entry.expect.stats)) {
  test(`stats: ${item.name}`, () => {
    assert.deepEqual(buildChartData(item.spec, item.fields, item.rows).stats, item.expect.stats)
  })
}
