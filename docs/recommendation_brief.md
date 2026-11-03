# Which Melbourne areas should be looked at first for rental affordability?

This is a short write-up of what I would recommend based on my analysis. It's a personal project using public data (rent to Sep 2025, 2021 Census income, 110 rent areas), and nobody has used it to make a decision. I wrote it as if I was advising a community organisation that supports renters and has to decide which areas to focus on first. This is an imagined audience, not a real client.

## My recommendation

I would look at these eight areas first. In each one, rent has grown by at least the average over the last 5 years (35.2%), and rent is also at least the average share of household income (31.8%). I left out areas with a lot of students, because their incomes look low for reasons that have nothing to do with rent (more on that below).

| Area | Region | Median weekly rent | 5-year rent growth | Rent as % of household income |
|---|---|---|---|---|
| Hastings-Flinders | Mornington Peninsula | $580 | 45.0% | 45.1% |
| Dromana-Portsea | Mornington Peninsula | $595 | 50.6% | 41.7% |
| Dandenong | South Eastern Melbourne | $520 | 48.6% | 41.0% |
| Springvale | South Eastern Melbourne | $570 | 42.5% | 40.7% |
| Frankston | Mornington Peninsula | $550 | 48.6% | 39.7% |
| Cranbourne | South Eastern Melbourne | $580 | 48.7% | 39.3% |
| Thomastown-Lalor | North Eastern Melbourne | $500 | 38.9% | 38.7% |
| Noble Park | South Eastern Melbourne | $520 | 44.4% | 37.6% |

These are the eight with the highest rent-to-income out of the 34 areas that are above average on both measures (I call these "squeezed").

## Why I picked them

- Rent-to-income tells me how stretched an area is compared to others. Rent growth tells me how quickly it got there. Being high on both seemed like the best sign of where affordability could be a problem.
- Seven of the eight are in the outer south-east or on the Mornington Peninsula. This lines up with the overall results: 7 of 8 South Eastern Melbourne areas and all 5 Mornington Peninsula areas are squeezed, compared with 3 of 22 in Inner Melbourne and 0 of 12 in Outer Western Melbourne.
- Across the 109 areas with income data, higher income goes with slower rent growth (correlation of -0.52). So lower-income areas have generally seen rents rise faster.

## Other areas to keep an eye on

- Rents grew fastest in Keilor (58.5%), Pakenham (54.3%), Dromana-Portsea (50.6%), Berwick (50.0%) and Cranbourne (48.7%). Some of these aren't far above average on rent-to-income yet, but they are moving quickly.
- Box Hill (48.1%), CBD-St Kilda Rd (45.6%) and Clayton (40.2%) have high rent-to-income, but I didn't put them in the list. A lot of students live there, so household income is low for other reasons. They would need a different measure before anyone acts on them.

## What this can't tell us

- **Why rents went up.** The data shows where and by how much, not the reason.
- **What any one household pays.** Rent-to-income is based on area medians, so it isn't a real rent burden for a person.
- **Current incomes.** Rent is from 2025 and income is from the 2021 Census. This means the percentages are too high in absolute terms, so I only use them to compare areas with each other. The order could change a bit if I had newer income data.
- **Grouped areas.** Some rent areas combine several suburbs, so their income is a population-weighted average of suburb medians, not a true median.
- **Keilor is a borderline case.** Its rent-to-income is 31.8%, right on the cut-off, and it only counts as squeezed because I rounded the averages to one decimal place. That's why I report 34 of 110 and not 33.
- **Yarra Ranges** has no income figure, so it isn't in the rent-to-income analysis.

## How confident I am

Fairly confident that outer south-east areas stand out on both measures. Less confident about the exact order of the eight, because the income data is older than the rent data.

## What I'd do next

1. Check the eight areas against newer income or rental stress data from another source.
2. Look at each one separately, for example by house vs unit, using the rent history in my database.
3. Find a better way to measure the student areas so I can include them.
