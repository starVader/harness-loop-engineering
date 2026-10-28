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
<!-- Intentionally empty: the stage 6 run without written rules. -->
