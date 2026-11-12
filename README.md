# RescueBuy

**An AI procurement assistant for small businesses. PayPal holds the money when the owner approves an order, and charges it only when the owner confirms the delivery.**

Built for the PayPal AI Hackathon with the PayPal sandbox (Orders API v2, authorize then capture), Google Gemini and AG Grid.

**Demo video:** https://youtu.be/JueOCtDYb3Y

> AI proposes, rules validate, the owner approves, PayPal reserves the money, and it is captured only when the owner confirms delivery.

## The problem

Small shops lose money in two ways. They run out of stock before a delivery arrives, or they over-order and tie up cash on the shelf. Owners have no time to watch every item, and most would not let an AI spend their money unsupervised.

RescueBuy does the watching and comparing, and leaves every payment decision with the owner.

## What it does

|Page|What it is for|
|-|-|
|**Overview**|A daily briefing of what needs attention. Each item has a runway bar: the bar is days of stock left, the tick is the fastest delivery.|
|**Reorder review**|Compares suppliers on total cost, delivery time and reliability. Suppliers that break a rule (too late, over budget, not approved) are listed with the reason.|
|**Orders**|Every order moves through four steps: Proposed, Approved, Funds reserved, Delivered and paid. A ledger shows what is reserved at PayPal, what is charged, and the item's stock.|
|**Decision Lab**|Compares four buying strategies against the budget. A stress test lets you delay a supplier, switch one off, or raise demand, and the strategies recalculate.|
|**Analytics**|Budget, spending, excess stock, savings from comparing suppliers, and a ledger of every purchase behind the numbers.|
|**Ask Rescue AI**|Answers questions in plain English from the shop's own data. It is read-only and can never place, approve or pay for an order.|

Every order also stores a **decision record**: who chose the supplier (Gemini, the rules, the owner or a Decision Lab strategy), which suppliers were rejected and why, and the assumptions used.

## How PayPal is used

1. The owner approves an order in RescueBuy.
2. **Pay with PayPal** creates a PayPal order with `intent=AUTHORIZE`. The amount comes from the server, never from the browser.
3. The buyer approves in the PayPal sandbox, and the backend authorizes the order. The money is reserved, not charged.
4. When the owner confirms delivery, the backend captures the authorization.
5. Only if PayPal reports the capture as `COMPLETED` does the app mark the order delivered, add the quantity to stock and record the spending, in one database transaction. A failed capture changes nothing and can be retried.

PayPal tools used: OAuth 2.0 client credentials, Orders API v2 (create and authorize), Payments API v2 (capture), webhook signature verification, and sandbox business and personal accounts.

## How AI is used

Google Gemini (`gemini-2.5-flash` by default, through the `google-genai` SDK):

* **Recommends a supplier** among the ones that already passed the rules, and explains why.
* **Explains the trade-offs** between Decision Lab strategies. Python calculates all the numbers.
* **Routes questions** in Ask Rescue AI to one of ten read-only lookups.
* **Words answers**, behind a guard that rejects any wording with a number the backend did not calculate, or that claims an action was taken.

Every Gemini call has a non-AI fallback, so the app works without a Gemini key.

## Tech stack

|Part|Technology|
|-|-|
|Backend|Python, FastAPI, SQLite|
|Frontend|React, TypeScript, Vite|
|Tables|AG Grid Community 36 (inventory board, stress-test grid, strategy matrix, purchase ledger)|
|Payments|PayPal sandbox, Orders API v2|
|AI|Google Gemini API|
|Tests|pytest, 440 tests, with PayPal and Gemini replaced by fakes|

## Run it locally

**You need:** Python 3.10 or newer, Node.js 20 or newer, a free PayPal developer account and (optionally) a free Gemini API key.

### 1\. PayPal sandbox

1. Log in at https://developer.paypal.com and open **Apps \& Credentials** with **Sandbox** selected.
2. Create a **Merchant** app and copy its Client ID and Secret.
3. Under **Testing Tools > Sandbox Accounts**, use one **Business** and one **Personal** account, both set to **United States**. The app charges in USD, and India-based sandbox accounts rejected USD payments during development.

### 2\. Backend

```bash
cd backend
python -m venv .venv
# Windows: .venv\\Scripts\\activate      Mac/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
```

Copy `.env.example` to `.env`, fill in your keys, then start it:

```bash
python -m uvicorn app.main:app --reload
```

The API runs at http://127.0.0.1:8000. The database `rescuebuy.db` is created with demo data on first start.

### 3\. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 (use `localhost`, not `127.0.0.1`).

### 4\. Try the flow from the video

1. **Overview** names Butter as the most urgent item. Click **Review Butter**.
2. The review recommends a supplier and lists the rejected one with its reason. Click **Create order**.
3. On **Orders**, click **Approve order**, then **Pay with PayPal**, and pay with your sandbox Personal account.
4. Back in the app, the ledger shows the amount reserved and $0.00 charged. Stock is unchanged.
5. Click **Confirm delivery**. The payment is captured and the stock goes up.
6. Try the **Decision Lab** stress test, **Analytics** and **Ask Rescue AI**.

### Run the tests

```bash
cd backend
python -m pytest -q
```

## Honest limits

* **Sandbox and demo data.** Payments run in the PayPal sandbox. The bakery inventory, suppliers, delivery history and earlier spending are sample data, and the app labels them as demo data.
* **Delivery is confirmed by the owner.** The app does not independently verify that goods arrived.
* **Webhooks.** The receiver, with signature verification and duplicate protection, is built and unit-tested, but it has never received a live PayPal event because the demo runs without a public URL. The payment flow does not depend on it.
* **Tests use fakes** for PayPal and Gemini. The sandbox flow was exercised by hand.
* **Estimates, not guarantees.** Days-left figures, the Decision Lab, the stress test and savings are estimates from the usage on record.
* **The AI guard checks numbers, not meaning.** It rejects invented numbers and claimed actions, but cannot tell whether a correct number was attached to the right item.
* **Authorizations expire.** Captures are blocked after 29 days. Re-authorization is not implemented.
* **Single business, no sign-in, USD only.**
* **AG Grid Community only.** AG Studio, AG Charts and Enterprise features are not used.

## AI assistance

Gemini runs inside the product. Claude (Anthropic) was used as a coding assistant during development. The opening animation in the demo video is an AI-generated illustration, and the rest of the video is a live recording of the app.

## Roadmap

Live webhooks on a hosted backend, re-authorization for late deliveries, partial capture for partial deliveries, real supplier data, multiple currencies and user accounts.

## License

MIT. See [LICENSE](LICENSE).

