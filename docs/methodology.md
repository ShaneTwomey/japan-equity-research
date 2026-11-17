# Methodology

Reported facts use current-year figures from consolidated Japanese GAAP statements. “Attributable net profit” refers to profit attributable to owners of the parent. The financial version is “As released.” Post-split normalization changes share units only. The original EPS, count and split basis remain in the provenance table. The editable notes and scenarios start with illustrative assumptions. Bear, Base and Bull carry no assigned probabilities.

Amounts are denominated in JPY millions (JPYm), shares in millions, and EPS and share price in JPY per share. To obtain JPYm, multiply 千円 by 0.001, 百万円 by 1 and 億円 by 100. Divide actual shares by one million. Absent inputs remain blank. An explicitly published dash is preserved in provenance and interpreted as nil. Losses and net cash preserve their signs.

## Historical metrics

| Derived metric | Calculation |
| --- | --- |
| Revenue growth | Current annual revenue ÷ prior comparable annual revenue − 1 |
| Operating margin | Operating profit ÷ revenue |
| Attributable net margin | Profit attributable to owners of the parent ÷ revenue |
| Cash flow after capital expenditure | Operating cash flow − cash PP&E purchases − cash intangible purchases |
| Interest-bearing debt | Reported borrowings and bonds plus disclosed current and noncurrent lease liabilities |
| Net debt | Interest-bearing debt including disclosed leases − closing cash and cash equivalents |
| Recomputed basic EPS | Attributable net profit in JPYm ÷ weighted-average shares in millions |

Growth requires adjacent full years, comparable reporting and positive prior revenue. The oldest bundled years have no growth comparison. MonotaRO's Japanese release reports no profit or loss impact from its 2022 revenue recognition change. The subsequent translation correction affects financing cash flow lines and standalone income. [Japanese release, PDF page 12](https://corp.monotaro.com/ir/upload_file/m005-m005_02/3064_20230202599174_P01_.pdf) · [English correction](https://corp.monotaro.com/en/ir/upload_file/m005-m005_02/Updateflashreort20221231.pdf)

Cash capex covers PP&E and intangible cash purchases. It excludes asset-sale proceeds, acquisitions and lease repayments. Outflows are shown as positive capex while provenance retains the source sign. Debt includes the lines listed in the period's **debt_components** field. It excludes unrecognized lease commitments and unclassified other liabilities. MonotaRO's December 2021 release omits separate short-term and current long-term borrowing lines. The line-item table leaves those entries blank and the total uses the reviewed borrowing and lease lines present. A period marked as having unconfirmed debt scope suppresses gross and net debt.

USS's fee-centric auction activity differs from MonotaRO's merchandise distribution, which carries inventory and fulfillment costs. Their fiscal windows also differ. Read cross-company margins and cash flow in that context.

## EPS and split bases

Use the annual weighted-average ordinary shares used for basic EPS. The reconciliation checks reported EPS against attributable profit divided by those shares. The tolerance is **JPY 0.005 + JPY 1 million ÷ actual weighted-average shares**, or **0.005 + 1 ÷ shares in millions**. It allows for two-decimal EPS rounding and whole-million truncation of profit. The app displays unexplained differences when they occur.

- USS implemented a 2-for-1 split on April 1, 2024. The app halves the originally reported March 2022 and March 2023 EPS and doubles weighted-average shares. The March 2024 release already reflects the split. The normalized March 2023 EPS can differ from the later issuer comparative due to rounding the original EPS first. [USS March 2024 annual release](https://www.ussnet.co.jp/en/ir/item/2024_4q.pdf)
- MonotaRO implemented a 2-for-1 split on April 1, 2021. The December 2021 release already reflects it in EPS and average shares. All five years use the same basis. [MonotaRO December 2021 annual release](https://corp.monotaro.com/en/ir/upload_file/m005-m005_02/Quarter4_FY2021_2.pdf)

## Forecast and price comparison

The scenario projects the full fiscal year following the base. The app flags forecasts for which bundled actuals already exist and forecasts for elapsed fiscal periods with missing actuals.

1. Forecast revenue = base revenue × (1 + revenue growth).
2. Forecast attributable profit = forecast revenue × assumed attributable net margin.
3. Forecast basic EPS = forecast attributable profit ÷ projected weighted-average ordinary shares.
4. **Implied price: forecast EPS × assumed forward P/E.**
5. Price upside/downside = implied price ÷ manual reference share price − 1.

Growth and margin are decimals for calculation and percentages for display. Profit in JPYm divided by shares in millions yields JPY per share. For example, 100,000 JPYm × 1.10 gives 110,000 JPYm of sales. At 10% margin, attributable profit is 11,000 JPYm. Dividing by 100 million shares gives JPY 110 EPS. At 20× this implies JPY 2,200 per share, or 10% above a JPY 2,000 reference price. This price comparison excludes dividends and is shown without annualization.

Manual reference prices require a positive amount, date, source and confirmation of the forecast split basis. Leave the price blank if its basis cannot be established. Positive EPS produces an implied price without a reference. EPS of zero or below suppresses P/E valuation and retains the earnings output. Positive numeric valuation inputs have a floor of 0.000001 (one share for the weighted-average share count in millions).

The heatmap varies net margin by up to ±2 percentage points in one-point steps and P/E from 60% through 140% of the assumed multiple. It holds the period, base revenue, growth and projected shares constant. Its center reproduces the selected case's implied price, with unavailable cells where EPS is nonpositive.

## Implementation references

- [Streamlit 1.52 downloads](https://docs.streamlit.io/1.52.0/develop/api-reference/widgets/st.download_button) and [Streamlit AppTest](https://docs.streamlit.io/develop/concepts/app-testing)
- [pandas 2.3 CSV reader](https://pandas.pydata.org/pandas-docs/version/2.3/reference/api/pandas.read_csv.html)
- [Plotly Heatmap](https://plotly.com/python/reference/heatmap/)
- [pytest 9 reference](https://docs.pytest.org/en/9.0.x/reference/reference.html)
- [Ruff linter](https://docs.astral.sh/ruff/linter/)
