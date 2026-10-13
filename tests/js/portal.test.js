// Optional tests for the pure helpers in portal.js.
// Run from the project root (Node 18 or newer):  node --test tests/js/portal.test.js
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const portal = require(path.join(__dirname, "..", "..", "src", "wbms", "web", "static", "portal.js"));

test("accepted phone formats all normalise to +254 form", () => {
  const accepted = [
    "0712345678",
    "0712 345 678",
    "0712-345-678",
    "0112345678",
    "254712345678",
    "+254712345678",
    "+254 712 345 678",
    "712345678",
  ];
  for (const raw of accepted) {
    const result = portal.normalizePhone(raw);
    assert.equal(result.ok, true, raw);
    assert.match(result.value, /^\+254[17]\d{8}$/, raw);
  }
  assert.equal(portal.normalizePhone("0712345678").value, "+254712345678");
  assert.equal(portal.normalizePhone("0112345678").value, "+254112345678");
});

test("rejected phone input gives a message", () => {
  const rejected = [
    "",
    "   ",
    null,
    undefined,
    "071234567",
    "07123456789",
    "0212345678",
    "+255712345678",
    "abcdefghij",
    "0712 345 67x",
    "<script>",
  ];
  for (const raw of rejected) {
    const result = portal.normalizePhone(raw);
    assert.equal(result.ok, false, String(raw));
    assert.ok(result.message.length > 0, String(raw));
  }
});

test("durations read naturally", () => {
  assert.equal(portal.formatDuration(1), "1 minute");
  assert.equal(portal.formatDuration(30), "30 minutes");
  assert.equal(portal.formatDuration(60), "1 hour");
  assert.equal(portal.formatDuration(180), "3 hours");
  assert.equal(portal.formatDuration(90), "1 h 30 min");
  assert.equal(portal.formatDuration(1440), "1 day");
  assert.equal(portal.formatDuration(43200), "30 days");
  assert.equal(portal.formatDuration(0), "");
  assert.equal(portal.formatDuration("x"), "");
});

test("speed, data and price formats", () => {
  assert.equal(portal.formatSpeed(512), "512 kbps");
  assert.equal(portal.formatSpeed(2000), "2 Mbps");
  assert.equal(portal.formatSpeed(1500), "1.5 Mbps");
  assert.equal(portal.formatData(null), "Unlimited data");
  assert.equal(portal.formatData(500), "500 MB data");
  assert.equal(portal.formatData(2048), "2 GB data");
  assert.equal(portal.formatPrice(20), "KES 20");
  assert.equal(portal.formatPrice(0), "Free");
});

test("failure messages", () => {
  const validation = portal.describeFailure(400, {
    error: { code: "validation_error", fields: { phone: "Not a valid number.", package_id: "Unknown package." } },
  });
  assert.equal(validation.fields.phone, "Not a valid number.");
  assert.equal(validation.fields.package_id, "Unknown package.");

  const mac = portal.describeFailure(400, { error: { fields: { mac: "Device address missing." } } });
  assert.equal(mac.message, "Device address missing.");

  assert.match(portal.describeFailure(429, null).message, /Too many attempts/);
  assert.match(portal.describeFailure(404, null).message, /not available/);
  assert.match(portal.describeFailure(502, null).message, /not responding/);
  assert.match(portal.describeFailure(418, null).message, /Something went wrong/);
  // Garbage bodies never throw.
  assert.deepEqual(portal.describeFailure(400, "oops").fields, {});
});
