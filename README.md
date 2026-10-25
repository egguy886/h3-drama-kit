# h3-drama-kit

**English** · [简体中文](README.zh-CN.md)

> **A reusable, end-to-end pipeline for AI short dramas on MiniMax H3** — script → assets (look and voice) → shot prompts → compile-time checks → cloud generation on AutoDL → review and retakes → post-production and delivery.
> Distilled from the production of *Crossing the Line*, a 60-episode AI drama (480 segments, about 120 minutes), and roughly 150 controlled comparison runs on RunningHub's H3. It works both as a Claude Code / Codex skill and as a plain set of Python tools.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Model](https://img.shields.io/badge/Video-MiniMax%20H3-brightgreen.svg)](#requirements)
[![Agents](https://img.shields.io/badge/Agent-Claude%20Code%20%7C%20Codex-orange.svg)](#install-as-a-skill)

---

## Why this exists

On a 60-episode AI drama, generation isn't what eats the budget. **Retakes** are: faces that drift between segments, blocking that doesn't cut together, half a line of dialogue trimmed at a seam, a voice that changes pitch every 15 seconds, fights that play like slow motion, an episode that cuts to black before the last word. *Crossing the Line* hit every one of these, and logged the data.

The kit turns that into three things:

- **Playbooks** — what to do at each stage and what gate it must pass. Every writing rule carries an evidence grade: *production-verified*, *A/B-tested on RunningHub*, *third-party*, or *tested and useless*.
- **Scripts** — the rules, enforced in code: bad prompts are blocked at compile time, every paid run is pre-checked and priced, dialogue is verified against the locked script after generation, and post-production is one command per episode.
- **Templates** — a sample project that runs end to end at zero cost, including a local mock of the generation API.

## The pipeline

| Stage | What happens | Tools | Gate |
|---|---|---|---|
| S0 Setup | aspect ratio, language, segments per episode, delivery spec, content level | `new_project.py` | aspect and content level confirmed |
| S1 Script audit + dialogue lock | lock dialogue word for word, estimate timing, move device audio to post | `lock_dialogue.py`, `plans/move_post.py` | no open logic conflicts |
| S2 Assets | break characters / locations / props into IDs, library entries, reference images; cast voices | `asset_gaps.py`, `blocking_diagram.py` | no missing reference images |
| S3 Shot plan | one `plans/eNN.py` per episode: shots, durations, dialogue placement, blocking, seams | `plans/pw.py` | self-check list |
| S4 Compile + lint | build bilingual prompts and validate them automatically | `compose_plan.py`, `build_episode.py`, `shot_lint.py`, `axis_lint.py` | zero ❌ |
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

## Ten shot-writing rules

From `playbook/04`; the evidence for each is in `playbook/09`.

1. Each segment is exactly 15.0 s with at most 6 shots; the last line of dialogue ends by 13.5 s; the final 1–1.5 s is a held moment with content. *(production)*
2. Within a scene, cut hard between segments and open the new segment on a different shot size, with a motivated seam (action, gaze or sound). No last-frame relays; never wide-to-wide. *(production)*
3. Opening wides must **move** (camera move plus ongoing action). Avoid "static shot"; never write "slow motion". *(production + A/B)*
4. In fights, one strike per shot, 0.8–1.4 s each. *(A/B + production)*
5. Positive phrasing only; describe the state already in progress; give every gaze a target; use frame-left / frame-right; sequence multi-person actions. *(production)*
6. A dialogue shot carries only its line; the action after the line goes in the next shot; other visible faces get "lips at rest". *(production + third-party)*
7. Blocking cards describe only what stays still for the whole segment; anyone who moves is written into the shots (otherwise they appear twice). *(production)*
8. Static scenes with three or more people open with a silent, one-second position lock; add a greyscale lettered blocking diagram for exact positions. *(A/B)*
9. Out-of-focus foreground objects (pipes, mirrors, railings) for depth; eyes lead the head. *(A/B)*
10. Changeable objects are drawn in their *before-action* state in reference images; every state change gets its own image. *(production + A/B)*

**Tested and useless or harmful:** count locks ("exactly one…"), describing a higher voice, pitch-shifting the reference audio, using "silence" to time dialogue starts, dropping the location reference, first-frame locks, height numbers, slimmed-down prompts for dialogue segments, full-line TTS replacement.

## Layout

| Path | Contents |
|---|---|
| `SKILL.md` | Skill entry point: pipeline, hard rules, the ten shot rules |
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

- [write-screenplay-skill](https://github.com/egguy886/write-screenplay-skill) — the step before this one: adapts novels into micro-drama scripts, builds a production bible, and exports it directly into this kit's asset library format.

## Language

Playbooks and the body of `SKILL.md` are written in Chinese, because the rules come from Chinese production logs. Ask your agent in any language and it will answer in that language.

## License

[MIT](LICENSE). Third-party models and tools (MiniMax H3, AutoDL, seed-vc, VoxCPM, Whisper) are subject to their own licenses and terms of service.
