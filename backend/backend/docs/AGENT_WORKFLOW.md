# Agent workflow

## Payment path

1. Parse natural language into a validated `PaymentIntent`.
2. Apply deterministic instruction guardrails before a model output can prepare a side effect.
3. Build a visible plan based on intent type.
4. Resolve an exact **user-created payment destination** and read the latest account balance.
5. Assign the fixed amount-based risk band.
6. Evaluate deterministic payment policies.
7. If any hard rule fails, stop and expose the failed checks.
8. If the amount is `≤ ₹2,000`, auto-authorize and continue to final revalidation.
9. If the amount is `> ₹2,000`, persist `AWAITING_APPROVAL` and pause. Resume only after explicit approve/reject input.
10. A user condition such as “ask me if it is above ₹500” can deliberately force approval below ₹2,000.
11. Before either auto or approved execution, serialize the final check/act boundary and **re-read current state**.
12. Revalidate destination/bill state, fixed risk, balance, daily limit and user conditions.
13. Execute the idempotent simulated payment only if revalidation still passes.
14. Verify the ledger state, return the transaction ID and persist the audit trail.

Execution-time revalidation matters because another payment may have changed balance or daily-limit usage between preparation and final execution.

## Risk path

Risk is intentionally fixed and explainable:

- LOW: amount `≤ ₹10,000`
- MEDIUM: amount `> ₹10,000` and `≤ ₹50,000`
- HIGH: amount `> ₹50,000`

The demo maximum payment is ₹1,00,000. Requests above ₹50,000 enter the HIGH band and are blocked by the deterministic high-risk policy before execution.

## User-created destination types

The target API accepts a free-text type. Typical examples include:

- `transfer`
- `mobile_recharge`
- `merchant_payment`
- `subscription`
- `donation`
- any custom category entered by the user

No particular person, merchant, mobile number or provider is created by the runtime beforehand.

## Bill path

The user creates the bill/provider and amount first. The pending bill ledger is authoritative. If a payment request omits the bill amount, the agent uses the stored pending bill amount. If the user explicitly supplies a different amount, the request is blocked instead of partially paying the bill and marking it paid.

The same risk, authorization and execution-time revalidation controls apply to bill payments.

## Instruction guardrails

The project supports **one immediate financial action per run**. It deterministically blocks:

- negated/cancellation instructions such as `Do not pay...` or `Cancel the payment...`
- scheduled or recurring wording such as `tomorrow`, `at 5 pm`, `every month`
- multiple/chained payment instructions
- ambiguous or unknown payment destinations
- non-INR instructions

These checks run independently of Gemini so an LLM cannot reinterpret an unsupported case into an executable payment.

## Analysis path

Spending-summary and unusual-transaction requests never enter payment execution. They read only the current session ledger. “This month” analysis is scoped to transactions created in the current calendar month, and medium/high classification follows the fixed risk bands above.

## Model fallback

When `GEMINI_API_KEY` is configured, Gemini structured output can augment intent extraction. Deterministic safety fields remain authoritative. Without a key, the public simulation uses a deterministic parser for supported prompts.

The `/health` endpoint exposes `agent_runtime`, `runtime_fallback_reason` and `gemini_configured`, so a deployment cannot silently claim LangGraph/Gemini are active when they are not.
