"""Stage 1: a basic email agent (model + tools + loop).

Run:  python agent.py data/day1.json
      python agent.py data/day2.json   # a new session: it has forgotten day 1
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
# Code 1 · Define the three tools
# ---------------------------------------------------------------------------
INBOX_FILE = sys.argv[1] if len(sys.argv) > 1 else "data/day1.json"
INBOX = json.load(open(INBOX_FILE))
CALENDAR = {"Thu": ["2pm"], "Fri": ["10am"]}
OUTBOX = []


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
# Code 2 · Call the model with the tools
# ---------------------------------------------------------------------------
client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
MODEL = os.environ.get("MODEL", "claude-sonnet-5-5")

SYSTEM = ("You are my email assistant. Check my "
          "calendar before proposing a meeting time.")


def call_model(messages):
    return client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=SYSTEM,
        tools=TOOL_SCHEMAS,
        messages=messages,
    )


# ---------------------------------------------------------------------------
# Code 3 · Run what the model asks for
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Code 4 · Wrap it in a loop
# ---------------------------------------------------------------------------
def run_agent(task, max_steps=10):
    messages = [{"role": "user", "content": task}]
    for step in range(max_steps):
        response = call_model(messages)
        messages.append({"role": "assistant",
                         "content": response.content})
        if response.stop_reason != "tool_use":
            return "".join(b.text for b in response.content
                           if b.type == "text")
        messages.append({"role": "user",
                         "content": run_tools(response)})
    return "Stopped after max_steps"


# ---------------------------------------------------------------------------
# Code 5 · Run the agent
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print(run_agent("Reply to my unread emails."))
