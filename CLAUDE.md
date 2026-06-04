# CLAUDE.md — Agent Team & Project Context

This file is read automatically at workspace startup. Follow everything here before
taking any action.

---

## Agent Roster

Eight specialized agents are available in this project. Always route work to the right
agent. Never do an agent's job yourself.

| Agent | File | When to use |
|---|---|---|
| `project-manager` | `.conductor/agents/project-manager.md` | Planning, specs, coordination, review against acceptance criteria |
| `database-engineer` | `.conductor/agents/database-engineer.md` | Schema design, migrations, indexes, query performance |
| `security-engineer` | `.conductor/agents/security-engineer.md` | Auth, webhooks, payment flow, PII, OWASP review |
| `software-engineer` | `.conductor/agents/software-engineer.md` | Models, services, controllers, jobs, Square API integration |
| `ui-engineer` | `.conductor/agents/ui-engineer.md` | ERB views, Turbo, Stimulus, Bootstrap, Square Web Payments SDK |
| `ui-designer` | `.conductor/agents/ui-designer.md` | Visual review, brand compliance, component consistency |
| `ux-designer` | `.conductor/agents/ux-designer.md` | Usability review, flow validation, error messaging, accessibility |
| `marketing-agent` | `.conductor/agents/marketing-agent.md` | Campaigns, promotions, copy for Lucky Hare / Night Train / Market |

---

## Sequencing Rules

Agents must run in the correct order. Skipping steps causes rework.

**For any feature with a schema change:**
```
project-manager → database-engineer → security-engineer → software-engineer → ui-engineer → ui-designer + ux-designer
```

**For features with no schema change:**
```
project-manager → security-engineer (if auth/payment/webhook) → software-engineer → ui-engineer → ui-designer + ux-designer
```

**For UI-only changes:**
```
project-manager → ui-engineer → ui-designer + ux-designer
```

**For marketing work:**
```
marketing-agent (standalone — no engineering sequencing required)
```

The `project-manager` always goes first on new tracks. The `database-engineer` always
goes before the `software-engineer` when schema changes are needed. The `security-engineer`
always reviews auth, payment, and webhook code before it merges.

---

## Handoff Protocol

Each agent documents its handoff in `conductor/tracks/{id}/plan.md` before passing
work to the next agent. No agent starts work without reading the handoff note from
the previous one.

If a handoff note is missing, ask the `project-manager` to reconstruct it before
proceeding.

---

## Hard Rules — Every Agent Follows These

**Multi-tenancy:**
- Every tenant-owned table has a `tenant_id` column (NOT NULL, indexed, FK)
- Every query on tenant-owned data is scoped to `current_tenant` — no exceptions
- `tenant_id` never comes from user input — resolved from subdomain/domain only
- Cross-tenant data leakage is a CRITICAL security finding

**Money:**
- All monetary values stored as `_cents` integer columns
- No floats for money. Ever.
- Prices always calculated server-side — never trust client params

**Square:**
- Every write call (CreateOrder, CreatePayment) includes an `idempotency_key`
- Card data is tokenized client-side — the Rails server never sees raw card numbers
- Webhook endpoints verify Square HMAC signatures before processing anything
- Square API keys live in ENV / Rails credentials — never in code, never in `conductor/` files

**Schema:**
- Every foreign key is indexed
- Every `square_catalog_id` column is indexed, with a composite unique index scoped to `tenant_id`
- Migrations are reversible
- No manual schema changes in production

**Testing:**
- Every PR from `software-engineer` includes model specs, service specs, and request specs
- All Square API calls are stubbed with WebMock/VCR in tests
- No feature merges without passing tests and `standardrb`

**UI:**
- Mobile is the primary target — test at 375px first
- Hotwire (Turbo + Stimulus) before any custom JavaScript
- Square Web Payments SDK for all card input — no custom card forms
- All interactive elements are keyboard-navigable

---

## Project Stack

- **Framework:** Rails 7
- **Database:** PostgreSQL (Heroku Postgres in production)
- **Frontend:** Bootstrap 5, Hotwire (Turbo + Stimulus), esbuild
- **Payments:** Square (Web Payments SDK + Orders API + Payments API)
- **Background jobs:** Sidekiq
- **Real-time:** Action Cable (OrderTrackingChannel)
- **Auth:** OmniAuth (Google + Apple), with `omniauth-rails_csrf_protection`
- **Code style:** standardrb

---

## Core Domain Model (Quick Reference)

```
tenants             → restaurants; each owns its own Square account, menu, settings
users               → customers, OmniAuth-authenticated, scoped to tenant
addresses           → delivery addresses, belong to users
categories          → Square-synced, scoped to tenant
menu_items          → Square-synced, base_price_cents, scoped to tenant
item_variations     → sizes with price_cents, Square-synced
modifier_lists      → crusts, sauces, cheeses, toppings groups, Square-synced
modifiers           → individual modifier options with price_cents
menu_item_modifier_lists → join table
carts               → session or user-linked, scoped to tenant
cart_items          → items + variation + quantity
cart_item_modifiers → modifier selections per cart item
orders              → placed orders, square_order_id, fulfillment state, scoped to tenant
order_items         → snapshot at time of order
order_item_modifiers → snapshot at time of order
payments            → Square payment records, scoped to tenant
deals               → coupons and promotions, scoped to tenant
deal_redemptions    → tracks per-user redemptions
```

---

## Price Calculation (Canonical)

```
subtotal_cents  = Σ (variation_price + modifier_prices) × quantity
tax_cents       = subtotal × tenant.tax_rate
discount_cents  = deal value from DealApplicator
delivery_fee    = tenant.delivery_fee_cents (0 if carryout or free-delivery deal)
total_cents     = subtotal - discount + tax + delivery_fee
```

The `software-engineer` owns this logic via `Cart::PriceCalculator`. Nothing else
computes cart totals.

---

## Order Fulfillment States

```
proposed → reserved → prepared → completed
                              ↘ canceled
```

State transitions come from Square webhooks only — never from direct app actions.
Each transition broadcasts a Turbo Stream to `OrderTrackingChannel`.

---

## Square Sync Fields

Every table synced from Square:
- Has a `square_catalog_id` string column (indexed)
- Has a composite unique index: `[:tenant_id, :square_catalog_id]`
- Uses Rails integer/bigint PKs — never Square IDs as primary keys

---

## Marketing Agent — Separate Context

The `marketing-agent` operates independently of the engineering team. It serves
Lucky Hare Gastropub, Night Train Pizza, and Lucky Hare Market in Marble Hill, Georgia.

Activate it for: campaigns, promotions, social posts, email copy, SMS, signage,
happy hour offers, upselling, campaign calendars.

Do NOT use it for: HR letters, legal documents, operational procedures, financial analysis.

The marketing agent follows its own internal rules (Ogilvy + Orwell + 4 Ps framework).
Do not apply engineering sequencing to marketing requests.

---

## When Starting Any New Track

1. Invoke `project-manager` first
2. Confirm the spec exists in `conductor/tracks/{id}/spec.md`
3. Confirm acceptance criteria are specific and testable
4. Follow the sequencing rules above
5. Do not write code until `project-manager` has produced a plan

When in doubt about which agent to use, ask the `project-manager`.
