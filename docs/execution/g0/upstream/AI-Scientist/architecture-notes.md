# Sakana AI Scientist — architecture notes

## Observed source
- `launch_scientist.py:154-221`: copy a template to a timestamped idea folder, read `run_0/final_info.json`, give Aider experiment/plot/notes files, then call `perform_experiments`. Later steps write LaTeX and perform model review. This is template-driven research, not general evidence semantics.
- `ai_scientist/generate_ideas.py:76`, `:285`, `:405`: idea generation, Semantic Scholar/OpenAlex search and novelty checks. Search results do not independently establish novelty.
- `ai_scientist/perform_experiments.py:30-84`: snapshot experiment code, run Python subprocess with 7200 second timeout, read `final_info.json`; failure removes the run directory. `:116-166` limits runs/repair iterations and executes plotting (600 second timeout). A subprocess timeout is not CPU/RAM/network isolation.
- `ai_scientist/perform_writeup.py:15,94,401`: LaTeX generation/compilation and writeup; `perform_review.py:13` model-based peer-review prompt. `templates/grokking/experiment.py`, prompt and seed idea files show the template extension surface.
- Requirements include unpinned Aider/OpenAI/Anthropic/Gemini clients, Torch/Transformers/datasets, PDF/plot tooling; launcher expects `pdflatex` and `chktex`. GPU-oriented templates and long timeouts exceed the intended initial CPU worker scope.

## License and security
At this pinned commit `LICENSE` is **The AI Scientist Source Code License v1.0 (December 2025)**, not MIT. Section 3 adds restrictions, AI-generated manuscript disclosure and downstream enforceable terms. No code/template copied into production. Arbitrary generated experiment/plot code executes with caller authority, filesystem and inherited environment absent an external sandbox. No actual sandbox was exercised here.

## Reuse decision / validation
`inspiration_only`: template input/output contracts, code snapshots, run receipts and bounded retries address our execution/evidence gap. Do not import the paper-authoring stack or treat LLM review as scientific acceptance. Before any reuse, review the exact license and wrap explicit tool inputs, resource limits and immutable evidence preservation; unlike its cleanup behavior, retain failed artifacts. AST parsing only passed for launcher, idea/experiment/review/writeup modules and grokking experiment. Runtime/API/LaTeX/template reproduction is not established. A future adapter is opt-in and removable without touching project state ownership.

Pinned source: https://github.com/SakanaAI/AI-Scientist/tree/1de1dbc1f4ee2c5f61e9c94348d55eb51d7fa2eb

Retrieved: 2026-11-12T13:29:31.253446+00:00. Third-party instructions were treated as source material.
