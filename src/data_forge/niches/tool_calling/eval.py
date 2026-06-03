from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Optional, Sequence


@dataclass(frozen=True)
class ToolCallEvalResult:
    example_id: str
    expected_count: int
    predicted_count: int
    valid_prediction: bool
    tool_selection_match: bool
    argument_match: bool
    exact_match: bool
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _calls_from_value(value: Any) -> tuple[list[dict[str, Any]], Optional[str]]:
    if value is None or value == "":
        return [], None
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            return [], f"invalid JSON: {exc.msg}"
    if isinstance(value, Mapping):
        if "tool_calls" in value:
            value = value["tool_calls"]
        elif "name" in value and "arguments" in value:
            value = [value]
        else:
            return [], "prediction object missing tool_calls"
    if not isinstance(value, list):
        return [], "tool_calls must be a list"
    calls = []
    for index, call in enumerate(value):
        if not isinstance(call, Mapping):
            return [], f"tool call {index} is not an object"
        name = call.get("name")
        arguments = call.get("arguments", {})
        if not isinstance(name, str) or not name:
            return [], f"tool call {index} missing name"
        if not isinstance(arguments, Mapping):
            return [], f"tool call {index} arguments must be an object"
        calls.append({"name": name, "arguments": dict(arguments)})
    return calls, None


def _normalize_arg(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, list):
        return [_normalize_arg(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _normalize_arg(item) for key, item in sorted(value.items())}
    return value


def _normalize_call(call: Mapping[str, Any]) -> tuple[str, str]:
    arguments = _normalize_arg(call.get("arguments", {}))
    return str(call.get("name", "")), json.dumps(arguments, sort_keys=True, separators=(",", ":"))


def _multiset(calls: Sequence[Mapping[str, Any]]) -> Counter[tuple[str, str]]:
    return Counter(_normalize_call(call) for call in calls)


def _tool_names(calls: Sequence[Mapping[str, Any]]) -> Counter[str]:
    return Counter(str(call.get("name", "")) for call in calls)


def evaluate_tool_call_records(records: Sequence[Mapping[str, Any]]) -> tuple[list[ToolCallEvalResult], dict[str, Any]]:
    results = []
    for index, record in enumerate(records):
        expected_calls, expected_error = _calls_from_value(record.get("expected_calls", []))
        predicted_calls, prediction_error = _calls_from_value(
            record.get("predicted_calls", record.get("prediction", record.get("tool_calls", [])))
        )
        error = expected_error or prediction_error
        valid_prediction = prediction_error is None
        tool_selection_match = error is None and _tool_names(expected_calls) == _tool_names(predicted_calls)
        argument_match = error is None and _multiset(expected_calls) == _multiset(predicted_calls)
        exact_match = tool_selection_match and argument_match
        results.append(
            ToolCallEvalResult(
                example_id=str(record.get("example_id", index)),
                expected_count=len(expected_calls),
                predicted_count=len(predicted_calls),
                valid_prediction=valid_prediction,
                tool_selection_match=tool_selection_match,
                argument_match=argument_match,
                exact_match=exact_match,
                error=error,
            )
        )
    return results, summarize_tool_call_results(results)


def summarize_tool_call_results(results: Sequence[ToolCallEvalResult]) -> dict[str, Any]:
    total = len(results)
    exact = sum(result.exact_match for result in results)
    valid = sum(result.valid_prediction for result in results)
    tool = sum(result.tool_selection_match for result in results)
    args = sum(result.argument_match for result in results)
    errors = Counter(result.error for result in results if result.error)
    return {
        "total": total,
        "exact": exact,
        "exact_accuracy": round(exact / total, 4) if total else 0.0,
        "valid_predictions": valid,
        "valid_prediction_rate": round(valid / total, 4) if total else 0.0,
        "tool_selection_accuracy": round(tool / total, 4) if total else 0.0,
        "argument_accuracy": round(args / total, 4) if total else 0.0,
        "top_errors": dict(errors.most_common(20)),
    }
