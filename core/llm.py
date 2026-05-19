import json
import re
import anthropic
import config


class LLMParseError(Exception):
    pass


def call_llm(system: str, user: str, model: str = config.MODEL_NAME) -> str:
    client = anthropic.Anthropic()
    message = client.messages.create(
        model=model,
        max_tokens=2048,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return message.content[0].text


def extract_json(raw_response: str) -> dict:
    text = raw_response.strip()
    # Strip markdown code fences if present
    match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if match:
        text = match.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise LLMParseError(f"JSON parse error: {e}\nRaw response:\n{raw_response}") from e
