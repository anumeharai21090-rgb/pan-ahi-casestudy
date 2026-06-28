# Appendix — Technical Terms Explained

---

## Markdown

Markdown is a simple way of writing formatted documents using plain text. Instead of clicking bold/italic buttons like in Microsoft Word, you type symbols:
- `#` creates a heading
- `**text**` makes text bold
- `|` creates a table
- ``` ` ``` creates code formatting

GitHub automatically converts Markdown into a nicely formatted webpage. The product spec (`AHI_Spec.md`) is a Markdown file — the `.md` extension stands for Markdown. When you open it on GitHub it renders as a professional document with headings, tables, and code blocks.

Why Markdown for the spec? Because it lives in a GitHub repository alongside the code, it can be versioned (every change is tracked), and any engineer or PM can read and edit it without needing Word or Google Docs.

---

## Python

Python is a programming language — a way of giving instructions to a computer. It's one of the most widely used languages for data work because it's readable and has a large ecosystem of libraries (pre-built tools) for data manipulation, statistics, and machine learning.

In this project Python was used to generate the synthetic dataset. The script runs once and produces five CSV files that become the source tables in BigQuery.

---

## Pandas

Pandas is a Python library for working with data tables. Think of it like Excel but in code — you can create rows and columns, filter data, calculate totals, merge tables, and export to CSV. 

In this project Pandas created and organized the five synthetic tables, applied the edge case logic (planting shelfware accounts, spike-and-drop patterns, etc.), and exported everything as CSV files ready for BigQuery upload.

---

## Faker

Faker is a Python library that generates realistic fake data. Instead of naming 1,000 fake companies "Company1, Company2, Company3..." Faker generates real-sounding names like "Marks, Miller and Griffin" or "Tran Inc." It can generate names, company names, addresses, dates — anything that needs to look authentic without using real customer information.

In this project Faker generated the company names in the Accounts table, making the synthetic data feel like real PAN customer records.

---

## NumPy

NumPy (Numerical Python) is a Python library for mathematical calculations. It handles things like random number generation, statistical distributions, and mathematical operations very efficiently.

In this project NumPy generated realistic consumption numbers — ensuring daily usage figures followed plausible distributions rather than being completely random. It also applied the mathematical patterns for spike-and-drop accounts (high month one, near-zero after) and consistent overages (consistently above 120% of committed credits).

---

## SQL

SQL (Structured Query Language) is the language used to talk to databases. It lets you ask questions of a database — "give me all accounts where AHI is below 50" — and perform calculations across millions of rows instantly.

In this project SQL was used for two things: the six data quality tests that check the raw data before the pipeline runs, and the six-step pipeline that calculates AHI scores from the source tables.

---

## BigQuery

BigQuery is Google's cloud database — a database that lives on Google's servers rather than on your laptop. It's built specifically for analytical queries — summing, averaging, and grouping millions of rows very quickly.

In this project BigQuery stores all five source tables and the two output tables (account_ahi_monthly and csm_ahi_monthly). The dashboard queries BigQuery live every time it loads.

The "Sandbox" tier is BigQuery's free version — no credit card required, full SQL functionality, with some limitations (no data deletion, 10GB storage limit).

---

## Node.js

Node.js is a technology that lets you run JavaScript code outside of a browser — directly on your computer. JavaScript is normally the language that makes webpages interactive in Chrome. Node.js takes that same language and lets you use it to build server-side applications.

In this project Node.js runs the proxy server (`server.js`) on your Mac. When you type `node server.js` in Terminal, Node.js reads and executes that file, starting the authentication proxy on port 3001.

---

## Express

Express is a Node.js framework — a pre-built toolkit that makes it easy to build a web server. Without Express you'd have to write a lot of repetitive code to handle incoming requests. Express handles the plumbing so you can focus on the logic.

In this project Express powers the proxy server — it defines the three API endpoints (`/api/portfolio`, `/api/csm`, `/api/accounts`) and handles the routing of requests from the dashboard to BigQuery.

---

## API

API (Application Programming Interface) is a way for two pieces of software to talk to each other. Think of it like a waiter at a restaurant — you (the dashboard) tell the waiter (the API) what you want, the waiter goes to the kitchen (BigQuery), and brings back your order (the data).

In this project the proxy server exposes three API endpoints:
- `/api/portfolio` — returns portfolio-level health summary
- `/api/csm` — returns CSM leaderboard data
- `/api/accounts` — returns account-level detail

The dashboard calls these three endpoints when it loads, gets the data back, and displays it on screen.

---

## Service Account

A service account is a Google identity for software rather than a person. When a program needs to access Google services (like BigQuery), it uses a service account instead of a personal email and password. 

The service account comes with a JSON key file — a text file containing a private cryptographic key that proves the program is authorized to access the resource. This is what the `credentials.json` file is — the proxy server reads it to authenticate with BigQuery.

Important: this file must never be committed to GitHub or shared publicly. If someone else gets this file, they can access your BigQuery data. That's why a fresh key had to be created after the earlier incident.

---

## GitHub

GitHub is a website where developers store and share code. Think of it like Google Drive but specifically for code, with two key differences:

1. **Version history** — every change to every file is tracked. You can see exactly what changed, when, and why.
2. **Collaboration** — multiple people can work on the same codebase, and GitHub manages merging their changes together.

In this project GitHub is used purely as a code repository — a place to store and share all the files built for the case study. PAN opens the link and can browse every file without needing to run anything.

---

## Port 3001

A port is like a door on your computer that software can use to send and receive information. Your computer has thousands of ports — each one can be used by a different program.

Port 3001 is the door the proxy server opens when it starts. When the dashboard wants data, it knocks on `http://localhost:3001` — `localhost` means "this same computer" and `3001` is the door number. The proxy answers, goes to BigQuery, and returns the data through the same door.

---

## Linear Regression

Linear regression is a statistical technique that finds the best straight line through a set of data points. If you plot monthly usage over 12 months on a graph, linear regression draws the line that best fits all those points. The slope of that line tells you whether usage is trending up (positive slope) or down (negative slope).

In this project linear regression is used in Step 3 of the SQL pipeline to calculate the Engagement Trend score for each account. A steep positive slope = score of 100 (strong growth). A steep negative slope = score of 0 (steep decline).

---

## Isolation Forest

Isolation Forest is an unsupervised machine learning algorithm for anomaly detection. "Unsupervised" means it learns what normal looks like from the data itself — you don't have to label which accounts are anomalous in advance. "Isolation Forest" refers to how it works: it randomly splits the data and measures how quickly each data point gets isolated. Anomalous points get isolated faster because they're different from the rest.

In this project Isolation Forest is used to detect spike-and-drop accounts — accounts with unusual usage patterns that shouldn't be treated the same as gradually declining accounts. Flagged accounts have their Engagement Trend score multiplied by 0.5.

---

## ARR-Weighted Average

A weighted average gives some items more influence over the result than others. ARR-weighted means accounts with larger Annual Recurring Revenue have more influence on the CSM's AHI score than small accounts.

For example: if a CSM has 20 accounts and one of them is a $10M account scoring 20 (Churning), that one account pulls the CSM's overall score down much more than twenty $100K accounts all scoring 80 (Healthy). This reflects business reality — losing a $10M account matters more than losing twenty $100K accounts.

---

*This appendix is a reference document — not for presentation, but for personal understanding and interview preparation.*

---

# Appendix — Trade-off Defenses

*Memorize these. The panel will ask.*

---

## "Why a weighted composite instead of an ML churn prediction model?"

Two reasons. First, I had no labeled training data — I couldn't tell the model which accounts had churned because I was working with synthetic data. You can't train a supervised model without ground truth. Second, and more importantly, comp is attached to this metric. A CSM cannot appeal a 73% churn probability. They need to be able to look at five dimension scores and say 'my Deployment score is low because I haven't finished the onboarding — here's what I'm doing about it.' Explainability is a product requirement, not a nice-to-have.

---

## "Why BigQuery instead of Postgres or Snowflake?"

This is an analytical workload — monthly aggregations across 214,000 rows, joining five tables. Postgres is built for transactional workloads, not analytical ones. Snowflake would have been an equally good choice technically, but BigQuery has a free Sandbox tier with no time limit and no credit card required. For a case study prototype, that's the right call. In production I'd evaluate Snowflake seriously, especially if PAN is already using it.

---

## "Why HTML + Node.js instead of Streamlit or React?"

The brief said the audience is executive — VP CS level. Streamlit is a data science tool. It looks like a notebook. The UI is limited, you can't control the layout, and it signals 'prototype' not 'product.' An executive-facing tool needs to feel like a product. HTML + Chart.js gave me full UX control. The Node.js proxy gave me a clean, secure way to authenticate with BigQuery without exposing credentials in the browser. React would have been equally valid — the architecture is identical, only the rendering layer changes. That's a half-day migration if the team has a React standard.

---

## "Why linear regression for engagement trend instead of ARIMA or Prophet?"

ARIMA and Prophet answer 'what comes next?' — they forecast future values. That's not what I needed. I needed 'which direction is this account moving?' — a signal, not a forecast. Linear regression gives me a slope. Positive slope means growing. Negative means declining. Steep negative means trouble. It's the simplest model for the question being asked, and simplicity matters when the output feeds into a compensation metric that CSMs will scrutinize and push back on.

---

## "Why Isolation Forest instead of a rules-based anomaly detector?"

Rules require manual calibration. I'd have to say 'spike-and-drop is when month one consumption exceeds X% and month two drops below Y%.' But what's X? What's Y? Does it vary by segment? By industry? By contract size? You'd need a data scientist to tune those thresholds for every cohort. Isolation Forest learns the normal distribution from the data itself and flags what doesn't fit. Contamination set at 5% because that's the prevalence of spike-and-drop accounts I seeded. In production, that parameter would be tuned against real data.

---

## "Why business-logic weights instead of statistically derived weights?"

I had no labeled dataset to derive weights from. To derive weights statistically I'd need historical renewal outcomes correlated with dimension scores — that data doesn't exist yet for this metric. So v1 weights are PM hypotheses grounded in business logic: consumption and deployment together at 50% because a product that isn't deployed and isn't consumed can't drive renewal. The 90-day shadow period produces the labeled dataset — actual renewal outcomes against AHI scores. v2 runs logistic regression on that dataset and recalibrates weights based on which dimensions actually predicted churn.

---

## "Why a 90-day shadow period before attaching comp?"

Two reasons. First, you want to catch gaming early. If CSMs figure out they can inflate their Deployment score by logging a fake usage event, you want to know that before their bonus depends on it — not after. Second, v1 weights are hypotheses. If the shadow period shows Engagement Trend is the strongest predictor of churn and Stability barely matters, I want to recalibrate before someone loses money over a wrong weight. The shadow period is the responsible path from prototype to production.

---

## "Why a 0.5× multiplier for anomaly flagged accounts instead of zeroing out the trend score?"

Zeroing it out loses the directional signal. An account that spiked in month one and has been declining since is different from an account that spiked in month one and has been flat since. Both are anomalies, but one is recovering and one isn't. The 0.5× multiplier says 'we know this account is unusual, so we're applying a penalty, but we're not treating all anomalies as identical.' It preserves the information while flagging the concern.

---

## "Why the Healthy threshold at 80 specifically?"

It's not an arbitrary round number. PAN's Q4 FY2025 and Q2 FY2026 earnings calls report that platform customers — accounts that have deployed multiple products and consume consistently — retain at 120% NRR with low single-digit churn. An account scoring 80+ on AHI exhibits that behavioral profile: deployed, consuming, stable, growing. The 80 threshold is calibrated to that profile. During the shadow period we'll validate whether the empirical breakpoint between renewing and churning accounts actually falls at 80, or whether it needs to shift.

---

## "Why monthly cadence instead of weekly?"

Monthly matches the contract structure — customers commit to monthly compute credits. Daily or weekly AHI would be noisy — a bad week doesn't mean a churning account. Monthly smooths out short-term spikes and gives a signal that's meaningful at the CSM cadence — most CSMs have monthly check-ins with accounts. That said, v2 should calculate weekly for Enterprise accounts above a certain ARR threshold, because for a $10M account you want earlier warning than 30 days.

---

## "Why ARR-weighted rollup to CSM level instead of a simple average?"

A simple average treats a $100K account the same as a $10M account. If a CSM has one $10M account scoring 20 and twenty $100K accounts all scoring 90, a simple average gives them an 85 — healthy. But $10M of ARR is at imminent risk. ARR-weighting surfaces that. It also aligns CSM comp with business value — the metric they're managed to should reflect the revenue impact of their decisions, not just the count of accounts.

---

## Three Business KPIs to Memorize

Say these out loud during Slide 9:

1. **Renewal rate** — 15 percentage point improvement in At Risk account renewal rate within 12 months
2. **Time to intervention** — average days to CSM action after At Risk flag, target under 14 days
3. **CSM adoption** — 70%+ of CSMs logging AHI-triggered action per week within 60 days of launch

---

## Retrospective — What I'd Do Differently

Frame this explicitly as "if I did this again with today's tech stack":

- Start with the LLM narrative layer from day one instead of adding it in v2 — it drives CSM behavior change and that feedback data is what you need earliest
- Use dbt for the SQL pipeline — lineage, documentation, and testability out of the box instead of raw SQL steps
- Instrument CSM actions from week one — acted/dismissed/escalated logged against every AHI signal — so by the end of the shadow period you have a labeled dataset for v2 weight calibration
- Involve a CS leader as co-designer from week one, not reviewer at the end — they would have caught the Platform Stability proxy problem before it became a v2 item
- Build the agentic trigger layer in parallel with v1, not after — the value of AHI is highest when CSMs don't have to check a dashboard to know something needs attention

