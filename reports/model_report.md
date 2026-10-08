# Model report: gradient-boosting-20261007-fe58760a

Trained: 2026-10-07T18:08:51.072782+00:00  |  Selected: **Gradient Boosting**

## Held-out test metrics (dropout = positive class)

| Model | CV F1 | CV ROC-AUC | Test Acc | Test Precision | Test Recall | Test F1 | Test ROC-AUC |
|---|---|---|---|---|---|---|---|
| Logistic Regression | 0.786 | 0.920 | 0.878 | 0.791 | 0.842 | 0.816 | 0.933 |
| Decision Tree | 0.761 | 0.892 | 0.862 | 0.748 | 0.859 | 0.800 | 0.920 |
| Random Forest | 0.773 | 0.915 | 0.881 | 0.823 | 0.803 | 0.813 | 0.931 |
| Gradient Boosting | 0.792 | 0.918 | 0.887 | 0.813 | 0.842 | 0.827 | 0.938 |

## Top permutation importances (test ROC-AUC drop)

- Units approved (second semester): 0.1674
- Tuition fees up to date: 0.0306
- Units approved (first semester): 0.0302
- Units enrolled (second semester): 0.0173
- Units enrolled (first semester): 0.0112
- Course: 0.0079
- Age at enrollment: 0.0055
- Unemployment rate (%): 0.0048
- Mother's occupation (code): 0.0030
- GDP change (%): 0.0025

## EDA insights

- Class balance: 2209 graduates, 1421 dropouts and 794 still enrolled; the binary dropout rate is 32.1%.
- Students whose tuition fees are not up to date have a 87% dropout rate versus 25% for those up to date.
- Students with no approved units in the 2nd semester have a 84% dropout rate versus 8% for those with 7 or more approved units.
- Scholarship holders: 12% dropout; non-holders: 39%.
- Students aged 30+ at enrollment: 54% dropout versus 21% for those aged 19 or younger.
- These are associations in historical data from one institution, not evidence of causation.