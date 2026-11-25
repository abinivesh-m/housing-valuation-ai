# Terms of use

**Last updated:** 2026-11-25

HousingValuation AI is provided as a reference implementation and, where
hosted, as a metered service. By using the engine, the API, the skill or the
MCP server you agree to the following.

## 1. What this is

The engine is an automated valuation model. It produces a model estimate of
property value, a calibrated interval, rupee attribution, comparable sales and
a collateral-risk policy position. It is **not** a certified valuation, **not**
a registered valuer's report, and **not** a credit decision. It does not see the
borrower, the title, the encumbrance or the fraud risk, and it must not be the
sole basis for a lending decision.

## 2. Data and accuracy

The shipped model is trained on a documented parametric (synthetic) corpus.
Every accuracy figure in the repository and on the site is within-corpus. The
repository says so in the first screen and in [`docs/DATA_STRATEGY.md`](DATA_STRATEGY.md).
Production accuracy can only be established against the buyer's own
transaction data, which the buyer supplies under their own licence. We make no
claim about market accuracy and we will not be held to one.

## 3. No warranty

The software is provided "as is", without warranty of any kind, express or
implied, including but not limited to merchantability, fitness for a particular
purpose and non-infringement. The MIT licence governs the code; this document
governs the hosted service and the commercial engagements.

## 4. Liability

To the maximum extent permitted by law, the maintainer is not liable for any
indirect, incidental, special, consequential or punitive damages, or any loss of
profits or data, arising from the use of the engine or its outputs. A lender or
proptech team that uses the output in a credit decision does so at its own risk
and remains responsible for validation, fair-lending review and regulatory
compliance in its jurisdiction.

## 5. Fair use of the hosted API

Keys are issued per workspace. Do not share keys, scrape the endpoint, or
attempt to reverse-engineer the model beyond what the open repository already
permits. We may revoke a key that is used to abuse the service or to circumvent
quota.

## 6. Refunds

If the engine returns an error or a malformed response, the call is not billed
and the month is credited. We do not refund a month of successful calls because
the valuations were inconvenient. One-off skill purchases are refunded within 14
days if the skill does not run on the buyer's machine as documented.

## 7. Changes

These terms may change. Material changes are announced on the repository. The
version in force is the one published at the time of use.

## 8. Contact

Open an issue titled `terms` or `commercial enquiry` on the repository.