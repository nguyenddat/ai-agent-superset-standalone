import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { join } from "node:path"
import { test } from "node:test"

import { bucketDisplay, cellText, keyText, MISSING, numberDisplay, periodLabel } from "./format.ts"
import type { ChartField, TimeUnit } from "./spec.ts"

type Cases = {
  number: [unknown, ChartField, string | null][]
  date: [string, TimeUnit | "datetime" | null, string, string][]
}

const FIXTURES = join(import.meta.dirname, "..", "..", "..", "..", "tests", "fixtures")
const cases: Cases = JSON.parse(readFileSync(join(FIXTURES, "format_cases.json"), "utf-8"))

for (const [value, field, expected] of cases.number) {
  test(`number ${JSON.stringify(value)} ${JSON.stringify(field)}`, () => {
    assert.equal(numberDisplay(value, field), expected)
    assert.equal(cellText(value, field, "2026-11-20"), expected ?? MISSING)
  })
}

for (const [value, unit, today, expected] of cases.date) {
  test(`date ${value} ${unit}`, () => {
    if (unit === null || unit === "datetime") {
      const field: ChartField = { name: "t", label: "T", type: unit === null ? "date" : "datetime" }
      assert.equal(cellText(value, field, today), expected)
    } else {
      assert.equal(bucketDisplay(value, unit, today), expected)
    }
  })
}

test("period labels drop the current year", () => {
  assert.equal(periodLabel("2026-11-19", "2026-11-20", "2026-11-20"), "thứ Năm, 19/11")
  assert.equal(periodLabel("2026-11-13", "2026-11-20", "2026-11-20"), "13–19/11")
  assert.equal(periodLabel("2026-10-28", "2026-11-04", "2026-11-20"), "28/10–3/11")
  assert.equal(periodLabel("2026-11-01", "2026-12-01", "2026-11-20"), "tháng 11")
  assert.equal(periodLabel("2025-12-29", "2026-01-05", "2026-11-20"), "29/12/2025–4/1/2026")
})

test("hourly axis keys keep their hours", () => {
  const field = { name: "gio", label: "Giờ", type: "datetime" } as ChartField
  assert.equal(keyText("2026-11-19T06:00:00", field, "2026-11-20"), "06:00")
  assert.equal(keyText("2026-11-19T00:00:00", field, "2026-11-20"), "19/11")
  assert.equal(keyText("2026-11-19T06:00:00", field, "2026-11-20", null, undefined, true), "06:00 thứ Năm, 19/11")
})
