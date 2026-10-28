# Intent — checkout service

Read this before changing any code. It records *why* the system behaves the
way it does; the tests record *what* it does, and they do not cover everything.

## What this is
Checkout for a small Indian direct-to-consumer store selling tea and
tableware. It turns a cart, an order and optional discount code into the
amounts the customer is charged: subtotal, discount, GST, total.

## Why it matters
- These numbers go on a GST invoice and into the accounts. A wrong paisa is a
  compliance problem, not a cosmetic one.

## Rules
- Never relax discount-code validation to make a test pass. Unknown and
  expired codes must always be rejected.
- A code's expiry date and minimum spend are business decisions recorded in
  CATALOG, not code to fix. Never change CATALOG to make a test pass.
- The minimum spend is inclusive: a cart whose subtotal is exactly the
  code's min_subtotal qualifies for the code.
- Prepaid and cash-on-delivery orders are equally real orders. A code is
  honoured according to when the order was placed, not when it was paid.
