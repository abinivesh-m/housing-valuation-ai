# Commercial engagement

The code in this repository is MIT-licensed and will stay that way. The reason is
that a secret you cannot inspect is not a product a lender will buy, and a
secret you cannot audit is not a product a regulator will accept. The MIT
licence is a feature, not a bug.

What that means for revenue is that the paid artifact is **not the code**. It is
one of four things, in increasing order of value:

## 1. Hosted metered access (self-serve)

The `/api/v1` surface is key-authenticated and counted per key per calendar
month, with Upstash Redis counters and constant-time key comparison. Tiers and
overage are in [`PRICING.md`](PRICING.md). This is the lowest-value product and
it exists to create pipeline, not to carry a revenue line.

## 2. Data onboarding (one-off, $199–$999)

A buyer brings their own transaction file and we run `ingest.py` against it,
produce the JSON report, retrain with `train.py --data`, and hand over the
artifacts plus a before/after accuracy table. The engine code does not change;
only the numbers do. This is the service that converts a reference
implementation into a usable system, and it is the single most defensible
revenue line because it requires the buyer's data, which we never see again.

## 3. Shadow-mode validation (monthly, $1,500+)

Run the engine against a lender's closed files in shadow mode and produce a
comparison table: model value vs physical valuer vs registered sale price,
broken down by price band, locality and property type. This is the artifact a
credit-risk committee actually signs off on, and it is the only thing that
justifies a production deployment. Terms: the lender owns the file, we own the
method, results are shared only with the lender.

## 4. Support and indemnity (annual)

A commercial support agreement covering: SLA on the hosted endpoint, a named
contact, an annual re-calibration against a refreshed data feed, and a
liability cap written into the contract. This is what an HFC or NBFC procurement
team needs before they can put a vendor on the approved list. It is not a
licence fee for the code — it is a fee for someone to answer the phone and sign
the paper.

## What we will not do

- We will not relicence the existing code or sell exclusive rights to it.
- We will not claim production accuracy on synthetic data.
- We will not make a credit decision or provide a certified valuation. The
  engine evaluates collateral risk only; the lender is the decision-maker and
  owns fair-lending review.
- We will not scrape or redistribute transaction data. The buyer brings their
  own, under their own licence.

## Contact

Open an issue titled `commercial enquiry` on the repository, or email the
maintainer. Lender pilots include a validation report on the lender's own files.