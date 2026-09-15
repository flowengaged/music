# YuE2 Professional Studio — Frontend + RunPod Implementation Specification

> **Target repository:** `flowengaged/music`  
> **Model:** `m-a-p/YuE2-3B`  
> **Deployment:** RunPod Serverless  
> **Goal:** build a professional music-creation studio exposing the real YuE2 capabilities without inventing unsupported features.

---

## 1. Non-negotiable rules

- Keep YuE2 as the generation model. Do not replace or silently simplify it.
- Never expose `RUNPOD_API_KEY` in the browser.
- Do not return `/tmp/...` paths as final assets. Serverless workers are ephemeral; upload artifacts to persistent object storage.
- All GPU jobs must be asynchronous and persisted in the application database.
- Every completed generation is immutable; edits create child versions.
- Keep all reproducibility data: prompt, lyrics, seed, score, config, model/VAE identity, timings and truncation flags.
- Do not advertise unsupported YuE2 features such as voice cloning, speaker identity lock, local waveform inpainting, phoneme alignment or direct audio-reference conditioning.
- Current YuE2 model weights are CC BY-NC 4.0. Do not launch a paid/commercial YuE2-based service until licensing is resolved.

---

## 2. Product vision

This must be a serious browser-based music-creation workspace, not a single prompt form.

Core UX:

```text
Lyrics + Style
      ↓
YuE2 symbolic composition
      ↓
Editable ABC score
      ↓
Semantic music generation
      ↓
Acoustic synthesis
      ↓
VAE decode
      ↓
48 kHz stereo audio
```

The user must be able to:

```text
create → plan → listen → inspect → edit → regenerate → compare → download → branch versions
```

Cover workflow:

```text
source audio → SheetSage2 → ABC → review/edit → YuE2 → new rendition
```

---

## 3. Visual/UI direction

Professional dark creative-studio interface.

```css
--background: #0B0B0C;
--surface-1: #111214;
--surface-2: #17181B;
--surface-3: #1E2024;
--text-primary: #F5F3EE;
--text-secondary: #A9A9A6;
--text-muted: #747474;
--accent: #D99A32;
--accent-light: #FFC35C;
--accent-soft: rgba(217,154,50,.12);
--border: rgba(255,255,255,.08);
```

Typography: **Geist**, **Inter** or **Manrope**.

Principles:

- compact professional controls;
- resizable/collapsible panels;
- subtle borders and elevation;
- restrained amber/gold accent;
- no neon/gaming look;
- no giant marketing cards inside the studio;
- desktop-first workflow.

---

## 4. Recommended frontend stack

```text
Next.js App Router
TypeScript
React
Tailwind CSS
shadcn/ui
Radix UI
TanStack Query
Zustand
React Hook Form
Zod
Framer Motion
Lucide
WaveSurfer.js
Monaco Editor
React Dropzone
Sonner
cmdk
```

Audio: Web Audio API + WaveSurfer.js.

Persistence:

```text
PostgreSQL
Prisma or Drizzle
Cloudflare R2 / AWS S3 / S3-compatible object storage
```

---

## 5. Architecture

The browser must never call RunPod with a private API key.

```text
Browser
   ↓
Next.js UI
   ↓
Application API
   ↓
Postgres job/project state
   ↓
RunPod Queue API
   ↓
YuE2 Serverless worker
   ↓
S3/R2 persistent artifacts
   ↓
Application API
   ↓
Browser
```

Server-only environment variables:

```env
RUNPOD_API_KEY=
RUNPOD_ENDPOINT_ID=
DATABASE_URL=
S3_ENDPOINT=
S3_ACCESS_KEY_ID=
S3_SECRET_ACCESS_KEY=
S3_BUCKET=
S3_REGION=
```

Never use `NEXT_PUBLIC_RUNPOD_API_KEY`.

---

## 6. Critical production change to the current worker

The current worker returns paths such as:

```text
/tmp/<generation-id>/audio.flac
```

This is not production-safe because Serverless workers may terminate after the request.

Required flow:

```text
YuE2
  ↓
/tmp/<generation-id>/
  ↓
upload all artifacts to S3/R2
  ↓
return object keys / signed references
```

Suggested object layout:

```text
projects/{project_id}/generations/{generation_id}/
  audio.flac
  score.abc
  plan.json
  plan_manifest.json
  request.json
  config.json
  result.json
  semantic.npy
  latent.npy
  abc_tokens.npy
  prefix.npy
```

Use private buckets and signed download URLs.

---

## 7. YuE2 modes that must exist in the UI

### Full Composition

```text
cot = "full"
```

Generates an editable melody + chord plan before rendering.

This is the default mode for new songs.

### Melody Guided

```text
cot = "melody"
```

Generates/uses a melody plan with freer accompaniment. Recommended for covers and melody-preservation workflows.

### Direct

```text
cot = "off"
```

Generates without a symbolic score. UI must clearly show that an editable score is unavailable.

### External ABC

Supported only with:

```text
cot = "full" | "melody"
```

UI must allow paste/upload/edit/validate/render of `.abc` content. Never allow ABC with `cot="off"`.

---

## 8. Real SongRequest fields

```ts
type SongRequest = {
  id: string;
  style: string;
  lyrics: string;
  cot: "full" | "melody" | "off";
  seed: number;
  abc?: string | null;
  cfg_scale?: number | null;
}
```

Validation:

```text
seed: integer, 0 <= seed < 2^63
cfg_scale: null or 0–20
abc: non-empty and only with full/melody
```

---

## 9. Style editor

Provide structured helpers plus an always-editable raw prompt.

Helpers:

```text
Language
Genre
Subgenre
Mood
Tempo/BPM
Vocal type
Vocal character
Instrumentation
Rhythm/groove
Production style
Era/sonic character
Additional direction
```

Example final style:

```text
Portuguese, deep Afro House, 120 BPM, intimate female vocal,
warm round kick, organic frame drums and congas, hypnotic sub bass,
cinematic strings, Portuguese guitar harmonics, expressive flute
```

Actions: Save preset, Copy prompt, Reset.

---

## 10. Lyrics editor

Professional multiline editor with autosave, undo/redo, section navigation, character count and quick section insertion.

Useful songwriting helpers:

```text
[Intro]
[Verse]
[Pre-Chorus]
[Chorus]
[Post-Chorus]
[Hook]
[Bridge]
[Breakdown]
[Outro]
```

These are UI songwriting helpers; do not claim YuE2 requires every label.

---

## 11. Seed + CFG

Seed UI:

```text
Seed [831001] [Randomize] [Lock]
```

Allow copy/reuse from any version.

Expose `cfg_scale` under Advanced:

```text
Default
Custom 0–20
```

Preserve effective values in generation metadata.

---

## 12. Advanced ABC sampling

YuE2 default symbolic-planning sampling:

```text
temperature = 0.7
top_p = 0.9
top_k = 30
repetition_penalty = 1.005
penalty_window = 100
min_tokens = 32
max_tokens = 4096
```

UI path: **Advanced → Composition Sampling**.

Expose all seven fields and a **Reset to YuE2 defaults** action.

---

## 13. Advanced semantic sampling

YuE2 default semantic sampling:

```text
temperature = 1.0
top_p = 0.95
top_k = 100
repetition_penalty = 1.2
penalty_window = 50
min_tokens = 200
max_tokens = 9000
```

UI path: **Advanced → Semantic/Audio Sampling**.

Validation:

```text
temperature: 0–5
top_p: >0 and <=1
top_k: >=1
repetition_penalty: >0
penalty_window: 1–100
min_tokens: >=0
max_tokens: >= min_tokens
```

---

## 14. Runtime/admin controls

YuE2 also exposes runtime options:

```text
ode_steps = 32
ode_method = midpoint
context = 24576
backend = torch | torch-eager | vllm
quantization = none | fp8
memory_budget_gib
vae_core_frames
offload_ar
```

These are infrastructure controls, not normal creative controls. Hide them from ordinary users; optionally expose them in an admin-only Runtime page.

---

## 15. Main workspace

```text
┌──────────────────────────────────────────────────────────────┐
│ Project / Version / Model / Queue / Account                 │
├──────────────┬─────────────────────────────┬─────────────────┤
│ Left         │ Main                        │ Right           │
│ Mode         │ Lyrics / Score / Audio      │ Generate        │
│ Style        │                             │ Advanced        │
│ Structure    │                             │ Metadata        │
│ Presets      │                             │                 │
├──────────────┴─────────────────────────────┴─────────────────┤
│ Persistent audio player + version strip                     │
└──────────────────────────────────────────────────────────────┘
```

Navigation:

```text
Create
Projects
Covers
Score Lab
Compare
Library
Jobs
Settings
```

Admin: Runtime, Model, Storage, RunPod.

---

## 16. Create actions

Tabs:

```text
Lyrics
Score
Audio
Artifacts
```

Generate menu:

```text
Generate 1
Generate 2
Generate 4
Generate 8
Generate Composition Only
```

One YuE2 pipeline call generates one candidate. Multiple candidates are application-level orchestration. If RunPod Max Workers is 1, queue sequentially.

---

## 17. Worker action router

Evolve `handler.py` into an action router.

Required actions:

```text
generate
plan
render_from_abc
decode_latents
health
model_info
```

Example request:

```json
{
  "input": {
    "action": "generate",
    "project_id": "uuid",
    "generation_id": "uuid",
    "request": {
      "id": "song-name",
      "style": "...",
      "lyrics": "...",
      "cot": "full",
      "seed": 831001,
      "abc": null,
      "cfg_scale": null
    },
    "abc_sampling": null,
    "semantic_sampling": null,
    "decoder": "default"
  }
}
```

---

## 18. `generate`

Run:

```text
plan → generate_semantic → synthesize → decode → save_artifacts → upload
```

Return structured metadata, not local paths:

```json
{
  "status": "completed",
  "generation_id": "...",
  "audio": {"sample_rate": 48000, "format": "flac", "object_key": "..."},
  "score": {"available": true, "object_key": "..."},
  "truncated": {"abc": false, "semantic": false},
  "timing": {},
  "request_identity": "...",
  "artifacts": {}
}
```

---

## 19. `plan` — composition-only workflow

Use:

```python
plan = pipe.plan(...)
```

Store:

```text
score.abc
plan.json
plan_manifest.json
abc_tokens.npy
prefix.npy
```

Do not generate audio yet.

UI result:

```text
Composition ready
[Edit score] [Render song] [Download ABC]
```

This enables `prompt → composition → edit → render`.

---

## 20. Score Lab

Use Monaco Editor for ABC.

Required functions:

```text
Open generated score
Paste ABC
Upload .abc
Validate
Save as child version
Reset
Compare
Render
Download
```

Never modify completed originals in place.

Supported workflows:

```text
Reharmonize
Change melody
Change tempo
Change form
Duplicate/remove/reorder sections
Preserve melody + change harmony
Preserve melody + change style
Change lyrics around existing score
```

These are symbolic edits followed by full regeneration, not local waveform edits.

---

## 21. Preserve staged YuE2 pipeline support

The backend architecture must retain support for:

```python
pipe.plan()
pipe.generate_semantic()
pipe.synthesize()
pipe.decode()
```

A future Lab mode may expose Plan only, Generate semantic, Synthesize and Decode cached latent independently.

---

## 22. Decoder controls

Default listening decoder:

```text
m-a-p/YuE2-Vae
```

Benchmark decoder:

```text
m-a-p/YuE2-Vae-legacy
```

Advanced UI:

```text
Decoder
● Standard
○ Benchmark Legacy
```

Do not label legacy as lower quality. Support decoding the same cached latents with another decoder without regenerating the musical content.

---

## 23. Audio + artifact player

Native audio: **48 kHz stereo**.

Master: **FLAC**. Optional WAV/MP3 delivery conversions.

Player:

```text
Play/Pause
Seek
Waveform
Time / duration
Volume
Loop
Zoom
Previous/next version
A/B
```

Artifact browser:

```text
audio.flac
score.abc
plan.json
plan_manifest.json
request.json
config.json
result.json
semantic.npy
latent.npy
abc_tokens.npy
prefix.npy
```

Allow download/inspect for text/JSON; do not auto-load large NPY files in the browser.

---

## 24. Version system

Every generation is a version:

```text
Project
├── V1 Initial
├── V2 Same seed / new style
├── V3 Reharmonized
├── V4 New lyrics
└── V5 Cover
```

Store at minimum:

```text
id
project_id
parent_generation_id
status
action
style
lyrics
cot
seed
cfg_scale
abc
abc_sampling
semantic_sampling
decoder
model
model_revision
vae
vae_revision
runpod_job_id
request_identity
audio_object_key
score_object_key
result_json
timing_json
truncated_json
created_at
completed_at
```

Derived versions must record parent, edit description, changed fields and preserved fields.

---

## 25. Compare

Allow 2–4 versions and show:

```text
waveform
style
lyrics
seed
mode
ABC
duration
generation time
model revision
decoder
truncation
```

Provide A/B switching and synchronized approximate seek when practical.

---

## 26. AI score-editing assistant

Optional panel for requests such as:

```text
Keep the vocal melody exactly the same but make the harmony more jazz influenced.
```

Send the editing agent:

```text
ABC
style
lyrics
requested edit
invariants
```

Return edited ABC + edit summary + invariant report, then render with YuE2.

This editing LLM is separate from YuE2.

Invariants UI:

```text
Preserve melody exactly
Preserve pitch + rhythm
Preserve tempo
Preserve structure
Preserve lyrics
Allow harmony change
Allow arrangement change
```

---

## 27. Covers

Official architecture:

```text
source recording → SheetSage2 → ABC → review/edit → YuE2
```

SheetSage2 and YuE2 use different dependency versions. Prefer two services:

```text
Endpoint A: YuE2
Endpoint B: SheetSage2
```

Cover UI:

```text
1. Upload audio
2. Transcribe
3. Review/edit score
4. Select target style
5. Add/adapt lyrics
6. Render
```

For freer arrangement, use chord-free ABC + `cot="melody"`. For retaining melody and harmony, use a full score + `cot="full"`.

Do not claim this clones the source singer or preserves source waveform identity.

---

## 28. Job orchestration

Use RunPod Queue asynchronously:

```text
POST /run
→ store external job id
→ poll status server-side
→ COMPLETE
→ persist result
→ notify UI
```

Frontend states:

```text
Draft
Queued
Starting
Running
Saving
Completed
Failed
Cancelled
```

Only show model stages such as Planning/Decoding when the worker really reports them. Never fake percentages.

Use SSE/WebSocket for realtime updates; TanStack Query polling is acceptable for v1.

---

## 29. Internal API

Recommended routes:

```text
POST   /api/projects
GET    /api/projects
GET    /api/projects/:id
POST   /api/projects/:id/generations
GET    /api/generations/:id
POST   /api/generations/:id/duplicate
POST   /api/generations/:id/render
POST   /api/generations/:id/retry
GET    /api/generations/:id/artifacts
GET    /api/artifacts/:id/download
POST   /api/covers/transcribe
GET    /api/jobs/:id
POST   /api/jobs/:id/cancel
```

Database entities:

```text
User
Project
Generation
Artifact
Job
Preset
Comparison
```

---

## 30. Worker lifecycle and RunPod sizing

Load YuE2 once at worker startup, outside the handler:

```python
pipe = YuE2Pipeline.from_pretrained(...)
```

Do not reload per job.

Use `/tmp/{generation_id}` per request, upload results, then optionally clean temporary files.

Cache:

```text
m-a-p/YuE2-3B
m-a-p/YuE2-Vae
```

Supported starting point:

```text
NVIDIA
BF16
24 GB VRAM
one request at a time per worker
```

Initial private-use config:

```text
Active workers: 0
Max workers: 1
GPU count: 1
```

Increase concurrency only after cost/stability tests.

---

## 31. Health/model information

Add:

```json
{"input":{"action":"health"}}
```

Return model, VAE, CUDA/device and worker version without generating music.

Add `model_info` with:

```text
model + revision
VAE + revision
runtime version
CUDA device
VRAM
backend
quantization
generation defaults
```

Expose `APP_VERSION` and `GIT_SHA` in the worker and store them with generation metadata.

---

## 32. Truncation and diagnostics

YuE2 exposes:

```json
{"truncated":{"abc":false,"semantic":false}}
```

Never hide a true truncation flag.

Store timings for:

```text
ABC planning
semantic generation
NAR synthesis
VAE decode
model load
end-to-end
```

Normal users see total generation time; advanced users can expand technical details.

---

## 33. SSH and coding-agent access — IMPORTANT

### Serverless

The production deployment is RunPod **Serverless**. A Serverless worker is not a stable persistent machine; workers are created/destroyed automatically.

The coding agent should **not depend on SSH into the Serverless endpoint**.

For Serverless production work use:

```text
GitHub repository
RunPod builds/deployments
RunPod API
RunPod logs
application logs
```

### If the agent needs real SSH

Create a temporary **RunPod GPU Pod** from the same repository/Docker image:

```text
same Docker image
      ↓
temporary GPU Pod
      ↓
SSH / shell / nvidia-smi / interactive testing
      ↓
fix code
      ↓
commit to GitHub
      ↓
rebuild Serverless endpoint
      ↓
terminate temporary Pod
```

If the coding agent supports SSH, provide via secret management only:

```text
SSH host
SSH port
SSH username
SSH private key / key reference
```

Never commit private SSH keys to GitHub. The agent does not need the RunPod account password.

---

## 34. Do not falsely advertise these as native YuE2 features

```text
voice cloning
speaker identity preservation
direct audio-reference conditioning
phoneme alignment
local audio inpainting
stem separation
sample-accurate waveform editing
native MIDI request input
```

They may later be added through separate services, but must be labelled as separate functionality.

---

## 35. Future integrations

Architect for later additions:

```text
Stem separation
Mastering
MERT2 analysis
ASR lyric verification
Automatic quality scoring
Best-of-N ranking
MIDI ↔ ABC conversion
DAW export
```

Do not block v1 waiting for them.

---

## 36. Implementation milestones

### Milestone 1 — production worker API

```text
persistent storage
action router
generate
plan
render_from_abc
decode_latents
health
model_info
full SongRequest
ABC + semantic sampling
decoder choice
structured results
tests
```

### Milestone 2 — Core Studio

```text
Projects
Create workspace
Style
Lyrics
Generation modes
Advanced controls
Job queue
Audio player
Versions
Artifacts
```

### Milestone 3 — Score Lab

```text
ABC editor
plan-only workflow
ABC upload/paste
validation
render edited score
version provenance
```

### Milestone 4 — Compare

```text
A/B player
metadata diff
prompt/lyrics diff
score diff
```

### Milestone 5 — Covers

```text
separate SheetSage2 service
audio upload
transcription
score review
YuE2 cover render
```

### Milestone 6 — AI score editing

```text
natural-language edits
invariants
ABC validation
render and compare
```

---

## 37. Acceptance criteria

### Generation

- [ ] `full` works.
- [ ] `melody` works.
- [ ] `off` works.
- [ ] custom seed works.
- [ ] custom CFG works.
- [ ] ABC sampling overrides work.
- [ ] semantic sampling overrides work.
- [ ] ABC is blocked in `off`.
- [ ] output audio is playable 48 kHz stereo.
- [ ] artifacts survive worker shutdown.

### Composition

- [ ] plan-only works.
- [ ] ABC can be downloaded and edited.
- [ ] edited ABC can be rendered.
- [ ] parent version remains unchanged.

### Versions

- [ ] parent-child relationships work.
- [ ] duplicate/reproduce works.
- [ ] compare works.
- [ ] seed/config/model differences are visible.

### RunPod

- [ ] API key never reaches browser.
- [ ] model loads once per worker lifecycle.
- [ ] Active Workers may remain 0.
- [ ] page refresh does not lose jobs.
- [ ] failed jobs retain error state.

### UI

- [ ] professional desktop workspace.
- [ ] coherent dark/amber visual system.
- [ ] resizable/collapsible panels.
- [ ] professional waveform player.
- [ ] clear queue/running/failure states.
- [ ] no fake progress percentages.
- [ ] mobile can monitor and play projects.

---

## 38. Required order for the implementation agent

```text
1. Inspect current `flowengaged/music` code and preserve working deployment.
2. Add persistent object storage.
3. Expand the handler request schema.
4. Add action router.
5. Implement generate.
6. Implement plan.
7. Implement render_from_abc.
8. Implement decode_latents.
9. Implement health/model_info.
10. Add tests + GPU smoke test.
11. Build database + application API.
12. Implement RunPod job orchestration.
13. Build Create workspace.
14. Build audio player + version history.
15. Build Score Lab.
16. Build Compare.
17. Deploy SheetSage2 separately.
18. Build Covers.
19. Add AI score editing last.
```

---

## 39. Definition of done

A musician can:

```text
Create project
→ write lyrics
→ define style
→ choose Full / Melody / Direct
→ generate composition or complete song
→ listen
→ inspect ABC
→ edit melody/harmony/tempo/form
→ render child version
→ A/B compare
→ download FLAC + score + artifacts
→ reproduce or branch any version
```

Cover workflow:

```text
Upload recording
→ SheetSage2 transcription
→ inspect/edit ABC
→ define target style/lyrics
→ YuE2 render
→ compare/preserve versions
```

The final product must feel like a **professional creative studio**, not a simple inference form.

---

## 40. Actual YuE2 interfaces used by this specification

```text
YuE2Pipeline.from_pretrained()
YuE2Pipeline.plan()
YuE2Pipeline.generate_semantic()
YuE2Pipeline.synthesize()
YuE2Pipeline.decode()
SongResult.save_artifacts()
SymbolicPlan.load()
```

Core modes:

```text
full
melody
off
```

Core request fields:

```text
style
lyrics
cot
seed
abc
cfg_scale
id
```

Official references:

```text
https://github.com/multimodal-art-projection/YuE
https://github.com/multimodal-art-projection/YuE/blob/main/docs/generation.md
https://github.com/multimodal-art-projection/YuE/blob/main/docs/covers.md
https://github.com/multimodal-art-projection/YuE/blob/main/docs/editing.md
https://huggingface.co/m-a-p/YuE2-3B
https://docs.runpod.io/
```

---

## Final instruction

Treat this as a production music application.

Do not deliver one prompt field, one Generate button and one HTML audio tag.

The product is:

> **creation + symbolic control + professional listening + version history + reproducibility**

Expose complexity progressively:

```text
simple creative controls
+
advanced model controls
+
score-level editing
+
technical reproducibility metadata
```

Verify behaviour against the actual YuE2 source before implementing any parameter or claiming any capability.
