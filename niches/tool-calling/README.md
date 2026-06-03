# Tool Calling

This niche is the second Data Forge Lab recipe target after Text-to-SQL.

The goal is to fine-tune a small local model to emit valid tool calls:

- choose the correct tool
- fill arguments correctly
- refuse tool use when no tool applies
- handle multiple and parallel calls

The public benchmark target is BFCL-style function calling. The current implementation includes a small local evaluator and seed fixture so the Lab can create a locked eval artifact before model training.

## Current Commands

Evaluate a JSONL prediction file:

```bash
python3 niches/tool-calling/scripts/evaluate_tool_calls.py \
  --input niches/tool-calling/examples/eval_cases.jsonl \
  --out /tmp/tool_call_eval
```

The file format expects:

```json
{
  "example_id": "calendar_001",
  "prompt": "Schedule a meeting tomorrow at 10am with Maya.",
  "tools": [
    {
      "name": "create_calendar_event",
      "parameters": {
        "type": "object",
        "properties": {
          "title": {"type": "string"}
        }
      }
    }
  ],
  "expected_calls": [
    {
      "name": "create_calendar_event",
      "arguments": {"title": "Meeting with Maya"}
    }
  ],
  "predicted_calls": []
}
```

## Metrics

- exact accuracy
- valid prediction rate
- tool-selection accuracy
- argument accuracy
