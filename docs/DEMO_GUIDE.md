# ResearchForge AI — 3–5 Minute Demo

This walkthrough uses completed results saved from earlier runs with the local Ollama
`qwen3:8b` model and a synthetic Juniper battery PDF. It does **not** start inference. Say
that these are saved results when presenting them. A fresh local run can take over a minute
and may fail; do not rerun repeatedly to obtain a preferred outcome.

## Before the meeting

Start Docker Desktop and Ollama. Confirm the model is already installed and check available
space:

```bash
cd /path/to/researchforge-ai
ollama list
df -h .
```

`qwen3:8b` should already be listed. Do not download it for this demo. Then start the app:

```bash
bash scripts/start_local.sh
```

Open [http://127.0.0.1:3000](http://127.0.0.1:3000). The startup helper uses local Ollama
and disables hosted-model calls. If no Wikimedia contact is configured, Web search remains
disabled. The walkthrough uses Documents mode and makes no public search request.

## Walkthrough

### 1. Introduce the app and interface — about 30 seconds

Show the Home page, then briefly point out the document library, saved History, Settings,
and report view. Explain that ResearchForge AI turns selected source material into a saved
research report whose evidence can be inspected.

### 2. Show the saved answerable result — about 60 seconds

Open **History** and locate the completed Documents session for:

> What is the rated capacity of the Juniper battery?

Confirm the saved run is marked **LOCAL · qwen3:8b**. Open its report and show the supported
answer, **12 kWh**. This is a saved completed local run, not a newly executed model call.

### 3. Inspect the citation — about 45 seconds

Open the report’s evidence or citation view. Show the source filename
`phase7-local-demo.pdf`, page 1, and the passage that states the battery’s rated capacity.
Explain that the workflow carries document/page provenance through retrieval and checks
that the cited quote is an exact part of the retrieved passage.

### 4. Show safe abstention — about 45 seconds

Return to **History** and open the completed Documents session for:

> What is the Juniper battery annual maintenance cost?

Explain that the synthetic document contains no maintenance cost. The saved local run
returned insufficient evidence rather than inventing a price. This is also a saved result,
not a new inference.

### 5. Explain the architecture — about 60 seconds

Give the short version: Next.js provides the interface; FastAPI runs a bounded LangGraph
workflow; BM25Plus and Qdrant retrieve document evidence; Ollama runs the local model;
source-ID and exact-quote checks guard the generated report; PostgreSQL saves sessions and
results. LangGraph makes planning, evidence assessment, writing or abstention, and claim
checks visible workflow stages.

## Optional live run

Only if you choose to show fresh inference, use the same selected PDF and the answerable
question above. Confirm the run label is **LOCAL · qwen3:8b** and inspect the result. If it
fails or abstains, show the actual outcome honestly. Do not present a mock result as local
model output, and do not switch to Web or Combined for the primary demonstration.

## Screenshots

The primary evidence is [the saved local report screenshot](screenshots/phase-8a/phase-8a-existing-local-run-desktop.png).
It shows a previous completed LOCAL run and its document citations. The [home screenshot](screenshots/phase-8a/phase-8a-home-desktop.png)
shows the interface. The citation-mobile screenshot shows a separate synthetic UI example,
not the Juniper result; identify it as sample content if you use it. Other screenshots may
show synthetic demo or UI test content and should be labelled accordingly.

## Web and Combined status

Web and Documents + Web are experimental. Their current deterministic offline regression
tests passed using clearly labeled synthetic evidence and fixture inference. Earlier
historical acceptance used saved Wikipedia evidence. One bounded real-Qwen Web run failed at
evidence sufficiency after a local Ollama HTTP 500; its cause is unknown. Combined real-Qwen
acceptance is unverified. A previous real Wikipedia retrieval was not a completed Web
report. Do not describe either mode as fully validated.

## Stop the application

```bash
bash scripts/stop_local.sh
```

The helper stops only the API and interface processes it started. PostgreSQL, Qdrant, and
the Ollama service remain running.
