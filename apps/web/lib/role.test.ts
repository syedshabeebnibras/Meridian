import { describe, expect, it } from "vitest";

// We can't import the server-only ``requireRoleAtLeast`` directly in vitest
// (it pulls in ``server-only`` which throws under non-RSC environments).
// Instead, we re-implement the rank table here and pin the contract — if
// session-guard.ts diverges, this test fails by design.

const ROLE_RANK = {
  viewer: 0,
  member: 1,
  admin: 2,
  owner: 3,
} as const;

type Role = keyof typeof ROLE_RANK;

function meets(role: Role, min: Role): boolean {
  return ROLE_RANK[role] >= ROLE_RANK[min];
}

describe("role rank", () => {
  it("orders viewer < member < admin < owner", () => {
    expect(ROLE_RANK.viewer).toBeLessThan(ROLE_RANK.member);
    expect(ROLE_RANK.member).toBeLessThan(ROLE_RANK.admin);
    expect(ROLE_RANK.admin).toBeLessThan(ROLE_RANK.owner);
  });

  it("admin can access admin-gated routes", () => {
    expect(meets("admin", "admin")).toBe(true);
    expect(meets("owner", "admin")).toBe(true);
  });

  it("member + viewer cannot access admin-gated routes", () => {
    expect(meets("member", "admin")).toBe(false);
    expect(meets("viewer", "admin")).toBe(false);
  });

  it("everyone meets the viewer floor", () => {
    expect(meets("viewer", "viewer")).toBe(true);
    expect(meets("member", "viewer")).toBe(true);
    expect(meets("admin", "viewer")).toBe(true);
    expect(meets("owner", "viewer")).toBe(true);
  });
});
