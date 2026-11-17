# Updating the dataset

Keep full issuer PDFs outside the repository. Use the original consolidated annual release and read any corrections and restatements. The ledger locators use physical PDF page numbers starting at 1, plus the table and line.

1. Add a stable ID in **data/sources.json** with securities code, exact title, HTTPS URL, publication and retrieval dates in ISO format, locator and notes. An undated business page can leave its publication date empty.
2. Add a row in **data/periods.csv** with the exact start and end, consolidation basis, accounting standard and annual release ID. Record an accounting break with **growth_comparable=no**. Use **Restated** for periods using later restated figures, and cite the later document for each affected value. Point to the original release in the period note.
3. Add one sourced row per metric in **data/facts.csv**. Preserve the source sign, dash or numeric string, and units. Populate the normalized amount and explain adjustments. Omit unavailable lines. Cash expenditure records should each point to the investing cash flow line. Debt components should each point to the balance sheet.
4. Mark debt scope **complete** when you've verified all separately reported borrowings, bonds and recognized leases. List their metric IDs in **debt_components**, separated by semicolons. For an issuer with separately presented current and noncurrent bonds, extend the debt metric registry to preserve both amounts. Use **unconfirmed** if coverage cannot be established.
5. Check for equity splits. Update the canonical **share_basis** and the mapping from reported bases to canonical basis in **data/companies.json**. Update matching periods and facts. Keep the original share basis and factor per EPS and shares entry. Omit per-share inputs with an unresolved basis. Saved JSON files on an obsolete basis prompt the researcher to review affected values.
6. Run the lint and test commands in the README. Restart Streamlit to refresh its data cache. Check dates and original figures against the PDFs, review EPS reconciliation and recompute debt and capex from their components. Refresh the screenshots and example report if they use the changed data.

## Adding an issuer

Add the code to **companies.json** using the existing schema. Include its issuer-sourced business description, exact name, industry, source IDs, documented split basis, sample assumptions and five research prompts. Each scenario array contains revenue growth and attributable margin as decimal fractions, then forward P/E and rationale. The initial share assumption comes from the selected fiscal year's weighted-average shares.

Add verified annual periods and facts using the same schema. The company selector reads the registry. The overview's comparison text is specific to USS and MonotaRO, and the chart palette supports up to three series. Revise those as the comparison expands.
