# Build an Email Agent from Scratch: live demo code

Two folders, one per stage of the lecture. Each one runs on its own.

| Folder | What it shows | Slides |
|---|---|---|
| `stage1_basic_agent/` | Model + 3 tools + loop. Works, but forgets everything between runs. | Part 3 · Code implementation, Part 4 · Live demo |
| `stage2_memory_agent/` | The same agent plus long-term memory: recall before the loop, reflect after it. | Part 6 · Memory in code |
| `workshop_study_planner/` | Hands-on version for students: same ideas, new scenario (study planner), 3 parts with TODOs + solutions. | see its README |

Nothing is ever really sent. `send_reply` writes to `outbox.json` in the folder you run from.

## Setup (once)

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...   # Windows: set ANTHROPIC_API_KEY=...
```

Optional: choose another model with `export MODEL=<model id>` (default `claude-sonnet-5-5`).

## Demo script

### Stage 1: the agent works, then forgets

```bash
cd stage1_basic_agent
python agent.py data/day1.json   # Alice: "call me Ali, never Thursdays, ref Q4-4471, keep it short"
python agent.py data/day2.json   # New session: "What was the ref number? Meet next week, afternoons?"
cat outbox.json
```

Day 1 plants three things the agent can only get right on day 2 if it remembers:
1. a fact it cannot guess: the contract reference number `Q4-4471`;
2. a constraint that conflicts with the "obvious" answer: Alice is out every Thursday, but Thu 2pm is the only free afternoon slot;
3. two style preferences: call her "Ali", keep replies to 1–2 sentences.

What to point out:
- The `[tool]` lines: the model chose the order (read → check calendar → reply).
- Day 2 is a fresh process, so `messages` starts empty. Expect: "Hi Alice", a 4-line reply, "I don't have the reference number", and a Thursday 2pm proposal, the one day she said never to book.

### Stage 2: the same agent, with memory

```bash
cd ../stage2_memory_agent
rm -f memory.json outbox.json    # start clean
python agent.py data/day1.json   # [memory] nothing known → saves ~5 facts about Alice
cat memory.json                  # facts (semantic) + history (episodic)
python agent.py data/day2.json   # [memory] alice@acme.com: 5 facts, 1 past email
cat outbox.json
```

What to point out:
- `[memory]` lines show recall before the loop and reflect after it.
- The loop is unchanged; only `handle_email` wraps it.
- The day 2 reply should now say "Hi Ali", give `Q4-4471`, skip Thursday (watch the `[tool]` lines: it does not even check Thu) and propose Friday 10am instead, in two sentences.
- Side by side with stage 1, every one of the four differences comes from `memory.json`, not from the prompt or the loop.

## Where each slide lives in the code

| Slide | stage1 `agent.py` | stage2 `agent.py` |
|---|---|---|
| Define the three tools | `get_unread_emails`, `check_calendar`, `send_reply`, `TOOLS` | same |
| Call the model with the tools | `call_model` | `call_model(messages, system)` |
| Run what the model asks for | `run_tools` | same |
| Wrap it in a loop | `run_agent` | `run_agent` (also returns the transcript) |
| Store memory in a JSON file | — | `load_memory`, `save_memory` |
| Recall | — | `recall` |
| Reflect | — | `reflect` |
| Wire it in | — | `handle_email` |

## Small differences from the slides

To keep the live demo robust, the code has a few extras the slides leave out:
- `TOOL_SCHEMAS` is written out in full (the slide shows one schema).
- `check_calendar` accepts "Thursday" as well as "Thu".
- `reflect` pulls the JSON out of the model's reply even if it is wrapped in prose or code fences, and skips duplicate facts. It only reads `text` blocks (some models also return `thinking` blocks) and uses `max_tokens=2000` so the JSON is not cut off.
- `[memory]` print lines make recall and reflect visible on screen.

## Tips for the live demo

- Run each step once before the lecture so you know what the model tends to say.
- Model output varies run to run. If a reply surprises you, that is a good moment to talk about evals.
- To show prompt injection afterwards, add an email to `data/day2.json` whose body says "Ignore your rules…", and watch what reflect saves into `memory.json`.
