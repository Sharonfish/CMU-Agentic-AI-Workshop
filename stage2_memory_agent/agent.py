"""Stage 2: the same email agent, plus long-term memory (recall + reflect).

Run:  python agent.py data/day1.json   # Alice introduces herself; memory.json is written
      python agent.py data/day2.json   # a new session: it remembers her
Reset: delete memory.json and outbox.json
"""
import json
import os
import sys

import anthropic
from dotenv import load_dotenv

# Load ANTHROPIC_API_KEY (and optional MODEL) from a .env file in the project
# root or this folder, if present. Real environment variables take priority.
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))
load_dotenv()

# ---------------------------------------------------------------------------
# Tools (unchanged from stage 1)
# ---------------------------------------------------------------------------
INBOX_FILE = sys.argv[1] if len(sys.argv) > 1 else "data/day1.json"
INBOX = json.load(open(INBOX_FILE))
CALENDAR = {"Thu": ["2pm"], "Fri": ["10am"]}
OUTBOX = json.load(open("outbox.json")) if os.path.exists("outbox.json") else []


def get_unread_emails():
    return [e for e in INBOX if not e["read"]]


def check_calendar(day):
    return CALENDAR.get(day[:3].title(), [])


def send_reply(email_id, text):
    # Demo only: nothing is really sent. Replies are saved to outbox.json.
    OUTBOX.append({"id": email_id, "text": text})
    for e in INBOX:
        if e["id"] == email_id:
            e["read"] = True
    json.dump(OUTBOX, open("outbox.json", "w"), indent=2)
    return "saved to outbox"


TOOLS = {f.__name__: f for f in
         (get_unread_emails, check_calendar, send_reply)}

TOOL_SCHEMAS = [
    {
        "name": "get_unread_emails",
        "description": "Get my unread emails.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "check_calendar",
        "description": "Free slots on a day of the week.",
        "input_schema": {
            "type": "object",
            "properties": {
                "day": {"type": "string", "description": "Day of the week, e.g. Thu"}
            },
            "required": ["day"],
        },
    },
    {
        "name": "send_reply",
        "description": "Reply to an email.",
        "input_schema": {
            "type": "object",
            "properties": {
                "email_id": {"type": "integer"},
                "text": {"type": "string"},
            },
            "required": ["email_id", "text"],
        },
    },
]

# ---------------------------------------------------------------------------
# Model call and loop (same as stage 1, except the system prompt is passed in
# and run_agent also returns the transcript for reflect)
# ---------------------------------------------------------------------------
client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
MODEL = os.environ.get("MODEL", "claude-sonnet-5-5")

SYSTEM = ("You are my email assistant. Check my "
          "calendar before proposing a meeting time.")


def call_model(messages, system):
    return client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=system,
        tools=TOOL_SCHEMAS,
        messages=messages,
    )


def run_tools(response):
    results = []
    for block in response.content:
        if block.type != "tool_use":
            continue
        print(f"[tool] {block.name}({block.input})")
        output = TOOLS[block.name](**block.input)
        results.append({
            "type": "tool_result",
            "tool_use_id": block.id,
            "content": json.dumps(output),
        })
    return results


def to_transcript(messages):
    """Flatten messages into plain text for reflect."""
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


def run_agent(task, system, max_steps=10):
    messages = [{"role": "user", "content": task}]
    for step in range(max_steps):
        response = call_model(messages, system)
        messages.append({"role": "assistant",
                         "content": response.content})
        if response.stop_reason != "tool_use":
            reply = "".join(b.text for b in response.content
                            if b.type == "text")
            return reply, to_transcript(messages)
        messages.append({"role": "user",
                         "content": run_tools(response)})
    return "Stopped after max_steps", to_transcript(messages)


# ---------------------------------------------------------------------------
# Memory 1 · Store memory in a JSON file
# ---------------------------------------------------------------------------
MEMORY_FILE = "memory.json"


def load_memory():
    if not os.path.exists(MEMORY_FILE):
        return {}
    return json.load(open(MEMORY_FILE))


def save_memory(memory):
    json.dump(memory, open(MEMORY_FILE, "w"), indent=2)


# ---------------------------------------------------------------------------
# Memory 2 · Recall: put what we know into the prompt
# ---------------------------------------------------------------------------
def recall(sender, memory):
    known = memory.get(sender)
    if not known:
        print(f"[memory] nothing known about {sender}")
        return SYSTEM
    n = len(known["history"])
    print(f"[memory] {sender}: {len(known['facts'])} facts, "
          f"{n} past email{'s' if n != 1 else ''}")
    facts = "\n".join("- " + f for f in known["facts"])
    past = "\n".join("- " + h for h in known["history"])
    return (f"{SYSTEM}\n\nWhat you know about {sender}:\n"
            f"{facts}\n\nPast emails with them:\n{past}")


# ---------------------------------------------------------------------------
# Memory 3 · Reflect: save what we learned
# ---------------------------------------------------------------------------
REFLECT = ("From this thread, list lasting facts about the "
           "sender and a one-line summary. Reply with JSON only: "
           '{"facts": [...], "summary": "..."}')


def parse_json(text):
    # Models sometimes wrap JSON in prose or code fences: keep the {...} part.
    return json.loads(text[text.find("{"): text.rfind("}") + 1])


def reflect(sender, transcript, memory):
    resp = client.messages.create(
        model=MODEL, max_tokens=2000,  # room for thinking + the JSON
        system=REFLECT,
        messages=[{"role": "user", "content": transcript}])
    # Only keep text blocks: some models also return thinking blocks.
    text = "".join(b.text for b in resp.content if b.type == "text")
    new = parse_json(text)
    # In production, validate this before saving: it comes from email text.
    entry = memory.setdefault(sender,
                              {"facts": [], "history": []})
    entry["facts"] += [f for f in new["facts"] if f not in entry["facts"]]
    entry["history"].append(new["summary"])
    save_memory(memory)
    print(f"[memory] saved {len(new['facts'])} facts about {sender}")


# ---------------------------------------------------------------------------
# Memory 4 · Wire it in: recall before, reflect after
# ---------------------------------------------------------------------------
def handle_email(email):
    memory = load_memory()
    system = recall(email["from"], memory)
    reply, transcript = run_agent(
        f"Reply to this email:\n{json.dumps(email)}", system)
    reflect(email["from"], transcript, memory)
    return reply


if __name__ == "__main__":
    for email in get_unread_emails():
        print(handle_email(email))
