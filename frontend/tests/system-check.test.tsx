import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { SystemCheck } from "../src/components/system-check";

afterEach(() => vi.unstubAllGlobals());

test("reports a real successful health response", async () => {
  const fetchMock = vi
    .fn()
    .mockResolvedValue(
      new Response(
        JSON.stringify({ status: "ok", service: "researchforge-api" }),
      ),
    );
  vi.stubGlobal("fetch", fetchMock);
  render(<SystemCheck />);
  expect(await screen.findByText("Backend connected")).toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledWith(
    "/api/system",
    expect.objectContaining({ cache: "no-store" }),
  );
});

test("backend failure is visible and retry recovers", async () => {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValueOnce(new Response("unavailable", { status: 503 }))
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ status: "ok", service: "researchforge-api" }),
        ),
      ),
  );
  render(<SystemCheck />);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Start the backend",
  );
  fireEvent.click(screen.getByRole("button", { name: /Check connection/ }));
  expect(await screen.findByText("Backend connected")).toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test("malformed health response is not presented as success", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: "ok" }))),
  );
  render(<SystemCheck />);
  expect(await screen.findByText("Backend offline")).toBeInTheDocument();
});
