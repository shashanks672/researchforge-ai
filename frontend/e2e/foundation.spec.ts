import { expect, test } from "@playwright/test";

test("new research clearly describes available sources and connects to the backend", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText(
    "Good questions deserve grounded answers",
  );
  await expect(
    page
      .getByRole("navigation", { name: "Primary navigation" })
      .getByRole("link", { name: "New research" }),
  ).toBeVisible();
  await expect(
    page.getByText(/Demo mode uses deterministic sample research/),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Start research" }),
  ).toBeDisabled();
  const response = await page.request.get("/api/system");
  expect(response.status()).toBe(200);
  expect(await response.json()).toMatchObject({
    service: "researchforge-api",
    research_enabled: true,
    uploads_enabled: true,
    sessions_enabled: true,
    execution_mode: "mock",
  });
  await page.setViewportSize({ width: 1440, height: 960 });
  await page.screenshot({
    path: "test-results/phase-8a-home-desktop.png",
    fullPage: true,
  });
  await page.goto("/settings");
  await expect(
    page.getByRole("heading", { name: "Settings", exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/phase-8a-settings-desktop.png",
    fullPage: true,
  });
});

test("one-click research persists a mock report and opens its real saved citation passage", async ({
  page,
}) => {
  await page.goto("/");
  await page
    .getByLabel("What would you like to research?")
    .fill("Demonstrate a bounded source-grounded research workflow.");
  await page.getByRole("button", { name: "Web", exact: true }).click();
  await page.getByRole("button", { name: "Start research" }).click();
  await page.waitForURL(/\/research\/[0-9a-f-]+$/);
  await expect(
    page.getByRole("heading", {
      level: 2,
      name: "Research findings",
      exact: true,
    }),
  ).toBeVisible({ timeout: 30000 });
  await expect(page.locator(".report-meta .run-mode-label")).toHaveText(
    "DEMO · synthetic results",
  );
  await expect(page.locator(".report-body")).toContainText(
    "MOCK DEMONSTRATION",
  );
  const citation = page
    .locator(".report-body")
    .getByRole("button", { name: "Open S1 source" })
    .first();
  await expect(citation).toBeVisible();
  await citation.click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByText("Evidence source · S1")).toBeVisible();
  await expect(dialog.getByRole("blockquote")).toContainText("fixture");
  await dialog.getByRole("button", { name: "Close source details" }).click();
  const path = new URL(page.url()).pathname;
  const id = path.split("/").at(-1);
  const report = await page.request.get(`/api/sessions/${id}/report`);
  expect(report.status()).toBe(200);
  expect(await report.text()).toContain("MOCK DEMONSTRATION");
  await page.setViewportSize({ width: 1440, height: 960 });
  await page.screenshot({
    path: "test-results/phase-8a-result-desktop.png",
  });
  await page
    .getByRole("region", { name: "Evidence review" })
    .scrollIntoViewIfNeeded();
  await page.screenshot({
    path: "test-results/phase-8a-evidence-review-desktop.png",
  });
});

test("library upload can be selected explicitly and used in document-only research", async ({
  page,
}) => {
  await page.goto("/library");
  const uploaded = page.waitForResponse((response) =>
    response.url().endsWith("/api/documents/upload"),
  );
  await page.getByLabel("Choose a document to upload").setInputFiles({
    name: "juniper-handbook.txt",
    mimeType: "text/plain",
    buffer: Buffer.from(
      "Juniper pilot handbook. The Juniper battery stores 20 kWh of energy. The pilot operates in Bristol and requires inspection every 30 days.",
    ),
  });
  expect((await uploaded).status()).toBe(202);
  const use = page.getByRole("link", { name: "Use in research" });
  await expect(use).toBeVisible({ timeout: 20000 });
  await page.setViewportSize({ width: 1440, height: 960 });
  await page.screenshot({
    path: "test-results/phase-8a-library-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: "test-results/phase-8a-library-mobile.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 1440, height: 960 });
  await use.click();
  await expect(page.getByLabel("Selected documents")).toContainText(
    "juniper-handbook.txt",
  );
  await page.getByRole("button", { name: "My documents" }).click();
  await page
    .getByLabel("What would you like to research?")
    .fill("What is the Juniper battery storage capacity?");
  await page.getByRole("button", { name: "Start research" }).click();
  await page.waitForURL(/\/research\/[0-9a-f-]+$/);
  await expect(
    page.getByRole("heading", {
      level: 2,
      name: "Research findings",
      exact: true,
    }),
  ).toBeVisible({ timeout: 30000 });
  await expect(page.locator(".report-body")).toContainText("20 kWh");
  await expect(page.locator(".source-row").first()).toContainText(
    "juniper-handbook.txt",
  );
  await page.locator(".source-row").first().click();
  await expect(page.getByRole("dialog").getByRole("blockquote")).toContainText(
    "20 kWh",
  );
  await expect(page.getByRole("dialog")).toContainText("Your document");
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({ path: "test-results/phase-8a-citation-mobile.png" });
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Close source details" })
    .click();
  await page.screenshot({ path: "test-results/phase-8a-result-mobile.png" });
});

test("history opens persisted research and supports filtering", async ({
  page,
}) => {
  const question =
    "History route keeps this unique saved question discoverable.";
  await page.goto("/");
  await page.getByLabel("What would you like to research?").fill(question);
  await page.getByRole("button", { name: "Web", exact: true }).click();
  await page.getByRole("button", { name: "Start research" }).click();
  await page.waitForURL(/\/research\/[0-9a-f-]+$/);
  await expect(
    page.getByRole("heading", {
      level: 2,
      name: "Research findings",
      exact: true,
    }),
  ).toBeVisible({ timeout: 30000 });
  await page
    .getByRole("navigation", { name: "Primary navigation" })
    .getByRole("link", { name: "History" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Research history" }),
  ).toBeVisible();
  const search = page.getByRole("searchbox", {
    name: "Search this page of research history",
  });
  await search.fill("unique saved question");
  const row = page.getByRole("link", { name: new RegExp(question) });
  await expect(row).toBeVisible();
  await page.setViewportSize({ width: 1440, height: 960 });
  await page.screenshot({
    path: "test-results/phase-8a-history-desktop.png",
    fullPage: true,
  });
  await row.click();
  await expect(page.getByRole("heading", { name: question })).toBeVisible();
});

test("mobile navigation and workspace stay usable from 360px through desktop widths", async ({
  page,
}) => {
  for (const width of [360, 390, 768, 1024, 1280, 1440]) {
    await page.setViewportSize({ width, height: 860 });
    await page.goto("/");
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
      `horizontal overflow at ${width}px`,
    ).toBe(true);
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  const toggle = page.getByRole("button", { name: "Open navigation" });
  await toggle.click();
  await expect(
    page.getByRole("button", { name: "Close navigation" }).first(),
  ).toHaveAttribute("aria-expanded", "true");
  await expect(
    page.locator(".mobile-drawer").getByRole("link", { name: "Library" }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(
    page.getByRole("button", { name: "Open navigation" }),
  ).toHaveAttribute("aria-expanded", "false");
  await page.screenshot({
    path: "test-results/phase-8a-home-mobile.png",
    fullPage: true,
  });
});
