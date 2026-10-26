# FragilityShield — Resource Limits & Operating Envelope

## 1. Scope & Objective

To prevent resource exhaustion, denial-of-service, runaway memory allocations, and CPU starvation in multi-tenant or containerized environments (such as Zoho Catalyst AppSail), FragilityShield defines strict, enforced upper bounds on all computational and data ingestion dimensions.

---

## 2. Enforced Operating Limits

| Dimension | Default Recommended | Strict Maximum / Hard Limit | Enforcement Point | Rejection Behavior |
| :--- | :--- | :--- | :--- | :--- |
| **Historical Observations ($N$)** | 252 – 2,520 (1 – 10 years) | **10,000 observations** | `Pydantic` schema validation | HTTP 422 Unprocessable Entity |
| **Minimum Observations** | 20 observations | **10 observations** | `fragility_engine.risk` | HTTP 400 / `ValueError` ("Insufficient observations") |
| **Monte Carlo Paths ($M$)** | 250 paths | **2,000 paths** | `simulation.py` | HTTP 422 ("Paths exceed maximum 2000") |
| **Monte Carlo Horizon ($T$)** | 30 days | **365 days** | `simulation.py` | HTTP 422 ("Horizon exceeds maximum 365") |
| **Bootstrap Iterations ($B$)** | 300 resamples | **1,000 resamples** | `simulation.py` | HTTP 422 ("Resamples exceed maximum 1000") |
| **Portfolio Assets ($K$)** | 5 – 50 assets | **100 assets** | `portfolio_loader.py` | HTTP 422 ("Portfolio exceeds 100 assets") |
| **Optimization Assets** | 2 – 30 assets | **50 assets** | `allocation.py` | HTTP 422 ("Optimization exceeds 50 assets") |
| **File Upload Size** | 100 KB – 1 MB | **10 MB** | Starlette / FastAPI middleware | HTTP 413 Payload Too Large |
| **Request Timeout** | N/A | **30 seconds** | Uvicorn / Reverse Proxy | HTTP 504 Gateway Timeout |
| **Memory Allocation (AppSail)** | 256 MB working set | **1,024 MB (1 GB) cgroup**| Catalyst AppSail container | Container restart / OOMKilled |

---

## 3. Graceful Rejection & Error Signatures

1. **Numerical Input Validation:**
   - Payloads containing non-finite floats (`NaN`, `+Inf`, `-Inf`) are immediately rejected at the Pydantic boundary with structured JSON details:
     ```json
     {
       "detail": [
         {
           "loc": ["body", "returns", 14],
           "msg": "Input should be a finite number",
           "type": "finite_float"
         }
       ]
     }
     ```
2. **Singular Matrix Protection:**
   - In `portfolio_optimization.py`, if $\det(\Sigma) \le 10^{-12}$ or eigenvalue $\lambda_{\min} < 0$, the algorithm attempts high-regularization shrinkage or explicitly returns:
     ```json
     {
       "detail": "Covariance matrix is singular or not positive semi-definite. Regularization required."
     }
     ```
3. **Payload Truncation Protection:**
   - Payloads exceeding `MAX_CONTENT_LENGTH = 10 * 1024 * 1024` are rejected before parsing to prevent memory amplification attacks.
