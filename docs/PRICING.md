# Pricing and revenue model

This is the commercial plan for the engine in this repository. It is written to be argued with,
not to flatter the product. The technical claims behind each tier are in
[`PRODUCT.md`](PRODUCT.md) and [`MODEL_CARD.md`](MODEL_CARD.md).

---

## 1. Who buys, and what they pay for

| Segment | What they are buying | Willingness to pay | Volume |
|---|---|---|---|
| **Agent developers** | A callable skill that prices Indian property without a data account | $29 one-off, or $49/mo | Low per customer, many customers |
| **Proptech and analyst teams** | Batch scoring, comparables, a defensible interval for reports | $199/mo | Moderate, few customers |
| **HFC / NBFC credit teams** | A shadow-mode file review against their own valuers, plus model documentation | $1,500+/mo | Very few customers, high value |
| **Students and researchers** | A reference implementation of a conformal, auditable AVM | $0 — they read the MIT repo | None directly |

The ranking matters. One lender pilot at $1,500/month equals thirty Developer plans. The
self-serve tiers exist to create pipeline and credibility, not to carry the revenue line.

---

## 2. The price ladder

| Plan | Price | Included | Overage |
|---|---|---|---|
| Explore | $0 | 50 valuations, 1 key, calls stop at the cap | not billed |
| Developer | $49/mo | 1,000 valuations, 2 keys, batch, usage endpoint | $0.050/call |
| Team | $199/mo | 5,000 valuations, 5 keys, per-key reporting, priority support | $0.035/call |
| Lender pilot | $1,500/mo | 25,000 valuations, 10 keys, validation report, documentation pack | $0.020/call |
| Agent skill (marketplace) | $29 one-off | Local skill, unlimited calls, no key | — |

Why these numbers:

- **$0.049 per valuation at the Developer cap** sits below a manual desktop review by three orders
  of magnitude and above the marginal compute cost, which is effectively zero. The price is anchored
  to the decision it replaces, not to server cost.
- **The Explore cap is hard, not metered.** A trial that can generate an invoice is a support
  liability. Fifty calls is enough to judge the output and too few to run a business on.
- **Overage is priced at the plan rate, not at a penalty rate.** Cutting a customer off mid-month
  costs more in churn than the overage earns.
- **The skill is priced at $29, not $9.** A price below $20 signals a toy; this is a working engine
  with a lending policy attached.

---

## 3. Revenue math, honestly

Assumptions: 70% net after the marketplace fee where a marketplace is involved; card fees ~3%;
support cost ~15 minutes per customer per month.

| Scenario | Developer | Team | Lender | Gross MRR | Net after fees and support |
|---|---|---|---|---|---|
| **Conservative, month 6** | 4 | 1 | 0 | $395 | ~$250 |
| **Base, month 12** | 15 | 4 | 1 | $3,081 | ~$2,300 |
| **Upside, month 18** | 40 | 12 | 3 | $8,440 | ~$6,400 |

Plus one-off skill sales: 10 sales/month at $29 is $290 gross, roughly $200 net. That is a
distribution channel, not a revenue line.

**The honest ceiling.** With a synthetic corpus, no lender will pay for production decisions. The
self-serve tiers can reach a few thousand dollars a month because developers are buying the system,
not the accuracy. The lender tier only becomes real after phase 1 of the data plan — a registry
transaction feed and a shadow-mode validation on one city and one property type. Until then, treat
lender revenue as $0 in any plan you rely on.

---

## 4. Channels, in order of expected return

1. **One lender conversation, pursued directly.** An HFC or NBFC with a desktop-valuation backlog.
   Offer a free shadow-mode run on 200 closed files. This is the only channel that changes the
   revenue order of magnitude.
2. **The Agensi listing.** Distribution to 20,000 agent users. Low volume for a niche B2B skill, but
   it costs one day and it puts the product in front of developers who already pay for skills.
3. **GitHub and the model card.** The repo is the sales asset: a technical buyer who reads
   `DATA_STRATEGY.md` §4 and §5 will trust the product more than any landing page can make them.
4. **API directories and agent-skill indexes.** Cheap listing, occasional qualified traffic.
5. **LinkedIn, written as engineering, not marketing.** One post per shipped capability, with the
   measured number in it. No launch announcements.

---

## 5. What must be true before the first invoice

| Item | Status | Note |
|---|---|---|
| Metered `/api/v1` with per-key quota | ✅ built | `metering.py`, `tests/test_commercial.py` |
| Agent skill package | ✅ built | `skill/housing-valuation-india/` |
| Pricing page | ✅ built | `/pricing` |
| Quota counter in durable storage | ⬜ | set `UPSTASH_REDIS_REST_URL` and `_TOKEN` on the deployment |
| Checkout | ⬜ | Stripe Payment Link or Lemon Squeezy; paste into `CHECKOUT_URL` in `pricing.html` |
| Contact channel | ⬜ | the CTA currently opens a GitHub issue; replace with a monitored address |
| Terms of service | ⬜ | liability cap, no-credit-decision clause, synthetic-corpus disclosure |
| Refund policy | ⬜ | stated on the pricing page; mirror it in the terms |
| Support inbox and response target | ⬜ | the published SLA is 2 business days on Developer |

Do not take card payments before the terms and the refund policy exist. The synthetic-corpus
disclosure on the pricing page is what keeps a dissatisfied buyer from being a fraud claim.

---

## 6. The three levers, ranked

1. **A real data feed for one city.** Registry deeds plus circle rates for Karnataka alone would move
   the product from "working system" to "sellable to a lender". Everything else is packaging.
2. **A shadow-mode pilot with one HFC.** Even on synthetic data, a side-by-side against human valuers
   on their files produces the only sales asset that matters: a comparison table they commissioned.
3. **Volume in the developer tier.** Useful, compounding, and not sufficient on its own. Price and
   packaging optimise this lever; they do nothing for the first two.

If the goal is revenue rather than a portfolio piece, lever 1 is the only one worth a month of work.
