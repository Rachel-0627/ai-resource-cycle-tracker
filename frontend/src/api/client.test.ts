import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "./client";

describe("api client", () => {
  afterEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("prefixes requests with /api and parses JSON responses", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(api.get<{ ok: boolean }>("/config")).resolves.toEqual({ ok: true });

    expect(fetchMock).toHaveBeenCalledWith("/api/config", {
      headers: { "Content-Type": "application/json" },
    });
  });

  it("serializes POST bodies", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ id: 1 }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await api.post("/stocks", { code: "DYL" });

    expect(fetchMock).toHaveBeenCalledWith("/api/stocks", {
      headers: { "Content-Type": "application/json" },
      method: "POST",
      body: JSON.stringify({ code: "DYL" }),
    });
  });

  it("sends the local admin token when configured", async () => {
    localStorage.setItem("adminApiToken", "secret-token");
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await api.get("/admin/runs");

    expect(fetchMock).toHaveBeenCalledWith("/api/admin/runs", {
      headers: {
        "Content-Type": "application/json",
        "X-Admin-Token": "secret-token",
      },
    });
  });

  it("uses backend detail messages for errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "bad config" }), {
          status: 400,
          statusText: "Bad Request",
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    await expect(api.put("/config", {})).rejects.toThrow("bad config");
  });
});
