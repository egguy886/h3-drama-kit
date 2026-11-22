# h3-drama-kit

**English** · [简体中文](README.zh-CN.md)

> **A reusable, end-to-end pipeline for AI short dramas on MiniMax H3 (v2.0 Spatial Rigor & Anti-Continuity-Bug Edition)** — script → assets (look and voice) → scene-to-subspace `STAGING_MAP` → shot prompts → compile-time hard gates → cloud generation on AutoDL → review and retakes → post-production and delivery.
> Distilled from the production of *Crossing the Line* (60 episodes / 480 segments), ~150 controlled A/B runs on RunningHub's H3, and widescreen period-fantasy continuity post-mortems. Works both as a Claude Code / Codex / Gemini skill and as standalone Python tools.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Model](https://img.shields.io/badge/Video-MiniMax%20H3-brightgreen.svg)](#requirements)
[![Agents](https://img.shields.io/badge/Agent-Claude%20Code%20%7C%20Codex-orange.svg)](#install-as-a-skill)

---

## Why this exists

On a 60-episode AI drama, generation isn't what eats the budget. **Retakes** are: faces that drift between segments, blocking that doesn't cut together, distinct rooms sharing one fixed-composition plate so characters spawn in place, stray black-clad strangers hallucinated from unmounted "silhouette" prompts, corpses swaying with idle breathing, half a line trimmed at a seam, or fights playing in slow motion.

The kit turns those lessons into three things:

- **Playbooks** — what to do at each stage and what gate it must pass. Every writing rule carries an evidence grade: *production-verified*, *A/B-tested on RunningHub*, *third-party*, or *tested and useless*.
- **Scripts** — the rules enforced in code: spatial reuse, micro-cuts, unmounted shadows, and missing corpse-motionless locks are blocked at compile time (`❌`), every paid run is pre-checked and priced, dialogue is verified against the locked script, and post-production is one command per episode.
- **Templates** — a sample project that runs end to end at zero cost, including a local mock of the generation API.

## The pipeline

| Stage | What happens | Tools | Gate |
|---|---|---|---|
| S0 Setup | aspect ratio, language, segments per episode, delivery spec, content level | `new_project.py` | aspect and content level confirmed |
| S1 Script audit + dialogue lock | lock dialogue word for word (dual-track `3.8 chars/s` CN / `2.5 words/s` EN), estimate timing, move device audio to post | `lock_dialogue.py`, `plans/move_post.py` | no open logic conflicts |
| S2 Assets | break characters / dedicated sub-space locations / props into IDs, library entries, reference images; cast voices | `asset_gaps.py`, `blocking_diagram.py` | no missing reference images |
| S3 Staging map + shot plan | declare `STAGING_MAP` + `plans/starts.py` (sub-space plates & barrier camera-side lock) before writing `plans/eNN.py` | `plans/pw.py`, `plans/defect_rules.py` | self-check list + pre-compile gates |
| S4 Compile + lint | build bilingual prompts and enforce spatial / shadow / motionless / shot-duration hard gates | `compose_plan.py`, `build_episode.py`, `shot_lint.py`, `axis_lint.py` | zero ❌ |
| S5 Generate | pre-check → dry run → pilot segments → overnight batch | `h3_run.py`, `h3_batch.py` | **explicit approval before any paid run** |
| S6 Review + retakes | dialogue check, contact sheets, motion check; fix at the earliest broken layer | `dialogue_check.py`, `episode_sheet.py`, `motion_check.py` | every keep is a human decision |
| S7 Post | voice consistency, device audio, assembly, room tone, subtitles and name cards, bumpers, loudness, platform edge fix | `voice_fix_ep.py`, `assemble_episode.py`, `subtitle_episode.py`, `finish_episode.py`, `tiktok_edge.py` | watch the finished episode in full |

## Quick start

```bash
git clone https://github.com/egguy886/h3-drama-kit.git
cd h3-drama-kit

# 1. Create a project (never overwrites existing files)
python3 scripts/new_project.py ~/my-drama --title-en "Night Shift" --title-cn "夜班" --aspect 9:16
cd ~/my-drama
python3 tools/kit_doctor.py                 # environment check

# 2. Run the bundled E01 sample end to end (free)
python3 tools/lock_dialogue.py scripts_fixed/E01_示例.md episodes/E01/02_dialogue_lock.json
python3 plans/e01.py && python3 tools/compose_plan.py E01
python3 tools/build_episode.py episodes/E01 --voices voices.json
python3 tools/asset_gaps.py                 # missing images + image-generation prompts
python3 tools/h3_run.py check E01           # pre-check once images are in place
python3 tools/h3_run.py run E01 --seg 1 --dry-run

# 3. Rehearse a full generation run against a local mock API (no cost)
python3 tools/mock_autodl.py &              # then: export AUTODL_BASE_URL=http://127.0.0.1:8765 AUTODL_TOKEN=TEST
```

## Install as a skill

```bash
ln -s "$(pwd)" ~/.claude/skills/h3-drama-kit     # Claude Code
ln -s "$(pwd)" ~/.agents/skills/h3-drama-kit     # Codex and other agents
```

Then ask your agent to "use h3-drama-kit to start a new drama", "write the shot plan for E05" or "generate E05".

## Twelve shot-writing & spatial rigor rules (v2.0)

From `playbook/04`; compile-time gates are enforced in `plans/pw.py`, `build_episode.py`, and `shot_lint.py`.

1. **Write `STAGING_MAP` + `starts.py` before writing shots**: map every physical sub-space to its own dedicated `scene_ref`, lock camera side relative to barriers (bars/doors/desks), and specify 0.0 s postures. *(v2.0)*
2. **Standard narrative/action shots run `2.5–5.0 s` (`3–4` shots/segment target, max 6)**: non-strike shots under `2.0 s` fail (`❌`); the last spoken line ends by `13.5 s` with a `1–1.5 s` held moment at the tail. *(v2.0)*
3. **Pure single strikes run `0.8–1.4 s`, one strike per shot**: never mix a strike and looting/prop-drawing in the same shot (`❌` — split prop retrieval into its own `≥2.5 s` shot with visible source container). *(A/B + v2.0)*
4. **Never share one fixed-composition `scene_ref` across distinct physical sub-spaces** (`❌`; pass `same_room_ok=True` only when returning to the exact same room), and never trap a same-side partner behind foreground bars on a reverse angle (`❌`). *(v2.0)*
5. **Never write `silhouette / dark figure / two figures` without mounted character plates** (`❌` — H3 invents stray black-clad strangers; use torchlight across stone + rattling lock + off-screen footsteps instead). *(v2.0)*
6. **Lock corpses, headless bodies, and feigning-sleep characters in-shot with `completely frozen motionless, zero breathing or swaying`** (`❌` — affirmative phrasing compatible with the no-negation gate; live characters still breathe and shift weight). *(v2.0)*
7. Within a scene, cut hard between segments on a different shot size with a motivated seam (`action`, `gaze`, or `sound`); avoid last-frame relays and never cut wide-to-wide. *(production)*
8. Opening wides must **move** (camera move + ongoing action); avoid `static shot` and `slow motion`. *(production + A/B)*
9. Positive phrasing only; describe states in progress; anchor every gaze; use `frame-left` / `frame-right`; sequence multi-person actions. *(production)*
10. A dialogue shot carries only its line; post-line actions go in the next shot; other visible faces get `lips at rest`. *(production + third-party)*
11. Blocking cards describe only what stays still for the whole segment; moving characters go in shots; `≥3`-person static scenes open with `lock1()`. *(production + A/B)*
12. Draw changeable props in their *before-action* state; each state change gets its own reference plate. *(production + A/B)*

**Tested and useless or harmful:** count locks ("exactly one…"), describing a higher voice, pitch-shifting the reference audio, using "silence" to time dialogue starts, dropping the location reference, first-frame locks, height numbers, slimmed-down prompts for dialogue segments, full-line TTS replacement.

## Layout

| Path | Contents |
|---|---|
| `SKILL.md` | Skill entry point: pipeline, v2.0 spatial hard gates, the twelve shot rules |
| `playbook/00–10` | Overview, script audit, visual assets, voices, **shot plans and prompts (core)**, compile checks, AutoDL generation, review and retakes, post and delivery, evidence table, pitfalls |
| `scripts/` | All tools (copied into a project's `tools/` on creation) |
| `templates/project/` | New-project template: config, asset library samples, E01 sample script and shot plan, blocking diagram sample |
| `templates/prompts/` | Reference-image prompt templates and a compiled single-segment prompt example |

## Requirements

- **Required:** Python ≥ 3.9, ffmpeg/ffprobe, Pillow, numpy.
- **Recommended:** openai-whisper (dialogue check, subtitles); [seed-vc](https://github.com/Plachtaa/seed-vc) + demucs for voice consistency (GPL-3.0, installed separately, see `playbook/08`); VoxCPM2 (device audio, voice candidates); macOS (OCR to detect subtitles burned in by H3, fonts).
- **Generation backend:** the MiniMax H3 workflow on [AutoDL](https://www.autodl.art) (`minimax_h3_zm_u24`). The token lives only in the project's `.env` as `AUTODL_TOKEN` and must **never be committed** (new projects ship with a `.gitignore` that excludes it).

## Safety and cost

- `h3_run.py` / `h3_batch.py` report task count × resolution × duration × estimated cost before any paid submission; when used as a skill, the agent must get your explicit approval before submitting.
- Network errors never trigger an automatic resubmit (run `resume` first), so you are not charged twice.
- 768p in the off-peak window was about ¥0.45 per segment (October 2026; check current pricing).

## Related

- [write-screenplay-skill](https://github.com/egguy886/write-screenplay-skill) — upstream pre-production director & scriptwriter (`v5.0`): adapts novels into single-subspace scenes with locked opening staging and exports directly into this kit's asset library format.

## Language

Playbooks and the body of `SKILL.md` are written in Chinese, because the rules come from Chinese production logs. Ask your agent in any language and it will answer in that language.

## License

[MIT](LICENSE). Third-party models and tools (MiniMax H3, AutoDL, seed-vc, VoxCPM, Whisper) are subject to their own licenses and terms of service.
