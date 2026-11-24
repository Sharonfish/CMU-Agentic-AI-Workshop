"""Study Planner agent, built in three parts in one file.

  PART 1  tools        the model gets hands: functions + schemas + one round trip
  PART 2  the loop     call model -> run tools -> repeat  (this is the agent)
  PART 3  memory       recall before the loop, reflect after it

Test each part as you finish it:
  python agent.py part1
  python agent.py part2 data/day1.json      then  data/day2.json
  python agent.py part3 data/day1.json      then  data/day2.json
"""
import json
import os
import sys

import anthropic
from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())  # ANTHROPIC_API_KEY from the project's .env

client = anthropic.Anthropic()
MODEL = os.environ.get("MODEL", "claude-sonnet-5-5")
SYSTEM = ("You are a study planner for a student. Check free "
          "slots before adding a study block.")


# ===========================================================================
# PART 1 · Tools. The model never runs them; it asks, we run, we report back.
# ===========================================================================

# --- 1a. Plain Python functions ---------------------------------------------
ASSIGNMENTS = [
    {"course": "HIST210", "task": "Reading response", "due": "Wed 9am"},
    {"course": "MATH120", "task": "Homework 6", "due": "Fri 9am"},
    {"course": "CS101", "task": "Problem set 4", "due": "Sat 5pm"},
]
FREE_SLOTS = {"Mon": ["7pm"], "Tue": ["10am"], "Wed": ["4pm"],
              "Thu": ["8pm"], "Fri": ["3pm"], "Sat": ["10am"]}
PLANNER = []


def get_assignments():
    return ASSIGNMENTS


def check_free_slots(day):
    return FREE_SLOTS.get(day[:3].title(), [])


def add_study_block(day, time, task):
    PLANNER.append({"day": day, "time": time, "task": task})
    json.dump(PLANNER, open("planner.json", "w"), indent=2)
    return "added"


TOOLS = {f.__name__: f for f in
         (get_assignments, check_free_slots, add_study_block)}

# --- 1b. Schemas: the only thing the model knows about the functions --------
TOOL_SCHEMAS = [
    {
        "name": "get_assignments",
        "description": "List the student's assignments and due dates.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "check_free_slots",
        "description": "Free study slots on a day of the week.",
        "input_schema": {
            "type": "object",
            "properties": {
                "day": {"type": "string", "description": "e.g. Mon, Tue"},
            },
            "required": ["day"],
        },
    },
    {
        "name": "add_study_block",
        "description": "Put a study block on the student's planner.",
        "input_schema": {
            "type": "object",
            "properties": {
                "day": {"type": "string"},
                "time": {"type": "string"},
                "task": {"type": "string"},
            },
            "required": ["day", "time", "task"],
        },
    },
]


# --- 1c. Call the model with the tools --------------------------------------
def call_model(messages, system=SYSTEM):
    return client.messages.create(
        model=MODEL, max_tokens=1024, system=system,
        tools=TOOL_SCHEMAS, messages=messages)


# --- 1d. Run what the model asked for ---------------------------------------
def run_tools(response):
    results = []
    for block in response.content:
        if block.type != "tool_use":
            continue
        print(f"[tool] {block.name}({block.input})")
        output = TOOLS[block.name](**block.input)
        results.append({"type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(output)})
    return results


# --- 1e. Test: one round trip, by hand --------------------------------------
def demo_part1():
    messages = [{"role": "user",
                 "content": "What's due this week, and am I free on Monday?"}]

    first = call_model(messages)
    print("stop_reason:", first.stop_reason)          # "tool_use": it wants tools
    messages.append({"role": "assistant", "content": first.content})
    messages.append({"role": "user", "content": run_tools(first)})

    second = call_model(messages)
    print("stop_reason:", second.stop_reason)         # "end_turn" if it is done
    print("".join(b.text for b in second.content if b.type == "text"))


# ===========================================================================
# PART 2 · The loop. Part 1's round trip, repeated until the model stops
# asking for tools. This is the whole "agent".
# ===========================================================================
def run_agent(task, system=SYSTEM, max_steps=10):
    messages = [{"role": "user", "content": task}]
    for step in range(max_steps):
        response = call_model(messages, system)
        messages.append({"role": "assistant", "content": response.content})
        if response.stop_reason != "tool_use":          # done: no more tools
            reply = "".join(b.text for b in response.content
                            if b.type == "text")
            return reply, messages
        messages.append({"role": "user", "content": run_tools(response)})
    return "Stopped after max_steps", messages


# ===========================================================================
# PART 3 · Memory. The loop does not change; we wrap it.
#   recall  (before): put what we know about the student into the prompt
#   reflect (after):  ask the model what is worth remembering, save it
# ===========================================================================

# --- 3a. Memory lives in a JSON file, keyed by student ----------------------
MEMORY_FILE = "memory.json"


def load_memory():
    if not os.path.exists(MEMORY_FILE):
        return {}
    return json.load(open(MEMORY_FILE))


def save_memory(memory):
    json.dump(memory, open(MEMORY_FILE, "w"), indent=2)


# --- 3b. Recall --------------------------------------------------------------
def recall(student, memory):
    known = memory.get(student)
    if not known:
        print(f"[memory] nothing known about {student}")
        return SYSTEM
    print(f"[memory] {student}: {len(known['facts'])} facts, "
          f"{len(known['history'])} past messages")
    facts = "\n".join("- " + f for f in known["facts"])
    past = "\n".join("- " + h for h in known["history"])
    return (f"{SYSTEM}\n\nWhat you know about {student}:\n{facts}"
            f"\n\nPast conversations:\n{past}")


# --- 3c. Reflect -------------------------------------------------------------
REFLECT = ("From this conversation, list lasting facts about the student "
           "and a one-line summary. Reply with JSON only: "
           '{"facts": [...], "summary": "..."}')


def to_transcript(messages):
    """Flatten the conversation into plain text for reflect."""
    lines = []
    for m in messages:
        if isinstance(m["content"], str):
            lines.append(f"{m['role']}: {m['content']}")
            continue
        for b in m["content"]:
            if isinstance(b, dict):
                lines.append(f"tool result: {b['content']}")
            elif b.type == "text":
                lines.append(f"{m['role']}: {b.text}")
            elif b.type == "tool_use":
                lines.append(f"tool call: {b.name}({json.dumps(b.input)})")
    return "\n".join(lines)


def parse_json(text):
    # Models sometimes wrap JSON in prose or code fences: keep the {...} part.
    return json.loads(text[text.find("{"): text.rfind("}") + 1])


def reflect(student, messages, memory):
    resp = client.messages.create(
        model=MODEL, max_tokens=2000, system=REFLECT,
        messages=[{"role": "user", "content": to_transcript(messages)}])
    text = "".join(b.text for b in resp.content if b.type == "text")
    new = parse_json(text)
    # In production, validate this before saving: it comes from user text.
    entry = memory.setdefault(student, {"facts": [], "history": []})
    entry["facts"] += [f for f in new["facts"] if f not in entry["facts"]]
    entry["history"].append(new["summary"])
    save_memory(memory)
    print(f"[memory] saved {len(new['facts'])} facts about {student}")


# --- 3d. Wire it in: recall before the loop, reflect after it ---------------
def handle_message(msg):
    memory = load_memory()
    system = recall(msg["from"], memory)
    reply, messages = run_agent(
        f"Message from {msg['from']}:\n{msg['text']}", system)
    reflect(msg["from"], messages, memory)
    return reply


# ===========================================================================
# Run:  python agent.py part1 | part2 <msg.json> | part3 <msg.json>
# ===========================================================================
if __name__ == "__main__":
    part = sys.argv[1] if len(sys.argv) > 1 else "part1"
    if part == "part1":
        demo_part1()
    else:
        msg = json.load(open(sys.argv[2] if len(sys.argv) > 2 else "data/day1.json"))
        task = f"Message from {msg['from']}:\n{msg['text']}"
        if part == "part2":
            reply, _ = run_agent(task)
            print(reply)
        elif part == "part3":
            print(handle_message(msg))
