# FragilityShield Plugin Developer Guide

## 1. Quickstart: Building a Quant Plugin

A FragilityShield plugin consists of two files:
1. `plugin_manifest.json`: Defines identity, version, declared capabilities, and resource limits.
2. An entry point Python file exposing a callable handler.

### Example Manifest (`plugin_manifest.json`)
```json
{
  "plugin_id": "quant_momentum_alpha",
  "name": "Cross-Sectional Momentum Alpha",
  "version": "1.0.0",
  "entry_point": "momentum_plugin.py:compute_alpha",
  "publisher": "Acme Quantitative",
  "description": "Calculates 12M - 1M price momentum over historical stock universe.",
  "requested_capabilities": [
    "dataset:read",
    "result:return"
  ],
  "resource_limits": {
    "max_memory_mb": 128,
    "timeout_seconds": 4.5,
    "max_cpu_cores": 1.0
  }
}
```

---

## 2. Implementing the Entrypoint Handler

Plugins must read inputs from the designated JSON environment payload and return a validated metric dictionary:

```python
# momentum_plugin.py
import json
import sys

def compute_alpha(dataset_path: str) -> dict:
    with open(dataset_path, "r", encoding="utf-8") as f:
        candles = json.load(f)

    # Compute 12M - 1M momentum
    closes = [c["close"] for c in candles]
    if len(closes) < 252:
        return {"status": "INSUFFICIENT_DATA", "momentum_score": 0.0}

    # 12M minus 1M price momentum
    momentum = (closes[-21] - closes[-252]) / closes[-252]
    
    return {
        "status": "SUCCESS",
        "momentum_score": round(float(momentum), 4),
        "lookback_sessions": len(closes),
    }

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        res = compute_alpha(sys.argv[1])
        print(json.dumps(res))
```

---

## 3. Testing & Validating Your Plugin

1. Open **Integration & Plugin Studio** at `/integrations` in FragilityShield.
2. Select **Tab 3: Manifest Validator & Sandbox**.
3. Paste your `plugin_manifest.json` and click **Validate Manifest**.
4. Verify that the SHA-256 fingerprint is generated and all capabilities are green.
