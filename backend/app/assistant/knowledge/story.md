# How Inventory Sentinel works (the leadership story)

## Stock that vanishes
Retailers lose around 1.5-2% of sales to shrinkage: theft from outside and inside, till fraud, miscounts, deliveries that
arrive short, typing mistakes and stock that is "in the system" but not on the shelf. Most of it is found weeks later, if at
all, by audits that look everywhere. Inventory Sentinel looks at every item in every store every day and points teams at
the few places that look wrong today.

## The data
Data the business already has: daily stock counts (expected from the books versus counted on the shelf), deliveries,
sales, returns, transfers and adjustments, till behaviour (manually keyed items, voided lines, overrides, after-hours
scans), store and category details, and past loss-prevention flags. Sentinel reads it straight from the inventory system
over MCP (a "connector"), keeps a rolling snapshot of the last 120 days, and learns what normal looks like for that
retailer's own stores. The demo connects to a simulated vendor back-office whose data has seven kinds of problem injected
and an answer key kept aside (inside the vendor, never a model input) to mark the homework.

## What "unusual" means
The methods learn what normal looks like from history, with no labels: how big the daily gap between expected and
counted stock usually is for this item, how fast it sells allowing for promotions, how often this store keys items by
hand or voids lines. A day is unusual when several of these move together in a way history rarely shows, for example
stock going missing for a week while the till shows extra voids.

## Four detectives compete
A rule of thumb (how many typical deviations today's shrinkage is from normal for the category) is the baseline. Isolation
Forest, an autoencoder, Local Outlier Factor and an ensemble of Isolation Forest and LOF compete with it. The last 28% of days are held back as an exam; the
answer key says which days really were problems. Average precision decides the winner. Isolation Forest finds far more
real problems than the rule of thumb in the same number of alerts, especially till fraud and internal theft that never
show up as a single big shrinkage day.

## From odd days to incidents
Flagged days for the same item in the same store are grouped into one alert with a severity (medium, high, critical), a
likely type (external theft, internal theft, till fraud, counting error, receiving error, data-entry error, sales pattern
change), the value of stock at risk, plain-language reasons ("7 voided till lines, well above the store's habit") and
P(true anomaly): out of alerts like this one, how many turn out to be real.

## Where it happens
The dashboard shows alerts and value at risk by day, a store x category heatmap, and the top stores, SKUs and warehouse
teams, so regional managers see patterns, not just single alerts.

## Plan the investigators' week
Investigator time is the scarce resource. The planner takes the hours available, the cost of an hour and how much of the
money at risk an investigation usually recovers, ranks alerts by expected recovery per hour, and produces a work list per
warehouse team with the expected return. Book-keeping errors count only a small share because fixing a record does not
bring money back.

## Teams teach the model
Every alert a team closes (confirmed theft, counting error, process issue or false alarm) is remembered. The feedback
recalibrates P(true) and can train a re-ranker that sits on top of the detector. The re-ranker is judged only on days no
one reviewed, so the improvement is honest.

## One engine, many questions
The same four steps (gather what the business already records, learn what normal looks like, flag and explain the unusual,
rank actions by value) answer other questions: customer lifetime value, vendor performance, demand forecasting, returns,
markdown timing, store staffing, influencer matching and loyalty engagement.

## Getting to live
Today: a laptop demo against a simulated vendor, already wired the way it would run live: a nightly schedule syncs the
vendor, scores the new day with the chosen model (or retrains one), and proposes recounts and investigations from the SOPs
into the vendor's own task inbox once someone approves them. Next: point the connector at one region's real system (an MCP
adapter over its stock and till data) with loss-prevention reviewing the alerts. Then: every region, with the model
retrained on a schedule from the teams' closed tasks.
