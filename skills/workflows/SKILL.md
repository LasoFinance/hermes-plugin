---
name: workflows
description: How to connect Laso Finance, fund the agent wallet, and run the common Laso jobs (prepaid cards, gift cards, push-to-card, Venmo/PayPal and bank payouts) with the laso_ tools.
---

# Laso Finance workflows

Laso lets you spend USDC in the real world for your human. Every tool in this plugin starts with `laso_`. When a detail is not covered here (fees, limits, refunds, supported countries), call `laso_search_docs` instead of guessing.

## Connecting

1. Call `laso_announce_connection` with your name and a one-line message.
2. If it returns `"error": "laso_not_connected"`, send your human the `message_for_human` exactly as returned. It holds a link and a short code. Do not open the link yourself.
3. When your human says they approved, call `laso_announce_connection` again. It finishes the sign-in and runs.

If a call later returns `laso_not_connected` again, the key was revoked from the dashboard. Repeat the same steps.

## Funding

Paid tools (their descriptions say PAID ROUTE) pay their USDC price from your agent wallet.

1. Call `laso_get_agent_wallet`. If you have none, call `laso_create_agent_wallet`.
2. If it needs funding, give your human the wallet's Solana address and ask them to send USDC to it.
3. Call `laso_get_agent_wallet` again to confirm the balance before your first paid call.

## Approvals

Tools that move money or hand out a credential ask your human to approve each call in Hermes before they run. Before you call one, say what you are about to do in plain words: the amount, who receives it, and what it is for. If your human declines, do not retry the same call; ask what they want instead.

## Common jobs

**Order a prepaid card.** `laso_order_card` with the amount. Then `laso_get_card_data` for the card details once it is ready. Card data can take a short while to appear; call `laso_refresh_card_data` if it is not ready yet.

**Buy a gift card.** `laso_search_gift_cards` to find the product and its allowed amounts, then `laso_order_gift_card`.

**Send money to a person.**
- To a debit card: `laso_push_to_card`.
- To Venmo or PayPal: `laso_send_payment`, then `laso_get_payment_status`.
- To a bank account: `laso_send_bank_payment`.

Saved recipients live in `laso_list_payment_recipients` and `laso_list_address_book`. Check them before asking your human for details they already gave.

**Withdraw.** `laso_withdraw` returns once the withdrawal is accepted, not when it lands. Follow it with `laso_get_withdrawal_status`.

**Show your human what you did.** `laso_get_auth_link` returns a one-time link to their Laso dashboard.

## Identity checks

Some products need your human to verify their identity. `laso_get_kyc_status` says whether that is needed, and `laso_get_kyc_link` returns the link. Only your human can complete it. Never fill in an identity form for them.
