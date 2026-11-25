# Payments setup — for an Indian creator selling globally

> **Update (Nov 2026):** Lemon Squeezy has closed new sign-ups and will stop
> processing payments on March 31, 2027. Its successor is Stripe Managed
> Payments, which is not available in every country. For an Indian seller this
> guide now leads with the providers that actually pay out to India.

The core requirement is a **Merchant of Record (MoR)**: a provider that is the
legal seller, collects and remits global VAT/GST/sales tax, and pays you in
INR or USD to an Indian bank. Do not try to be your own MoR — global tax
compliance is a full-time job.

## Recommended: Dodo Payments (India-based MoR)

India-headquartered, built for exactly this case. Global coverage, INR
payouts, and an API that is simpler than Stripe's.

1. Sign up at https://dodopayments.com.
2. Create a business, complete KYC (PAN, GST if applicable, bank details).
3. **Products → New product** for each tier:
   - "HousingValuation AI — Developer plan" — subscription, $49/month
   - "HousingValuation AI — Team plan" — subscription, $199/month
   - "HousingValuation AI — Validation engagement" — one-off, $1,500
   - "housing-valuation-india skill" — one-off, $29
4. Copy each product's **checkout link**.
5. Vercel → Settings → Environment Variables → set `CHECKOUT_URL` to the link
   (or to a pricing page you control). Redeploy.
6. The pricing page reads `/api/checkout-url` and rewires every CTA to it.
   Until the variable is set, CTAs fall back to a GitHub key request.

**Payouts:** INR to your Indian bank. Fees ~4% + per transaction (check
current pricing). Weekly payouts, low minimum.

**Tax:** Dodo is the MoR, so global tax is handled. You owe Indian GST on the
payout you receive (18% on services) and income tax on profit. Keep invoices.

## Alternative: Paddle (MoR, global, pays out to India)

5% + 50¢. Stronger for B2B annual contracts. Longer onboarding (business
review). Same flow: create products, copy checkout links, set `CHECKOUT_URL`.

## Alternative: Gumroad (simplest, highest fee)

10% + 30¢. Fastest to set up; good for the $29 skill while you validate
demand. Pays to India via PayPal or bank transfer. No real subscription
support worth using for a SaaS.

## Alternative: Stripe Atlas → Stripe Managed Payments

Only if you have meaningful volume and want Stripe's infrastructure:

1. Incorporate a US LLC via Stripe Atlas (~$500, includes registered agent).
2. Open a Stripe account on that entity.
3. Use Stripe Managed Payments (the Lemon Squeezy successor) as MoR.
4. Pay US federal/state tax filing annually. Worth it above ~$5k/month.

## What NOT to use (yet)

- **Stripe directly.** Indian individuals cannot receive payouts without a
  supported country.
- **Razorpay.** Excellent for INR, but global card acceptance requires RBI
  approval and is a poor fit for a USD-priced SaaS until you have volume.
- **Lemon Squeezy.** Closed to new sign-ups; shutting down March 31, 2027.

## Webhooks (when you want automatic key issuance)

When a payment succeeds you want to issue an API key. The current flow is
manual (GitHub issue → you issue a key). To automate:

1. In Dodo/Paddle: Settings → Webhooks → add
   `https://housing-valuation-ai.vercel.app/api/webhooks/dodo`
   with `payment.succeeded` / `subscription.activated`.
2. Add a route in `app.py` that verifies the webhook signature (HMAC), reads
   the product, generates a key, stores it in Upstash, and emails it.
3. Store `DODO_WEBHOOK_SECRET` and `DODO_API_KEY` in Vercel env vars.

This is the step that turns "you manually email keys" into "money in, key
out, no human." Roughly one afternoon once the provider is live.

## Environment variables (Vercel)

| Variable | Purpose |
|---|---|
| `CHECKOUT_URL` | The single checkout link the pricing page uses |
| `HVA_API_KEYS` | `key:plan:quota,...` issued to paying customers |
| `UPSTASH_REDIS_REST_URL` | Per-key monthly counters |
| `UPSTASH_REDIS_REST_TOKEN` | Upstash auth |
| `DODO_WEBHOOK_SECRET` | Webhook verification (when automating) |
| `DODO_API_KEY` | Issue keys / look up orders |

## Checklist before taking money

- [ ] Terms page live (`/terms`) — done
- [ ] Refund policy stated — done in terms + pricing FAQ
- [ ] Privacy note on what you store (API key + counter only) — add to terms
- [ ] GST registration if your Indian turnover crosses ₹20 lakh
- [ ] A monitored email address (not a GitHub issue) for support
- [ ] Webhook signature verification before issuing keys