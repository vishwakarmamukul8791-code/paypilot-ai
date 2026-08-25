# PayPilot testing fixes 01

This is a targeted overlay patch for the current PayPilot AI project.

## Included fixes

1. High-risk test path is now reachable
   - Maximum configurable daily account limit: ₹2,00,000
   - Demo per-payment maximum: ₹1,00,000
   - Existing risk bands remain:
     - LOW: <= ₹10,000
     - MEDIUM: > ₹10,000 and <= ₹50,000
     - HIGH: > ₹50,000
   - HIGH requests remain blocked by the deterministic risk policy (score 90 >= block threshold 80).

2. Duplicate saved payment references
   - A second payee cannot reuse the same reference for the same payment type.
   - Checks are case-insensitive.
   - Edit operations cannot take another payee's reference.
   - Fresh databases also receive a database uniqueness constraint.
   - Existing databases still receive application-level protection even though SQLAlchemy create_all does not retrofit constraints.

3. Dashboard quick-action payee
   - "Send money" now prefers the destination from the most recent DEBIT transaction instead of beneficiaries[0].
   - Transaction ordering now uses created_at DESC, id DESC for deterministic tie-breaking.

4. Tests
   - New coverage for high daily limits and duplicate payee references.

## Existing duplicate rows

If your current local database already contains:
Rahul -> same UPI/reference
aa    -> same UPI/reference

the patch will not silently delete either row. Remove one duplicate in the UI (or reset the demo session), then future duplicate creation/edit attempts will be blocked.

## Validation in build environment

- Focused agent + multi-account tests: passed.
- Full dependency-independent suite: passed.
- The only two full-suite failures in the build sandbox are environment-only runtime dependency checks because langgraph and google-genai are not installed there.
