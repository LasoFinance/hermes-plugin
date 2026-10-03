# Laso Finance for Hermes Agent

Give your [Hermes](https://hermes-agent.nousresearch.com) agent a way to spend USDC in the real world: prepaid cards, gift cards, push-to-card, Venmo and PayPal payouts, and bank payments.

The plugin adds the Laso tools to Hermes, each named with a `laso_` prefix. They are the same tools as the [Laso MCP server](https://docs.laso.finance/guides/mcp-server) and forward to it with your API key.

## Install

1. Create an API key in the [Laso agent dashboard](https://laso.finance/agent/dashboard). It starts with `lasoak_`.
2. Install and enable the plugin. Hermes asks for the key and saves it as `LASO_API_KEY`.

   ```bash
   hermes plugins install LasoFinance/hermes-plugin --enable
   ```

3. Start a new session. Your agent's first call is `laso_announce_connection`, which confirms the connection on your dashboard.

In Hermes Desktop, open this link instead: `hermes://plugin/install?repo=LasoFinance/hermes-plugin&enable=1`.

## Paid tools

Tools marked PAID ROUTE settle their price in USDC from your agent wallet. Before the first paid call, have your agent run `laso_get_agent_wallet` (or `laso_create_agent_wallet`) and fund the wallet's Solana address with USDC.

## Updating

Tools follow the Laso API. When new tools ship, update with:

```bash
hermes plugins update laso-finance
```

## More

- Docs: https://docs.laso.finance
- API contract: https://laso.finance/openapi.json
- Agent skill: https://laso.finance/SKILL.md

This repository is published from the Laso monorepo. Open issues here and we will pick them up.
