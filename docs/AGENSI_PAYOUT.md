# Agensi payout setup — for an Indian creator

This document covers the **Agensi marketplace** path only: you sell the
`housing-valuation-india` skill on Agensi, Agensi brings the buyers, and you
receive 70% of each sale. This is a different business model from selling the
product directly via Dodo Payments / Gumroad (see `docs/PAYMENTS.md`).

## What Joeri confirmed (Agensi)

- No IP transfer; non-exclusive listing.
- 70/30 split, Stripe fees covered by Agensi.
- 50 MB upload cap; 24-hour review before listing goes live.
- Creators earn nothing from tool charges (the skill runs on the buyer's
  machine; there are no per-call fees to share).
- Featured placement is demand-based, not paid.
- Indian creators are paid via **Zoneless → USDC on Solana**, not via Stripe
  payouts (Stripe is not available to India).
- Minimum payout: $3.50. Payout delay: 14 days.

## The PayPal question

You asked Joeri whether PayPal payouts are possible for Indian creators. Based
on what Joeri has stated so far, **Agensi routes Indian creators through
Zoneless (USDC on Solana), not PayPal.** PayPal is not mentioned as an option
for India. You should ask Joeri directly to confirm, but plan on the
Zoneless/USDC route.

If Joeri confirms PayPal is not available for India, the practical question
becomes: can you receive USDC on Solana and convert it to INR cheaply? Yes,
but it adds steps (see below).

## What you need to set up (Zoneless → USDC → INR)

### Step 1 — A Solana wallet

You need a wallet that can receive USDC on the Solana network.

- **Phantom** (phantom.app) — browser extension + mobile app. Easiest.
  Create a wallet, back up the seed phrase offline, copy your Solana address.
- **Solflare** (solflare.com) — alternative, also fine.

Your Solana address looks like a long base58 string (e.g.
`7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU`). This is what you give
Zoneless.

### Step 2 — Zoneless account

Zoneless is the payout rail Agensi uses for India.

1. Sign up at https://zoneless.com (or whatever URL Joeri provides).
2. Complete KYC (PAN, Aadhaar, bank details — required for Indian residents).
3. Link your Solana wallet address for USDC payouts.
4. Note the minimum payout threshold and any fees Zoneless charges on top of
   Agensi's.

### Step 3 — Receiving USDC

When Agensi pays out, Zoneless sends USDC (a USD-pegged stablecoin) to your
Solana wallet. This is not rupees yet. The USDC sits in your wallet until you
convert it.

### Step 4 — Converting USDC to INR

You need an exchange or ramp that supports USDC on Solana → INR:

- **CoinDCX** (coindcx.com) — Indian exchange, supports USDC, INR withdrawals
  to Indian bank accounts. KYC required.
- **WazirX** — Indian exchange, supports USDC, INR withdrawals.
- **Binance P2P** — peer-to-peer USDC→INR, but Binance's India status is
  uncertain (regulatory issues). Avoid if possible.
- **Transak / MoonPay** — ramp services, higher fees, simpler UX.

Flow: USDC (Solana) → deposit to exchange → sell USDC for INR → withdraw INR
to your Indian bank account.

### Step 5 — Tax

This is the part that eats the margin. Indian tax treatment of crypto/VDA:

- **30% tax on VDA gains** (Section 115BBH) — USDC is a virtual digital
  asset. Gains are taxed at 30% with no loss offset against other income.
- **1% TDS** (Section 194S) on VDA transfers above ₹10,000/year, deducted by
  the exchange or buyer.
- **GST** on the service income (18% on services) if your turnover crosses
  ₹20 lakh.

On a $29 sale: you receive $20.30 (70%). After 30% VDA tax and 1% TDS on
conversion, you keep roughly $13–14. The compliance overhead (ITR filing,
Schedule VDA) is the same whether you sell 10 units or 1,000.

**Practical implication:** the Agensi skill at $29 is a poor revenue vehicle
for an Indian creator once tax is applied. The real money is the hosted API
and data-onboarding services (Path 2/3 in `docs/COMMERCIAL.md`), which are
paid in fiat via a MoR provider and taxed as normal service income.

## What to ask Joeri (next message)

Send Joeri a follow-up covering:

1. **Payout method for India:** Confirm whether Zoneless/USDC is the only
   route, or whether PayPal bank transfer is available. If PayPal is available,
   what is the minimum payout and delay?
2. **Zoneless onboarding:** Official instructions — signup URL, KYC documents
   needed for Indian residents, and whether the Solana wallet address can be
   changed after setup.
3. **Tax documentation:** Does Agensi provide a 1099 or equivalent for Indian
   creators, or is the creator solely responsible for declaring the income?
4. **Featured placement:** How is demand-based featuring determined? Can a
   creator request it?

## Checklist before listing on Agensi

- [ ] Solana wallet created and seed phrase backed up offline
- [ ] Zoneless account created and KYC submitted
- [ ] Solana address ready to give Zoneless
- [ ] Exchange account (CoinDCX or WazirX) for USDC → INR
- [ ] Joeri's reply on PayPal vs Zoneless received
- [ ] Skill zip uploaded (`skill/dist/housing-valuation-india.zip`, 0.54 MB)
- [ ] Listing copy written (lead with "reference implementation, synthetic
      corpus, bring your own data")
- [ ] Terms accepted (no IP transfer, non-exclusive — already confirmed)

## The two business models, side by side

| | Agensi marketplace | Direct sales (Dodo/Paddle) |
|---|---|---|
| Product | Agent skill (zip) | Hosted API + onboarding + validation |
| Who brings buyers | Agensi | You |
| Fee | 30% to Agensi | ~4–5% MoR fee |
| Payout to India | Zoneless → USDC on Solana | INR to Indian bank |
| Tax | 30% VDA + 1% TDS + GST | GST + income tax (normal) |
| Revenue potential | $0–150/mo (skill is a demo) | $300–2,000/mo (services) |
| Effort to start | Upload zip + wait for review | Set CHECKOUT_URL + send outreach |

The Agensi listing is a distribution channel and a credibility signal, not a
revenue line. The hosted API and data-onboarding services are the revenue line.
Run both in parallel; do not expect the Agensi skill to pay rent.