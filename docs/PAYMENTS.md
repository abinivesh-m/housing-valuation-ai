# Payments setup — for an Indian creator selling globally

Stripe does not pay out to Indian bank accounts without a US entity, so the
recommended routes are **Merchant of Record (MoR)** providers that handle global
tax (GST/VAT/sales tax) and pay you in INR or USD to an Indian bank. Pick one.

## Recommended: Lemon Squeezy (MoR)

Best for digital products and subscriptions. They are the merchant of record,
so they collect and remit VAT/GST worldwide and you receive a payout.

1. Sign up at https://lemonsqueezy.com with your Indian details.
2. Create a **Store** (one per product line).
3. **Products → New product**:
   - "HousingValuation AI — Developer plan" — subscription, $49/month
   - "HousingValuation AI — Team plan" — subscription, $199/month
   - "HousingValuation AI — Validation engagement" — one-off, $1,500
   - "housing-valuation-india skill" — one-off, $29
4. For each product, open **Share → Checkout link** and copy the URL.
5. In Vercel: Project → Settings → Environment Variables → add
   `CHECKOUT_URL` = the Lemon Squeezy checkout URL (or a pricing page you
   control). Redeploy.
6. The pricing page reads `/api/checkout-url` and rewires every CTA to it.
   Until the variable is set, CTAs fall back to a GitHub key request, so the
   page never dead-ends.

**Payouts:** Lemon Squeezy pays to Indian bank accounts in USD; your bank
converts to INR. Expect 5% + 50¢ per transaction. Payouts are weekly with a
$50 minimum.

**Tax:** As an Indian resident selling digital services, you are liable for GST
on the payout you receive (18% on services) and for income tax on the profit.
Keep invoices. Lemon Squeezy provides invoice PDFs per transaction.

## Alternative: Dodo Payments (India-based MoR)

India-headquartered MoR with global coverage and INR payouts. Similar flow:
create products, copy checkout links, set `CHECKOUT_URL`. Worth comparing fees.

## Alternative: Gumroad (simplest, highest fee)

10% + 30¢. Fastest to set up; good for the $29 skill while you validate
demand. Pays to India via PayPal or bank transfer. No subscription support
worth using.

## Alternative: Paddle (MoR, enterprise-grade)

5% + 50¢. Stronger for B2B annual contracts. Longer onboarding.

## What NOT to use (yet)

- **Stripe directly.** Indian individuals cannot receive payouts without a
  supported country. Stripe Atlas (US LLC) is an option later, at the cost of
  US tax filing.
- **Razorpay.** Excellent for INR, but global card acceptance requires RBI
  approval and is a poor fit for a USD-priced SaaS until you have volume.

## Webhooks (when you want automatic key issuance)

When a payment succeeds you want to issue an API key. The current flow is
manual (GitHub issue → you issue a key). To automate:

1. In Lemon Squeezy: Settings → Webhooks → add your Vercel URL
   `https://housing-valuation-ai.vercel.app/api/webhooks/lemonsqueezy`
   with the events `order_created`, `subscription_created`,
   `subscription_payment_success`.
2. Add a route in `app.py` that verifies the webhook signature (HMAC-SHA256
   with your signing secret), reads the product variant, generates a key,
   stores it in Upstash, and emails it to the buyer.
3. Store `LEMONSQUEEZY_WEBHOOK_SECRET` and `LEMONSQUEEZY_API_KEY` in Vercel
   env vars.

This is the step that turns the product from "you manually email keys" into
"money in, key out, no human." It is roughly one afternoon of work once the
payment provider is live.

## Environment variables (Vercel)

| Variable | Purpose |
|---|---|
| `CHECKOUT_URL` | The single checkout link the pricing page uses |
| `HVA_API_KEYS` | `key:plan:quota,...` issued to paying customers |
| `UPSTASH_REDIS_REST_URL` | Per-key monthly counters |
| `UPSTASH_REDIS_REST_TOKEN` | Upstash auth |
| `LEMONSQUEEZY_WEBHOOK_SECRET` | Webhook verification (when automating) |
| `LEMONSQUEEZY_API_KEY` | Issue keys / look up orders |

## Checklist before taking money

- [ ] Terms page live (`/terms`) — done
- [ ] Refund policy stated — done in terms + pricing FAQ
- [ ] Privacy note on what you store (API key + counter only) — add to terms
- [ ] GST registration if your Indian turnover crosses ₹20 lakh
- [ ] A monitored email address (not a GitHub issue) for support
- [ ] Webhook signature verification before issuing keys