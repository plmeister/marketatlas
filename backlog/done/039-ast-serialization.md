# 039: AST Serialization — JSON

**Status:** pending  
**Epic:** ast  
**Priority:** medium

## Description

JSON serialization/deserialization for the AST. Enables testing, debugging, persistence, and future tooling (DSL parsers, visualizers).

## Acceptance Criteria

- [ ] `Analysis.to_json() -> str` serializes to JSON string
- [ ] `Analysis.from_json(data: str) -> Analysis` deserializes from JSON string
- [ ] Round-trip: `from_json(to_json(a)) == a` (no information loss)
- [ ] Pretty-print option for human readability
- [ ] Handles all node types: Parameter, Binding, Definition, Analysis
- [ ] Handles optional metadata fields gracefully
- [ ] Error handling: malformed JSON → clear error
- [ ] Error handling: missing required fields → clear error

## JSON Format Sketch

```json
{
  "name": "pullback_4swing",
  "version": "1.0.0",
  "definitions": [
    {
      "name": "ema20",
      "type": "analyzer",
      "impl": "EMAAnalyzer",
      "parameters": [
        {"name": "period", "value": 20}
      ]
    }
  ],
  "metadata": {
    "author": "Scott",
    "description": "4-swing pullback strategy"
  }
}
```

## Related

- Backlog 036: AST model
- Backlog 040: Compiler adapter
