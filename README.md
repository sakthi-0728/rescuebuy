\# RescueBuy



\*\*An AI assistant that reorders stock for small businesses, but only pays when the goods actually arrive.\*\*



Built for the PayPal AI Hackathon with the PayPal sandbox (Orders API: authorize, then capture) and Google Gemini.



Demo video: \_add YouTube link here\_



\## The idea



Small shops run out of stock because nobody has time to watch every item. RescueBuy watches inventory, predicts when something will run out, compares suppliers, and proposes an order. The owner approves it, PayPal reserves the money, and the money is only taken when delivery is confirmed. Stock goes up at delivery, not at payment.



\*\*AI proposes, rules validate, human approves, PayPal pays.\*\*



\## How it works



1\. \*\*Watch stock.\*\* Days left = (stock + incoming) / daily usage, with a risk badge (ok, warning, critical).

2\. \*\*Build options.\*\* Each supplier that is approved, arrives before stock runs out, can fill the order, and passes the budget rules becomes an option with its own quantity and total cost.

3\. \*\*Gemini chooses.\*\* Gemini picks one option and explains the trade-offs. Code checks the pick is on the list of valid options. If Gemini is unavailable or picks something invalid, the app falls back to the lowest total cost.

4\. \*\*Owner approves.\*\* Orders above the auto-approve limit need the owner's approval. Orders above the budget are blocked.

5\. \*\*PayPal reserves the money.\*\* The order is created with `intent=AUTHORIZE`. The buyer approves it in the PayPal sandbox, and the app authorizes it. Funds are held, not charged.

6\. \*\*Delivery is confirmed.\*\* Only then does the app capture the payment and add the quantity to stock.



\### Where the AI is, and where it is not



All numbers (days left, reorder quantity, totals, rule checks) come from plain, tested Python. Gemini only chooses among options that already passed the rules and explains the result. It cannot change a number or pick a supplier that breaks a rule.



\### PayPal safety details



\- Authorize now, capture later, so money moves only after delivery.

\- Idempotency keys (`PayPal-Request-Id`) on create, authorize and capture, so retries are safe.

\- Authorization expiry handling: the honor period and validity window are the constants `HONOR\_DAYS` and `VALID\_DAYS` in `backend/app/orders.py`. An expired authorization is blocked before PayPal is called, and an old one shows a clear warning if the capture fails.

\- A failed capture leaves the order `AUTHORIZED` and the stock unchanged, so it can be retried.

\- Each order keeps its own timeline (created, approved, payment started, authorized, delivered, stock updated).



\## Tech stack



| Part | Technology |

|---|---|

| Backend | Python, FastAPI |

| Dashboard | React, TypeScript (Vite) |

| Payments | PayPal sandbox (Orders API, authorize and capture) |

| AI | Google Gemini API |

| Tests | pytest (131 tests; PayPal and Gemini are mocked) |



\## Run it locally



\*\*You need:\*\* Python 3.10 or newer, Node.js 20 or newer, a free PayPal developer account, and a free Gemini API key. Developed and tested on Python 3.15 and Node 24 on Windows.



\### 1. PayPal sandbox setup



1\. Log in at https://developer.paypal.com and open \*\*Apps \& Credentials\*\* with the \*\*Sandbox\*\* toggle on.

2\. Create an app of type \*\*Merchant\*\* and copy its Client ID and Secret.

3\. In \*\*Testing Tools > Sandbox Accounts\*\*, use a \*\*Business\*\* and a \*\*Personal\*\* account. Make both \*\*United States\*\* accounts. We hit a "seller doesn't accept payments in your currency" error with India-based sandbox accounts.



\### 2. Backend



```bash

cd backend

python -m venv .venv

\# Windows: .venv\\Scripts\\activate      Mac/Linux: source .venv/bin/activate

python -m pip install -r requirements.txt

```



Copy `.env.example` to `.env` and fill in your values:



```

PAYPAL\_CLIENT\_ID=your\_sandbox\_client\_id

PAYPAL\_CLIENT\_SECRET=your\_sandbox\_secret

PAYPAL\_BASE\_URL=https://api-m.sandbox.paypal.com

GEMINI\_API\_KEY=your\_gemini\_api\_key

GEMINI\_MODEL=gemini-2.5-flash

```



`GEMINI\_MODEL` is configurable because model names change. If you get a "not found" error, set a current model name from https://aistudio.google.com.



Start the API:



```bash

python -m uvicorn app.main:app --reload

```



The API runs at http://127.0.0.1:8000 (interactive docs at `/docs`).



\### 3. Dashboard



In a second terminal:



```bash

cd frontend

npm install

npm run dev

```



Open http://localhost:5173 (use `localhost`, not `127.0.0.1`; the backend only allows that origin).



\### 4. Try the demo flow



1\. Click \*\*Get recommendation\*\* on \*\*boxes\*\*. Gemini compares the suppliers and picks one.

2\. Click \*\*Create order\*\* on a supplier, then \*\*Approve\*\*.

3\. Click \*\*Pay with PayPal\*\* and log in with your sandbox \*\*Personal\*\* account. Click \*\*Pay Now\*\*.

4\. Back on the dashboard, boxes still show \*\*600\*\*. The money is reserved, nothing has arrived.

5\. Click \*\*Confirm delivery\*\*. The payment is captured and boxes go to \*\*1000\*\*.

6\. Click \*\*Timeline\*\* to see the order history.

7\. \*\*Reset demo\*\* clears orders and restores stock so you can run it again.



Orders and stock are held in memory and reset when the backend restarts. Don't save a backend file while demoing, because `--reload` restarts the server.



\### Run the tests



```bash

cd backend

python -m pytest -v

```



No API keys are needed. PayPal and Gemini are replaced with fakes in the tests.



\### Without a Gemini key



The app still works. It falls back to the lowest total cost and a plain-sentence explanation, and the dashboard labels this "AI unavailable". PayPal credentials are required for the payment steps.



\## Project layout



```

backend/app/

&#x20; forecast.py    days left, risk level, reorder quantity

&#x20; suppliers.py   supplier eligibility

&#x20; policy.py      budget and approval rules

&#x20; compare.py     options, AI choice with fallback

&#x20; ai.py          Gemini: choose supplier, explain

&#x20; orders.py      order state machine, timeline, expiry

&#x20; paypal.py      PayPal client (token, create, authorize, capture, webhook check)

&#x20; main.py        FastAPI routes

backend/tests/   pytest suite

frontend/        React + TypeScript dashboard

```



\## Scope and roadmap



Left out on purpose to keep the first version finishable:



\- \*\*Webhooks:\*\* the receiver, signature verification and duplicate protection are implemented and unit-tested with a fake PayPal, but it has not received a real PayPal event, because that needs a public URL. The payment flow does not depend on it.

\- \*\*Payouts and Invoicing APIs:\*\* RescueBuy pays through checkout, so it does not need them yet.

\- Real POS integrations, multiple payment providers, a database (storage is in memory), ML demand forecasting, and unattended supplier payments.

\- Next ideas: read a delivery note photo with Gemini and capture only the quantity that arrived.



\## License



MIT. See \[LICENSE](LICENSE).

